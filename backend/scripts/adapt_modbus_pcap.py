"""Streaming, non-production Modbus/TCP PCAP adapter.

This module deliberately has no third-party packet-parser dependency. It reads
classic pcap files, decodes Ethernet/IPv4/TCP, reassembles enough TCP payload
bytes to parse Modbus/TCP messages, and emits JSON-compatible network events.
It never assigns attack labels, authorization decisions, RTU IDs, or physical
measurements.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import ipaddress
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


class PcapFormatError(ValueError):
    """Raised for a malformed or unsupported classic PCAP stream."""


def _pcap_header(raw: bytes) -> Tuple[str, float]:
    if len(raw) != 24:
        raise PcapFormatError("short global header")
    magic = raw[:4]
    if magic == b"\xd4\xc3\xb2\xa1":
        endian, scale = "<", 1e-6
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian, scale = ">", 1e-6
    elif magic == b"\x4d\x3c\xb2\xa1":
        endian, scale = "<", 1e-9
    elif magic == b"\xa1\xb2\x3c\x4d":
        endian, scale = ">", 1e-9
    else:
        raise PcapFormatError(f"unsupported PCAP magic {magic.hex()}")
    version_major, version_minor, _thiszone, _sigfigs, snaplen, network = struct.unpack(
        endian + "HHiiii", raw[4:]
    )
    if (version_major, version_minor) != (2, 4):
        raise PcapFormatError(f"unsupported PCAP version {version_major}.{version_minor}")
    if snaplen <= 0 or network != 1:
        raise PcapFormatError(f"unsupported linktype/snaplen network={network} snaplen={snaplen}")
    return endian, scale


def iter_pcap_packets(path: Path, limit: Optional[int] = None) -> Iterator[Tuple[int, float, bytes, int]]:
    """Yield packet number, epoch timestamp, captured bytes, original length."""
    with path.open("rb") as handle:
        prefix = handle.read(4)
        handle.seek(0)
        if prefix == b"\x0a\x0d\x0d\x0a":
            yield from _iter_pcapng_packets(handle, limit)
            return
        endian, scale = _pcap_header(handle.read(24))
        number = 0
        while limit is None or number < limit:
            header = handle.read(16)
            if not header:
                return
            if len(header) != 16:
                raise PcapFormatError(f"truncated packet header after packet {number}")
            ts_sec, ts_frac, incl_len, orig_len = struct.unpack(endian + "IIII", header)
            if incl_len > 64 * 1024 * 1024:
                raise PcapFormatError(f"unreasonable captured length {incl_len} at packet {number + 1}")
            payload = handle.read(incl_len)
            if len(payload) != incl_len:
                raise PcapFormatError(f"truncated packet {number + 1}: expected {incl_len} bytes")
            number += 1
            yield number, float(ts_sec) + float(ts_frac) * scale, payload, orig_len


def _iter_pcapng_packets(handle, limit: Optional[int] = None) -> Iterator[Tuple[int, float, bytes, int]]:
    """Yield Ethernet packets from pcapng Enhanced Packet Blocks.

    This intentionally supports the common pcapng subset used by capture
    tools: section headers, interface descriptions, enhanced packet blocks,
    and simple packet blocks. Multi-interface timestamp resolutions are read
    from the interface options when present; unsupported blocks are skipped.
    """
    interfaces: Dict[int, Tuple[str, int, int]] = {}
    number = 0
    endian = "<"
    while limit is None or number < limit:
        header = handle.read(8)
        if not header:
            return
        if len(header) != 8:
            raise PcapFormatError(f"truncated pcapng block header after packet {number}")
        block_type_raw, block_length_raw = header[:4], header[4:]
        if block_type_raw == b"\x0a\x0d\x0d\x0a":
            bom = handle.read(4)
            if len(bom) != 4:
                raise PcapFormatError("truncated pcapng section header")
            if bom == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif bom == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            else:
                raise PcapFormatError(f"unsupported pcapng byte order {bom.hex()}")
            remaining = struct.unpack(endian + "I", block_length_raw)[0] - 12
            if remaining < 0:
                raise PcapFormatError("invalid pcapng section length")
            handle.seek(remaining, 1)
            continue
        block_type = struct.unpack(endian + "I", block_type_raw)[0]
        block_length = struct.unpack(endian + "I", block_length_raw)[0]
        if block_length < 12 or block_length > 256 * 1024 * 1024:
            raise PcapFormatError(f"invalid pcapng block length {block_length}")
        body = handle.read(block_length - 8)
        if len(body) != block_length - 8:
            raise PcapFormatError("truncated pcapng block")
        if struct.unpack(endian + "I", body[-4:])[0] != block_length:
            raise PcapFormatError("pcapng block length trailer mismatch")
        content = body[:-4]
        if block_type == 1 and len(content) >= 8:  # Interface Description Block
            linktype, _reserved, snaplen = struct.unpack(endian + "HHI", content[:8])
            resolution = 1e-6
            options = content[8:]
            pos = 0
            while pos + 4 <= len(options):
                code, length = struct.unpack(endian + "HH", options[pos:pos + 4])
                pos += 4
                value = options[pos:pos + length]
                pos += (length + 3) & ~3
                if code == 9 and value:
                    resolution = (10 ** -value[0]) if not (value[0] & 0x80) else (2 ** -(value[0] & 0x7F))
                if code == 0:
                    break
            interfaces[len(interfaces)] = (endian, linktype, resolution)
        elif block_type == 6 and len(content) >= 20:  # Enhanced Packet Block
            interface_id, ts_high, ts_low, captured_len, original_len = struct.unpack(endian + "IIIII", content[:20])
            interface = interfaces.get(interface_id, (endian, 1, 1e-6))
            if interface[1] != 1:
                continue
            packet = content[20:20 + captured_len]
            number += 1
            yield number, ((ts_high << 32) | ts_low) * interface[2], packet, original_len
        elif block_type == 3 and len(content) >= 4:  # Simple Packet Block
            original_len = struct.unpack(endian + "I", content[:4])[0]
            packet = content[4:]
            number += 1
            yield number, float(number), packet, original_len


def _tcp_packet(packet: bytes) -> Optional[Dict[str, object]]:
    """Decode Ethernet/IPv4/TCP header and return payload metadata."""
    if len(packet) < 14:
        return None
    ethertype = struct.unpack("!H", packet[12:14])[0]
    offset = 14
    if ethertype == 0x8100 and len(packet) >= 18:
        ethertype = struct.unpack("!H", packet[16:18])[0]
        offset = 18
    if ethertype != 0x0800 or len(packet) < offset + 20:
        return None
    first = packet[offset]
    version, ihl_words = first >> 4, first & 0x0F
    if version != 4 or ihl_words < 5:
        return None
    ip_header_len = ihl_words * 4
    if len(packet) < offset + ip_header_len:
        return None
    ip = packet[offset : offset + ip_header_len]
    if ip[9] != 6:
        return None
    src = str(ipaddress.ip_address(ip[12:16]))
    dst = str(ipaddress.ip_address(ip[16:20]))
    tcp_offset = offset + ip_header_len
    if len(packet) < tcp_offset + 20:
        return None
    src_port, dst_port, seq = struct.unpack("!HHI", packet[tcp_offset : tcp_offset + 8])
    data_offset = (packet[tcp_offset + 12] >> 4) * 4
    if data_offset < 20 or len(packet) < tcp_offset + data_offset:
        return None
    flags = struct.unpack("!H", packet[tcp_offset + 12 : tcp_offset + 14])[0] & 0x01FF
    return {
        "source_ip": src,
        "destination_ip": dst,
        "source_port": src_port,
        "destination_port": dst_port,
        "sequence": seq,
        "tcp_flags": flags,
        "payload": packet[tcp_offset + data_offset :],
        "packet_length": len(packet),
    }


def _message_from_buffer(buffer: bytearray) -> Optional[Tuple[Dict[str, int], int]]:
    """Parse one Modbus/TCP message from a direction buffer, if complete."""
    if len(buffer) < 8:
        return None
    transaction_id, protocol_id, length = struct.unpack("!HHH", buffer[:6])
    if protocol_id != 0 or length < 2 or length > 260:
        # Drop one byte to resynchronise rather than treating arbitrary TCP
        # payload as a Modbus event.
        del buffer[:1]
        return None
    total = 6 + length
    if len(buffer) < total:
        return None
    unit_id = buffer[6]
    function_code = buffer[7]
    if function_code == 0:
        # Function code zero is not a Modbus application function. It can
        # occur when a capture begins in the middle of a TCP stream; discard
        # one byte and wait for a valid MBAP boundary.
        del buffer[:1]
        return None
    pdu = bytes(buffer[8:total])
    del buffer[:total]
    reference = 0
    if len(pdu) >= 3 and function_code in (1, 2, 3, 4, 5, 6, 15, 16):
        reference = struct.unpack("!H", pdu[0:2])[0]
    return {
        "transaction_id": transaction_id,
        "protocol_id": protocol_id,
        "modbus_length": length,
        "unit_id": unit_id,
        "function_code": function_code,
        "reference_number": reference,
        "exception": 1 if function_code & 0x80 else 0,
    }, total


def _iso_timestamp(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat()


def iter_modbus_events(path: Path, limit_packets: Optional[int] = None, include_unmatched: bool = False) -> Tuple[Iterator[Dict[str, object]], Dict[str, object]]:
    """Return a lazy event iterator and mutable parse summary.

    Events are request-side Modbus messages. A matched response enriches the
    request with latency and success. Unmatched requests remain traceable and
    omit ``success`` rather than being mislabeled as errors.
    """
    summary: Dict[str, object] = {
        "capture_file": str(path),
        "packet_count": 0,
        "ipv4_tcp_packets": 0,
        "tcp_payload_packets": 0,
        "modbus_messages": 0,
        "events_emitted": 0,
        "matched_responses": 0,
        "exception_responses": 0,
        "unmatched_requests": 0,
        "packet_parse_errors": 0,
    }

    def generator() -> Iterator[Dict[str, object]]:
        buffers: Dict[Tuple[str, int, str, int], bytearray] = defaultdict(bytearray)
        pending: Dict[Tuple[Tuple[str, int, str, int], int, int], Dict[str, object]] = {}
        orientations: Dict[Tuple[Tuple[str, int, str, int], Tuple[str, int, str, int]], Tuple[str, int, str, int]] = {}
        try:
            for packet_number, timestamp, packet, _original_length in iter_pcap_packets(path, limit_packets):
                summary["packet_count"] = int(summary["packet_count"]) + 1
                try:
                    decoded = _tcp_packet(packet)
                except (ValueError, struct.error):
                    summary["packet_parse_errors"] = int(summary["packet_parse_errors"]) + 1
                    continue
                if decoded is None:
                    continue
                summary["ipv4_tcp_packets"] = int(summary["ipv4_tcp_packets"]) + 1
                payload = bytes(decoded["payload"])
                if not payload:
                    continue
                summary["tcp_payload_packets"] = int(summary["tcp_payload_packets"]) + 1
                src = str(decoded["source_ip"])
                dst = str(decoded["destination_ip"])
                sport, dport = int(decoded["source_port"]), int(decoded["destination_port"])
                if sport != 502 and dport != 502:
                    continue
                flow = (src, sport, dst, dport)
                buffers[flow].extend(payload)
                reverse_flow = (dst, dport, src, sport)
                conversation = tuple(sorted((flow, reverse_flow)))
                # Some supplied basic captures use the process listening on
                # port 502 as the message initiator. Infer direction from the
                # first Modbus message in each conversation instead of using
                # the conventional destination-port heuristic.
                while True:
                    parsed = _message_from_buffer(buffers[flow])
                    if parsed is None:
                        break
                    message, _message_size = parsed
                    request_flow = orientations.get(conversation)
                    if request_flow is None:
                        orientations[conversation] = flow
                        request_flow = flow
                    summary["modbus_messages"] = int(summary["modbus_messages"]) + 1
                    tid = int(message["transaction_id"])
                    unit = int(message["unit_id"])
                    reverse = (dst, dport, src, sport)
                    is_request = flow == request_flow
                    key = ((flow if is_request else reverse_flow), tid, unit)
                    if is_request:
                        event: Dict[str, object] = {
                            "capture_file": str(path),
                            "capture_packet_number": packet_number,
                            "timestamp_epoch": timestamp,
                            "timestamp_utc": _iso_timestamp(timestamp),
                            "source": src,
                            "target_rtu": "UNMAPPED",
                            "source_ip": src,
                            "destination_ip": dst,
                            "source_port": sport,
                            "destination_port": dport,
                            "protocol": "Modbus/TCP",
                            "packet_length": int(decoded["packet_length"]),
                            "tcp_flags": int(decoded["tcp_flags"]),
                            "transaction_id": tid,
                            "unit_id": unit,
                            "modbus_length": int(message["modbus_length"]),
                            "function_code": int(message["function_code"]),
                            "reference_number": int(message["reference_number"]),
                            "response_matched": False,
                            "observer_verified": False,
                            "is_unexpected_write": False,
                        }
                        pending[key] = event
                    else:
                        event = pending.pop(key, None)
                        if event is None:
                            continue
                        event["response_matched"] = True
                        event["response_packet_number"] = packet_number
                        event["response_timestamp_epoch"] = timestamp
                        event["response_time_ms"] = round((timestamp - float(event["timestamp_epoch"])) * 1000.0, 6)
                        event["success"] = not bool(message["exception"])
                        if message["exception"]:
                            event["exception_response"] = True
                            summary["exception_responses"] = int(summary["exception_responses"]) + 1
                        summary["matched_responses"] = int(summary["matched_responses"]) + 1
                        summary["events_emitted"] = int(summary["events_emitted"]) + 1
                        yield event
        except (OSError, PcapFormatError) as exc:
            summary["error"] = str(exc)
        summary["unmatched_requests"] = len(pending)
        if include_unmatched:
            for event in pending.values():
                summary["events_emitted"] = int(summary["events_emitted"]) + 1
                yield event
        summary["events_emitted"] = int(summary["events_emitted"])

    return generator(), summary


def process_capture(path: Path, output_dir: Path, max_events: int = 1000, limit_packets: Optional[int] = None) -> Dict[str, object]:
    """Parse one capture and write a bounded, gzipped trace sample."""
    output_dir.mkdir(parents=True, exist_ok=True)
    events, summary = iter_modbus_events(path, limit_packets=limit_packets)
    event_path = output_dir / f"{path.stem}.events.jsonl.gz"
    written = 0
    with gzip.open(event_path, "wt", encoding="utf-8") as handle:
        for event in events:
            if written < max_events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
                written += 1
    summary["event_sample_path"] = str(event_path)
    summary["event_sample_count"] = written
    summary["event_sample_limit"] = max_events
    return summary


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--max-events-per-capture", type=int, default=1000)
    parser.add_argument("--limit-packets", type=int, default=None)
    args = parser.parse_args()
    raw = args.dataset_root / "raw"
    captures = sorted([*raw.glob("*.cap"), *raw.glob("*.pcap")])
    if not captures:
        parser.error(f"no .cap/.pcap files found under {raw}")
    summaries = [process_capture(p, args.output_dir / "events", args.max_events_per_capture, args.limit_packets) for p in captures]
    report = {
        "adapter": "backend/scripts/adapt_modbus_pcap.py",
        "dataset_root": str(args.dataset_root),
        "capture_count": len(summaries),
        "max_events_per_capture": args.max_events_per_capture,
        "limit_packets": args.limit_packets,
        "captures": summaries,
        "fields_produced": [
            "capture_file", "capture_packet_number", "timestamp_epoch", "timestamp_utc", "source", "target_rtu",
            "source_ip", "destination_ip", "source_port", "destination_port", "protocol", "packet_length",
            "tcp_flags", "transaction_id", "unit_id", "modbus_length", "function_code", "reference_number",
            "response_matched", "response_time_ms", "success", "observer_verified", "is_unexpected_write"
        ],
        "physical_fields_unavailable": [
            "state_estimation_result", "PCD residuals", "voltage", "power flow", "topology", "telemetry", "attack labels"
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "adapter_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"capture_count": len(summaries), "summary": str(args.output_dir / 'adapter_summary.json')}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

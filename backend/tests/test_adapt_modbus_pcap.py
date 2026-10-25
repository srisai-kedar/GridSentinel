import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from adapt_modbus_pcap import _message_from_buffer, _tcp_packet, iter_modbus_events  # noqa: E402


def _packet(payload: bytes, src_port=1234, dst_port=502, seq=1, flags=0x18, reverse=False) -> bytes:
    eth = b"\x00" * 12 + struct.pack("!H", 0x0800)
    ip = bytearray(20)
    ip[0] = 0x45
    struct.pack_into("!H", ip, 2, 20 + 20 + len(payload))
    ip[8] = 64
    ip[9] = 6
    ip[12:16] = bytes([192, 168, 1, 20 if reverse else 10])
    ip[16:20] = bytes([192, 168, 1, 10 if reverse else 20])
    tcp = bytearray(20)
    struct.pack_into("!HHI", tcp, 0, src_port, dst_port, seq)
    tcp[12] = 0x50
    struct.pack_into("!H", tcp, 12, (5 << 12) | flags)
    return eth + bytes(ip) + bytes(tcp) + payload


def _pcap(path: Path, packets):
    with path.open("wb") as handle:
        handle.write(b"\xd4\xc3\xb2\xa1" + struct.pack("<HHiiii", 2, 4, 0, 0, 65535, 1))
        for sec, payload in packets:
            handle.write(struct.pack("<IIII", sec, 0, len(payload), len(payload)))
            handle.write(payload)


def test_modbus_message_parser_decodes_fc3():
    # TID=7, protocol=0, length=6, unit=1, FC=3, reference=10, quantity=2.
    message = struct.pack("!HHHBBHH", 7, 0, 6, 1, 3, 10, 2)
    parsed = _message_from_buffer(bytearray(message))
    assert parsed[0]["transaction_id"] == 7
    assert parsed[0]["function_code"] == 3
    assert parsed[0]["reference_number"] == 10


def test_tcp_packet_decodes_headers_and_payload():
    decoded = _tcp_packet(_packet(b"abc"))
    assert decoded["source_ip"] == "192.168.1.10"
    assert decoded["destination_port"] == 502
    assert decoded["payload"] == b"abc"


def test_event_format_matches_network_contract_and_response_latency(tmp_path):
    request = struct.pack("!HHHBBHH", 7, 0, 6, 1, 3, 10, 2)
    response = struct.pack("!HHHBBBH", 7, 0, 5, 1, 3, 4, 0x1234)
    path = tmp_path / "sample.cap"
    _pcap(path, [(10, _packet(request)), (11, _packet(response, src_port=502, dst_port=1234, reverse=True))])
    events, summary = iter_modbus_events(path)
    rows = list(events)
    assert len(rows) == 1
    assert rows[0]["protocol"] == "Modbus/TCP"
    assert rows[0]["target_rtu"] == "UNMAPPED"
    assert rows[0]["function_code"] == 3
    assert rows[0]["response_matched"] is True
    assert rows[0]["response_time_ms"] == 1000.0
    assert summary["packet_count"] == 2


def test_malformed_input_is_reported_without_fake_events(tmp_path):
    path = tmp_path / "bad.cap"
    path.write_bytes(b"\xd4\xc3\xb2\xa1" + b"\x00" * 10)
    events, summary = iter_modbus_events(path)
    assert list(events) == []
    assert "error" in summary

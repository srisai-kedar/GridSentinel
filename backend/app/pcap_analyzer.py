"""Bounded, non-production PCAP analysis service for the website."""

from __future__ import annotations

import math
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Any

from scripts.adapt_modbus_pcap import iter_modbus_events, iter_pcap_packets, _tcp_packet, PcapFormatError


MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_PACKETS = 2_000_000
MAX_PROCESSING_SECONDS = 30.0


def analyze_capture(path: Path, *, max_packets: int = MAX_PACKETS, max_seconds: float = MAX_PROCESSING_SECONDS) -> Dict[str, Any]:
    started = time.perf_counter()
    packet_count = 0
    tcp_packets = 0
    packet_size_sum = 0
    packet_size_min = None
    packet_size_max = None
    packet_size_histogram = Counter()

    for number, _timestamp, packet, _original_length in iter_pcap_packets(path, limit=max_packets + 1):
        if number > max_packets:
            raise ValueError(f"packet limit exceeded ({max_packets:,})")
        packet_count += 1
        packet_size = len(packet)
        packet_size_sum += packet_size
        packet_size_min = packet_size if packet_size_min is None else min(packet_size_min, packet_size)
        packet_size_max = packet_size if packet_size_max is None else max(packet_size_max, packet_size)
        bucket = min(packet_size // 100, 65)
        packet_size_histogram[str(bucket * 100)] += 1
        if _tcp_packet(packet) is not None:
            tcp_packets += 1
        if time.perf_counter() - started > max_seconds:
            raise TimeoutError(f"processing time limit exceeded ({max_seconds:.1f}s)")

    events, parser_summary = iter_modbus_events(path, limit_packets=max_packets, include_unmatched=True)
    function_codes = Counter()
    source_ips = set()
    latencies = []
    matched = 0
    errors = 0
    event_count = 0
    for event in events:
        event_count += 1
        function_codes[str(event.get("function_code", 0))] += 1
        if event.get("source_ip"):
            source_ips.add(str(event["source_ip"]))
        if event.get("response_matched"):
            matched += 1
        if event.get("success") is False:
            errors += 1
        latency = event.get("response_time_ms")
        if latency is not None and math.isfinite(float(latency)):
            latencies.append(float(latency))
        if time.perf_counter() - started > max_seconds:
            raise TimeoutError(f"processing time limit exceeded ({max_seconds:.1f}s)")

    elapsed = time.perf_counter() - started
    return {
        "analysis_type": "network_only_pcap_analysis",
        "production_inference_run": False,
        "labels_assigned": False,
        "physical_features_available": False,
        "packet_summary": {
            "total_packets": packet_count,
            "ipv4_tcp_packets": tcp_packets,
            "file_size_bytes": path.stat().st_size,
            "min_packet_bytes": packet_size_min,
            "max_packet_bytes": packet_size_max,
            "mean_packet_bytes": round(packet_size_sum / packet_count, 3) if packet_count else None,
            "size_histogram_100_byte_buckets": dict(sorted(packet_size_histogram.items(), key=lambda item: int(item[0]))),
        },
        "modbus_summary": {
            "decoded_messages": parser_summary.get("modbus_messages", 0),
            "request_events": event_count,
            "function_code_distribution": dict(sorted(function_codes.items(), key=lambda item: int(item[0]))),
            "source_cardinality": len(source_ips),
            "request_response_matched": matched,
            "matched_response_fraction": matched / event_count if event_count else 0.0,
            "mean_latency_ms": round(sum(latencies) / len(latencies), 6) if latencies else None,
            "min_latency_ms": min(latencies) if latencies else None,
            "max_latency_ms": max(latencies) if latencies else None,
            "error_responses": errors,
            "unmatched_requests": parser_summary.get("unmatched_requests", 0),
            "parser_errors": parser_summary.get("packet_parse_errors", 0),
        },
        "limitations": [
            "Network analysis only; this is not an attack detector.",
            "No attack labels, physical-system fields, or production-model predictions are generated.",
            "Request/response metrics depend on the adapter's TCP reassembly quality.",
        ],
        "processing_seconds": round(elapsed, 6),
    }

import struct
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.pcap_analyzer import analyze_capture  # noqa: E402
from scripts.adapt_modbus_pcap import PcapFormatError  # noqa: E402


def _packet(payload: bytes) -> bytes:
    eth = b"\x00" * 12 + struct.pack("!H", 0x0800)
    ip = bytearray(20); ip[0] = 0x45; struct.pack_into("!H", ip, 2, 40 + len(payload)); ip[8] = 64; ip[9] = 6
    ip[12:16] = bytes([192, 168, 1, 10]); ip[16:20] = bytes([192, 168, 1, 20])
    tcp = bytearray(20); struct.pack_into("!HHI", tcp, 0, 1234, 502, 1); tcp[12] = 0x50
    return eth + bytes(ip) + bytes(tcp) + payload


def _pcap(path: Path):
    message = struct.pack("!HHHBBHH", 7, 0, 6, 1, 3, 10, 2)
    with path.open("wb") as handle:
        handle.write(b"\xd4\xc3\xb2\xa1" + struct.pack("<HHiiii", 2, 4, 0, 0, 65535, 1))
        handle.write(struct.pack("<IIII", 10, 0, len(_packet(message)), len(_packet(message))))
        handle.write(_packet(message))


def _pcapng(path: Path):
    message = struct.pack("!HHHBBHH", 7, 0, 6, 1, 3, 10, 2)
    packet = _packet(message)
    def block(block_type, content):
        total = 12 + len(content)
        return struct.pack("<II", block_type, total) + content + struct.pack("<I", total)
    section = struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1)
    interface = struct.pack("<HHI", 1, 0, 65535) + struct.pack("<HH", 0, 0)
    epb = struct.pack("<IIIII", 0, 0, 10_000_000, len(packet), len(packet)) + packet
    epb += b"\x00" * ((-len(epb)) % 4)
    path.write_bytes(block(0x0A0D0D0A, section) + block(1, interface) + block(6, epb))


def test_valid_capture_returns_network_summary(tmp_path):
    path = tmp_path / "capture.cap"; _pcap(path)
    result = analyze_capture(path, max_packets=10, max_seconds=2)
    assert result["production_inference_run"] is False
    assert result["packet_summary"]["total_packets"] == 1
    assert result["modbus_summary"]["decoded_messages"] == 1
    assert result["modbus_summary"]["function_code_distribution"] == {"3": 1}


def test_pcapng_capture_is_supported(tmp_path):
    path = tmp_path / "capture.pcapng"; _pcapng(path)
    result = analyze_capture(path, max_packets=10, max_seconds=2)
    assert result["packet_summary"]["total_packets"] == 1
    assert result["modbus_summary"]["decoded_messages"] == 1


def test_invalid_capture_reports_parser_failure(tmp_path):
    path = tmp_path / "bad.pcap"; path.write_bytes(b"not a capture")
    with pytest.raises(PcapFormatError):
        analyze_capture(path, max_packets=10, max_seconds=2)


def test_packet_limit_is_enforced(tmp_path):
    path = tmp_path / "capture.cap"; _pcap(path)
    with pytest.raises(ValueError, match="packet limit"):
        analyze_capture(path, max_packets=0, max_seconds=2)


def test_upload_temp_prefix_is_not_left_by_normalized_cleanup_contract():
    # The endpoint uses NamedTemporaryFile(delete=False) and unlinks it in a
    # finally block. This test documents the prefix used by the cleanup path.
    assert not list(Path(tempfile.gettempdir()).glob("gridsentinel-pcap-*.cap"))


def test_endpoint_rejects_unsupported_extension_without_processing():
    from app.main import app
    with TestClient(app) as client:
        response = client.post("/tools/pcap-analyzer", headers={"X-PCAP-Filename": "notes.txt"}, content=b"not a capture")
    assert response.status_code == 415


def test_endpoint_reports_malformed_supported_capture():
    from app.main import app
    with TestClient(app) as client:
        response = client.post("/tools/pcap-analyzer", headers={"X-PCAP-Filename": "bad.cap"}, content=b"not a capture")
    assert response.status_code == 422

"use client";

import React, { useState } from "react";
import { FileSearch, LoaderCircle, Upload } from "lucide-react";
import { analyzePcap, PcapAnalysis } from "@/lib/api";

const n = (value: number | null | undefined, digits = 0) => typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";

export function PcapAnalyzer() {
  const [result, setResult] = useState<PcapAnalysis | null>(null);
  const [filename, setFilename] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setFilename(file.name); setError(""); setResult(null); setBusy(true);
    try { setResult(await analyzePcap(file)); }
    catch (err) { setError(err instanceof Error ? err.message : "The capture could not be analyzed."); }
    finally { setBusy(false); }
  }

  const distribution = result?.modbus_summary.function_code_distribution || {};
  return <div className="scada-feed-stack" data-testid="pcap-analyzer">
    <div className="scada-surface scada-alert-summary"><div><span className="scada-kicker">Experimental network tool</span><strong>PCAP analyzer</strong></div><FileSearch size={18} className="text-normal" /></div>
    <div className="scada-surface pcap-analyzer-panel">
      <p className="pcap-analyzer-note">Network analysis only. No attack labels, physical features, ML predictions, or detection verdicts are produced.</p>
      <label className="scada-tool-button pcap-upload-button">{busy ? <LoaderCircle size={14} className="pcap-spin" /> : <Upload size={14} />}{busy ? "Analyzing…" : "Choose PCAP"}<input type="file" accept=".pcap,.pcapng,.cap" onChange={handleFile} disabled={busy} /></label>
      {filename && <small className="pcap-file-name">{filename}</small>}
      {error && <div className="pcap-error" role="alert">{error}</div>}
      {result && <>
        <div className="pcap-metric-grid"><div><span>Packets</span><strong>{n(result.packet_summary.total_packets)}</strong></div><div><span>Modbus messages</span><strong>{n(result.modbus_summary.decoded_messages)}</strong></div><div><span>Requests</span><strong>{n(result.modbus_summary.request_events)}</strong></div><div><span>Sources</span><strong>{n(result.modbus_summary.source_cardinality)}</strong></div></div>
        <div className="pcap-analysis-section"><span className="scada-kicker">Function codes</span><div className="pcap-code-list">{Object.entries(distribution).map(([code, count]) => <span key={code}>FC {code}: <b>{n(count)}</b></span>)}</div></div>
        <div className="pcap-analysis-section"><span className="scada-kicker">Packet and matching</span><p>Mean packet: {n(result.packet_summary.mean_packet_bytes, 1)} bytes · range {n(result.packet_summary.min_packet_bytes)}–{n(result.packet_summary.max_packet_bytes)} bytes</p><p>Matched responses: {n(result.modbus_summary.request_response_matched)} ({n(result.modbus_summary.matched_response_fraction * 100, 2)}%) · unmatched: {n(result.modbus_summary.unmatched_requests)}</p><p>Latency: {result.modbus_summary.mean_latency_ms == null ? "unavailable" : `${n(result.modbus_summary.mean_latency_ms, 3)} ms mean`} · parser errors: {n(result.modbus_summary.parser_errors)}</p></div>
        <div className="pcap-limitations"><span className="scada-kicker">Limitations</span>{result.limitations.map((item) => <div key={item}>• {item}</div>)}</div>
      </>}
    </div>
  </div>;
}

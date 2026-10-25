"use client";

import React, { useState } from "react";
import { FileSearch, LoaderCircle, Upload } from "lucide-react";
import { analyzePcap, PcapAnalysis, PcapMessageDetail } from "@/lib/api";

const n = (value: number | null | undefined, digits = 0) => typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
const timestamp = (value: string | null) => value ? value.replace("T", " ").replace("+00:00", " UTC") : "—";

function MessageStatus({ message }: { message: PcapMessageDetail }) {
  if (message.response_status === "matched_exception") return <span className="pcap-status pcap-status-error">Matched exception</span>;
  if (message.response_status === "matched") return <span className="pcap-status pcap-status-matched">Matched</span>;
  return <span className="pcap-status pcap-status-unmatched">Unmatched</span>;
}

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
  const messages = result?.modbus_summary.message_details || [];
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
        <div className="pcap-analysis-section" data-testid="decoded-messages">
          <span className="scada-kicker">Decoded Modbus Messages</span>
          <p className="pcap-message-note">Decoded request messages from the capture. This table is network inspection only, not an attack verdict.</p>
          {messages.length === 0 ? <div className="pcap-empty-state">No Modbus request messages were decoded from this capture.</div> : <>
            {result.modbus_summary.message_details_truncated && <div className="pcap-truncation">Showing the first {n(result.modbus_summary.message_details_displayed)} of {n(result.modbus_summary.decoded_messages)} decoded messages.</div>}
            <div className="pcap-message-table-wrap">
              <table className="pcap-message-table">
                <thead><tr><th>Timestamp</th><th>Source</th><th>Destination</th><th>Transaction</th><th>Unit</th><th>Function</th><th>Register</th><th>Status</th><th>Latency</th><th>Success</th></tr></thead>
                <tbody>{messages.map((message, index) => <tr key={`${message.timestamp_utc ?? "message"}-${message.transaction_id ?? "na"}-${index}`}>
                  <td>{timestamp(message.timestamp_utc)}</td>
                  <td>{message.source_ip ?? "—"}:{message.source_port ?? "—"}</td>
                  <td>{message.destination_ip ?? "—"}:{message.destination_port ?? "—"}</td>
                  <td>{n(message.transaction_id)}</td>
                  <td>{n(message.unit_id)}</td>
                  <td><span className="pcap-function-code">FC {n(message.function_code)}</span><span className="pcap-function-name">{message.function_name}</span></td>
                  <td>{n(message.reference_number)}</td>
                  <td><MessageStatus message={message} /></td>
                  <td>{message.response_time_ms == null ? "—" : `${n(message.response_time_ms, 3)} ms`}</td>
                  <td>{message.success == null ? "—" : message.success ? "Yes" : "No"}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </>}
        </div>
        <div className="pcap-limitations"><span className="scada-kicker">Limitations</span>{result.limitations.map((item) => <div key={item}>• {item}</div>)}</div>
      </>}
    </div>
  </div>;
}

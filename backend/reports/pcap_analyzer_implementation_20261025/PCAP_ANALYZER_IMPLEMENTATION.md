# Standalone PCAP Analyzer implementation

Date: 2026-10-25
Scope: isolated website network-analysis tool; no production ML behavior changed.

## What changed

The website now has a `PCAP tool` sidebar tab. A user can select a `.pcap`, `.pcapng`, or `.cap` file and view:

- packet count and packet-size summary;
- decoded Modbus message and request counts;
- Modbus function-code distribution;
- source cardinality;
- request/response matching and latency when the adapter can match them;
- unmatched requests, parser errors, and limitations.

The UI explicitly identifies the feature as network analysis only. It never displays attack labels, physical-system features, ML predictions, or detection verdicts.

## Backend boundary and safety

Endpoint: `POST /tools/pcap-analyzer`

The browser sends raw file bytes with the original name in `X-PCAP-Filename`. This avoids adding a multipart parser dependency to the current environment. The endpoint:

- accepts only `.pcap`, `.pcapng`, and `.cap` suffixes;
- rejects files above 128 MiB;
- limits processing to 2,000,000 packets and 30 seconds;
- writes only to a temporary file;
- analyzes through the existing `backend/scripts/adapt_modbus_pcap.py` logic;
- removes the temporary file in a `finally` block on success, parse failure, limit failure, or read failure;
- never calls the production classifier or persists uploaded captures.

The adapter was extended to read common pcapng section/interface/enhanced-packet blocks while retaining its classic-PCAP path. Existing parsing logic remains the single source of packet/Modbus decoding; the website analyzer only aggregates bounded summaries. Unmatched requests are included for function-code accounting but remain clearly separate from matched latency/error metrics.

## Changed files

- `backend/scripts/adapt_modbus_pcap.py` — pcapng support and optional unmatched-event emission.
- `backend/scripts/__init__.py` — experimental script package marker.
- `backend/app/pcap_analyzer.py` — bounded analyzer aggregation service.
- `backend/app/main.py` — isolated upload endpoint and CORS header allowance.
- `backend/tests/test_pcap_analyzer.py` — parser, pcapng, limits, invalid input, cleanup, and endpoint tests.
- `frontend/components/PcapAnalyzer.tsx` — analyzer UI.
- `frontend/lib/api.ts` — raw upload client and response types.
- `frontend/app/page.tsx` — new sidebar tab.
- `frontend/app/globals.css` — analyzer styles.

## Verification

Focused backend tests:

```text
11 passed
```

Frontend production build:

```text
npm run build
✓ Compiled successfully
✓ Type checking passed
✓ Static generation completed
```

The existing production model checksum remains unchanged:

```text
backend/models/fusion_classifier.joblib
EE5211510E41EDDAC32ED1EED405AF982A0A550BD0B75E8867253135B812CCAE
```

## Local run instructions

Start the backend from `backend/` using the project environment, then start the frontend from `frontend/`:

```powershell
cd "C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\backend"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

cd "C:\Users\K Srisai Kedar\OneDrive\Documents\Projects\GridSentinel - SIH\gridsentinel\frontend"
npm run dev
```

Open `http://localhost:3000`, select `PCAP tool`, and choose a supported capture. The upload is analyzed in memory via a temporary file and is not retained by the application.

## Remaining before deployment

This feature is experimental and should not be presented as an intrusion detector. Before deployment, confirm the operational upload policy, reverse-proxy body/time limits, authentication/authorization requirements, and resource isolation for untrusted captures. The two Dataset 1 captures previously identified with unreliable request/response pairing remain subject to the adapter’s reported limitations; this UI does not conceal or repair that limitation.

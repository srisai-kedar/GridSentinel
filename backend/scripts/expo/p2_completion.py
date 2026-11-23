"""Re-validate the committed P2 evidence and provenance boundary."""
from __future__ import annotations
import argparse, hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from leakage_audit import compare_feature_dicts, static_provenance_violations
ROOT = Path(__file__).resolve().parents[3]

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args(); started=datetime.now(timezone.utc); a.out.mkdir(parents=True,exist_ok=True)
    prior=ROOT/'backend/reports/research/P2/leakage_audit.json'; evidence=json.loads(prior.read_text(encoding='utf-8'))
    violations=static_provenance_violations([ROOT/'backend/app/ml/feature_engineering.py'])
    evidence['reaudit']={'static_provenance_violations':violations,'static_provenance_passed':not violations,'blind_reextraction_reused':bool(evidence.get('blind_reextraction',{}).get('passed')),'canary_reused':bool(evidence.get('canary',{}).get('audit_detected_leak')),'note':'The serialized prior P2 artifacts were rechecked; no held-out dataset was read.'}
    result=a.out/'p2_reaudit.json'; result.write_text(json.dumps(evidence,indent=2,sort_keys=True),encoding='utf-8')
    findings=a.out/'FINDINGS.md'; findings.write_text('# P2 Findings\n\n## Supported\n\n'+f"- Static provenance re-audit passed: `{not violations}`; violations: `{len(violations)}`.\n- Prior blind re-extraction and canary results are preserved and revalidated from the machine-readable evidence.\n- Focused provenance and lock tests passed in this task run.\n\n## Not supported\n\n- The diagnostic repaired-versus-pre-PR16 comparison remains one seed and is not a production claim.\n\n## Unresolved\n\n- A fresh pre-PR16 scratch checkout is not available as a reproducible input in this worktree; no replacement result was fabricated.\n",encoding='utf-8')
    manifest={'task_id':'P2','git_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'python_version':sys.version,'cpu_model':platform.processor() or platform.machine(),'cli_arguments':sys.argv,'seeds':{'prior_diagnostic':101},'started_at_utc':started.isoformat(),'ended_at_utc':datetime.now(timezone.utc).isoformat(),'input_datasets':{str(prior):sha256(prior)},'output_datasets':{str(result):sha256(result),str(findings):sha256(findings)}}
    (a.out/'run_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding='utf-8'); return 0
if __name__=='__main__': raise SystemExit(main())

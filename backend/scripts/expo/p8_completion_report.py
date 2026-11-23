"""Render P8 completion evidence and expose unmet exposure/benign coverage."""
from __future__ import annotations
import argparse, hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--alert-results',type=Path,required=True); ap.add_argument('--pilot-dir',type=Path,required=True); ap.add_argument('--out-dir',type=Path,required=True); a=ap.parse_args(); started=datetime.now(timezone.utc); a.out_dir.mkdir(parents=True,exist_ok=True)
    payload=json.loads(a.alert_results.read_text(encoding='utf-8')); files=sorted(a.pilot_dir.glob('*.csv')); frames=[pd.read_csv(p) for p in files]; pilot=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    benign={'load_step','authorized_control_write','planned_switching','communication_stall','load_step','authorized_write'}
    observed={str(k):int(v) for k,v in pilot.get('subtype_label',pd.Series(dtype=str)).value_counts().items()}
    summary={'task_id':'P8-completion','validation_alert_candidates':int(payload['candidate_count']),'selected_budgets':{str(k):bool(v) for k,v in payload['selected_by_budget'].items()},'pilot':{'files':len(files),'rows':int(len(pilot)),'run_ids':int(pilot['run_id'].nunique()) if 'run_id' in pilot else 0,'subtype_counts':observed,'requested_benign_subtypes':sorted(benign),'requested_benign_rows_observed':int(sum(v for k,v in observed.items() if k in benign)),'clean_hours':float(sum(float(x) for x in pilot.get('duration_hours',pd.Series(dtype=float)).drop_duplicates())) if 'duration_hours' in pilot else 0.0},'acceptance':{'24_real_clock_hours':False,'independent_clean_heldout_final_eval':False,'benign_event_coverage':False,'target_0_125_fa_per_hour_supported':False},'blocker':'The measured generator throughput is 1.465759 ticks/second; 86400 real-clock ticks are not feasible in this unattended run. The benign pilot generated no requested benign event subtypes.'}
    result=a.out_dir/'completion_results.json'; result.write_text(json.dumps(summary,indent=2,sort_keys=True),encoding='utf-8')
    report=a.out_dir/'FINDINGS.md'; report.write_text('# P8 Findings\n\n## Supported\n\n'+f"- Validation-only alert analysis executed `{summary['validation_alert_candidates']}` candidates with budgets 1, 5, and 20 events/hour. Machine results remain in `{a.alert_results}`.\n- The benign pilot completed `{summary['pilot']['files']}` runs and `{summary['pilot']['rows']}` rows; its observed subtype counts are machine-generated in `completion_results.json`.\n\n## Not supported\n\n- The required 24 real-clock clean validation hours were not completed.\n- No independent clean held-out dataset was evaluated through `scripts/eval_final.py`.\n- The benign pilot observed zero requested benign-event subtypes, so no benign-event robustness claim is supported.\n- The 0.125 false-alarm/hour target is not established; the existing short-exposure Poisson intervals remain too wide.\n\n## Unresolved\n\n- Human/runtime action: run `--ticks 86400 --sim-seconds-per-tick 1.0` with unique ports, then generate a disjoint held-out clean run and pass it once to `scripts/eval_final.py`.\n- Generate targeted or sufficiently long benign-event runs until each requested benign subtype is observed, preserving manifests and hashes.\n",encoding='utf-8')
    manifest={'task_id':'P8-completion','git_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[2],text=True).strip(),'python_version':sys.version,'cpu_model':platform.processor() or platform.machine(),'cli_arguments':sys.argv,'seeds':{'benign_pilot':list(range(800,804))},'started_at_utc':started.isoformat(),'ended_at_utc':datetime.now(timezone.utc).isoformat(),'input_datasets':{str(a.alert_results):sha256(a.alert_results),**{str(p):sha256(p) for p in files}},'output_datasets':{str(result):sha256(result),str(report):sha256(report)}}; (a.out_dir/'run_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding='utf-8'); return 0
if __name__=='__main__': raise SystemExit(main())

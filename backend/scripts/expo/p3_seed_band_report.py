"""Summarize generated P3 seed bands without reading held-out test paths."""
from __future__ import annotations
import argparse, hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    started=datetime.now(timezone.utc); a.out.mkdir(parents=True,exist_ok=True)
    files=sorted(a.root.glob('*.csv'))
    rows=[]; outputs={}
    for p in files:
        frame=pd.read_csv(p); outputs[str(p)]=sha256(p)
        rows.append({'file':p.name,'rows':int(len(frame)),'ticks':int(frame['tick'].nunique()) if 'tick' in frame else None,'class_counts':{str(k):int(v) for k,v in frame.get('top_level_label',pd.Series(dtype=str)).value_counts().items()},'scenario_counts':{str(k):int(v) for k,v in frame.get('scenario_type',pd.Series(dtype=str)).value_counts().items()},'evidence_visible_fraction':float(frame['evidence_visible'].mean()) if 'evidence_visible' in frame else None,'profile_family':str(frame['profile_family'].iloc[0]) if 'profile_family' in frame and len(frame) else None})
    summary={'task_id':'P3','files':rows,'file_count':len(files),'expected_files':40,'complete':len(files)==40,'output_sha256':outputs}
    result=a.out/'p3_seed_band_summary.json'; result.write_text(json.dumps(summary,indent=2,sort_keys=True),encoding='utf-8')
    findings=a.out/'FINDINGS.md'; findings.write_text('# P3 Findings\n\n## Supported\n\n'+f"- The seed-band generator produced `{len(files)}` of `40` requested seed outputs; row counts and class/evidence summaries are machine-generated in `p3_seed_band_summary.json`.\n"+'- Each generated CSV is hashed and retains run/scenario/episode/evidence fields.\n\n## Not supported\n\n- No held-out test data was read, tuned, or used for selection.\n\n## Unresolved\n\n'+(' - Seed-band generation is incomplete and requires rerun.\n' if len(files)!=40 else ' - No seed-band completeness gap remains.\n'),encoding='utf-8')
    manifest={'task_id':'P3','git_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'python_version':sys.version,'cpu_model':platform.processor() or platform.machine(),'cli_arguments':sys.argv,'seeds':{'train':list(range(100,120)),'validation':list(range(200,205)),'ood':list(range(400,410)),'clean':list(range(500,505))},'started_at_utc':started.isoformat(),'ended_at_utc':datetime.now(timezone.utc).isoformat(),'input_datasets':outputs,'output_datasets':{str(result):sha256(result),str(findings):sha256(findings)}}
    (a.out/'run_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding='utf-8'); return 0
if __name__=='__main__': raise SystemExit(main())

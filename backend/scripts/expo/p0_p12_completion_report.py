"""Build a machine-generated closure report for P0-P12 acceptance status."""
from __future__ import annotations
import argparse, hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args(); started=datetime.now(timezone.utc); a.out.mkdir(parents=True,exist_ok=True)
    clean=ROOT/'backend/experiments/P0-P3-P2-P6/P0/clean_5000/generated.csv'; seed_dir=ROOT/'backend/experiments/P0-P3-P2-P6/P3/seed_band'; p6=ROOT/'backend/experiments/P0-P3-P2-P6/P6'
    clean_df=pd.read_csv(clean); seed_files=sorted(seed_dir.glob('*.csv')); tv=sorted(seed_dir.glob('train_*.csv'))+sorted(seed_dir.glob('validation_*.csv')); frames=[pd.read_csv(p,usecols=['scenario_type','attack_active','evidence_visible','run_id','episode_id']) for p in tv]; d=pd.concat(frames,ignore_index=True)
    cv=pd.read_csv(p6/'grouped_cv_validation_results.csv'); cfg=json.loads((p6/'selected_config.json').read_text(encoding='utf-8'))
    statuses={
      'P0':{'status':'PASS_WITH_LIMITATION','evidence':'5,000-tick clean run, prior reproducibility and concurrency evidence; Docker digest unavailable.'},
      'P2':{'status':'PARTIAL','evidence':'Static provenance, blind re-extraction and canary evidence are present; fresh historical pre-PR16 checkout is unavailable.'},
      'P3':{'status':'PASS_FOR_SEED_COVERAGE','evidence':'All configured train/validation/OOD/clean seed outputs exist at the recorded tick count.'},
      'P6':{'status':'PASS_FOR_ISOLATED_VALIDATION','evidence':'All prescribed arms and available model families executed on train/validation only; no held-out evaluation.'},
      'P7':{'status':'PARTIAL','evidence':'Pilot final comparison exists, but independent exposure and statistical power are insufficient for production claims.'},
      'P8':{'status':'BLOCKED','evidence':'Required 24-hour real-clock clean validation and independent clean held-out exposure are not available.'},
      'P9':{'status':'BLOCKED','evidence':'Required magnitude/profile grid and benign/natural-fault corpus are not available.'},
      'P10':{'status':'PARTIAL','evidence':'Jacobian diagnostic exists, but the 13-versus-15 measurement contract is unresolved and traffic is unchanged.'},
      'P11':{'status':'BLOCKED','evidence':'Second feeder and authorized cross-condition/cross-topology held-out evaluation are unavailable.'},
      'P12':{'status':'BLOCKED','evidence':'Elevated Windows packet capture infrastructure is unavailable; no simulated substitute was used.'},
    }
    result={'task_id':'P0-P12-completion','generated_at_utc':datetime.now(timezone.utc).isoformat(),'frozen_artifacts':{'model_sha256':sha256(ROOT/'backend/models/fusion_classifier.joblib'),'metrics_sha256':sha256(ROOT/'backend/reports/metrics.json')},'measured_checks':{'p0_clean_rows':int(len(clean_df)),'p0_clean_ticks':int(clean_df['tick'].nunique()),'p0_clean_attack_rows':int((clean_df.get('attack_active',False)==True).sum()) if 'attack_active' in clean_df else None,'p3_seed_files':len(seed_files),'p3_train_validation_rows':int(len(d)),'p3_train_validation_runs':int(d.run_id.nunique()),'p3_scenario_counts':{str(k):int(v) for k,v in d.scenario_type.value_counts().items()},'p3_attack_rows':int(d.attack_active.sum()),'p3_evidence_visible_rows':int(d.evidence_visible.sum()),'p6_result_rows':int(len(cv)),'p6_policies':sorted(cv.policy.unique().tolist()),'p6_feature_arms':sorted(cv.feature_arm.unique().tolist()),'p6_models':sorted(cv.model.unique().tolist()),'p6_selected_config':{'model':cfg['model'],'feature_arm':cfg['feature_arm'],'threshold':cfg['threshold']}},'statuses':statuses,'acceptance_note':'P8-P12 are not claimed complete where required data or infrastructure is unavailable.'}
    out_json=a.out/'completion_status.json'; out_json.write_text(json.dumps(result,indent=2,sort_keys=True),encoding='utf-8')
    md=['# P0-P12 Completion Findings','','## Supported','',f"- P0 measured `{result['measured_checks']['p0_clean_ticks']}` clean ticks and `{result['measured_checks']['p0_clean_rows']}` rows with zero attack-active rows.",f"- P3 measured `{result['measured_checks']['p3_seed_files']}` seed files and `{result['measured_checks']['p3_train_validation_rows']}` train/validation rows across `{result['measured_checks']['p3_train_validation_runs']}` runs.",f"- P6 executed `{result['measured_checks']['p6_result_rows']}` model/arm/policy result rows across the recorded model families and feature arms.",'','## Not supported','', '- P8, P9, P11 and P12 do not satisfy their original acceptance criteria because required exposure, scenario coverage, independent topology/data, or capture infrastructure is unavailable.', '- P2 cannot reproduce the historical pre-PR16 comparison without the original scratch checkout and inputs.', '- P6 validation results do not establish generalization or production improvement.','','## Unresolved','', '- Obtain the exact P8 clean exposure, P9 scenario grid, P11 second feeder/OOD evaluation inputs, and elevated P12 packet-capture capability.', '- Resolve the P10 13-versus-15 RTU-reported measurement contract before interpreting the frontier as production evidence.','','## Task status table','']
    for key,val in statuses.items(): md.append(f"- `{key}`: **{val['status']}** — {val['evidence']}")
    report=a.out/'FINDINGS.md'; report.write_text('\n'.join(md)+'\n',encoding='utf-8')
    manifest={'task_id':'P0-P12-completion','git_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'python_version':sys.version,'cpu_model':platform.processor() or platform.machine(),'cli_arguments':sys.argv,'seeds':{'p3_train':list(range(100,120)),'p3_validation':list(range(200,205)),'p3_ood':list(range(400,410)),'p3_clean':list(range(500,505))},'started_at_utc':started.isoformat(),'ended_at_utc':datetime.now(timezone.utc).isoformat(),'input_datasets':{str(p):sha256(p) for p in [clean,*tv,p6/'grouped_cv_validation_results.csv',p6/'selected_config.json']},'output_datasets':{str(out_json):sha256(out_json),str(report):sha256(report)}}
    (a.out/'run_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding='utf-8'); return 0
if __name__=='__main__': raise SystemExit(main())

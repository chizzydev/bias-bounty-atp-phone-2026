#!/usr/bin/env python3
"""Run the frozen ATP-PHONE science from public raw inputs; NO score reconstruction.

Release adapter dynamically pins each parent manifest SHA after its stage completes.
Portability adapter; fresh Windows P0A–P0D-A rerun passed 2026-10-08.
Independent second-machine reproduction has not been claimed.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

STAGES=[
 ("P0A", "RUN_ATP_PHONE_P0A_SOURCE_VINTAGE_FREEZE.py", None),
 ("P0B", "RUN_ATP_PHONE_P0B_TRANSFER_DEFECT_SCREEN.py", "P0A"),
 ("P0C", "RUN_ATP_PHONE_P0C_MATCHED_CONTACTABILITY_DISPARITY.py", "P0B"),
 ("P0D-A", "RUN_ATP_PHONE_P0D_A_OPERATIONAL_IMPACT_FREEZE.py", "P0C")]

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda: f.read(1024*1024),b''): h.update(b)
 return h.hexdigest().upper()

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--work-dir',default='atp_run')
 ap.add_argument('--start',choices=['P0A','P0B','P0C','P0D-A'],default='P0A')
 args=ap.parse_args()
 wd=Path(args.work_dir).resolve();(wd/'inspections').mkdir(parents=True,exist_ok=True);(wd/'outputs').mkdir(exist_ok=True)
 env=os.environ.copy();env['ATP_PHONE_ROOT']=str(wd)
 stages=[]
 start=next(i for i,v in enumerate(STAGES) if v[0]==args.start)
 for name,filename,prev in STAGES[start:]:
  # All existing parent manifests must be pinned; P0D-A consumes BOTH P0B and P0C.
  required=[]
  if name=='P0B':required=['P0A']
  elif name=='P0C':required=['P0B']
  elif name=='P0D-A':required=['P0B','P0C']
  for parent in required:
   manifest=wd/'inspections'/('ATP-PHONE-'+parent+'-manifest.json')
   if not manifest.exists():raise SystemExit('MISSING_PARENT_MANIFEST: '+str(manifest))
   env['ATP_PHONE_'+parent+'_MANIFEST_SHA']=sha(manifest)
  print('RUN_STAGE='+name,flush=True)
  subprocess.run([sys.executable,'-u',str(Path(__file__).parent/'src'/filename)],env=env,check=True)
  mp=wd/'inspections'/('ATP-PHONE-'+name+'-manifest.json')
  if not mp.exists():raise SystemExit('MISSING_OUTPUT_MANIFEST '+str(mp))
  print('STAGE_FINISHED',name,'MANIFEST_SHA256',sha(mp),flush=True)
  stages.append(name)
 print('PIPELINE_FINISHED_STAGES='+','.join(stages),flush=True)
 print('CAUTION=Clean independent rerun certification requires verifying stage counts and all report claims.',flush=True)

if __name__=='__main__':main()

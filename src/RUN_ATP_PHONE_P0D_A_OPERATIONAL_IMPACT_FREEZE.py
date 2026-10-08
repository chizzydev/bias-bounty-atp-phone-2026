from __future__ import annotations
from pathlib import Path
import os
import hashlib, json, sys

import pandas as pd
import numpy as np

VERSION="ATP-PHONE-P0D-A-1.0"

ROOT = Path(os.environ.get("ATP_PHONE_ROOT", str(Path.cwd() / "atp_run"))).resolve()
OUT=ROOT/"outputs"
INSPECT=ROOT/"inspections"

P0C_MANIFEST=INSPECT/"ATP-PHONE-P0C-manifest.json"
P0C_MANIFEST_SHA=os.environ.get("ATP_PHONE_P0C_MANIFEST_SHA", "52A430EF79CDBA22E99C89B60B0855CBD1B1C4C8478A078D10864CE1F277C492")
P0B_MANIFEST=INSPECT/"ATP-PHONE-P0B-manifest.json"
P0B_MANIFEST_SHA=os.environ.get("ATP_PHONE_P0B_MANIFEST_SHA", "1FDD5B00179D45185DF6A97FD6F19354F93279882BE1B6AA6D5DDDEADE7E0740")

PREREG_NAME="ATP_PHONE_P0D_A_OPERATIONAL_IMPACT_PREREGISTRATION_v1.0.txt"
ROLE_NAME="ATP_PHONE_P0D_A_FROZEN_SERVICE_ROLE_TAXONOMY_v1.0.csv"
EXPECTED_PREREG="6A537A909BEEFB75DC74AC54B4B71CC4E54BDF819B66328CFC8D3824A0B5B759"
EXPECTED_ROLE="1E2BB41AE7C97EE4440C21AC27454927B7C3E882BE675F8763C41AFAA7F34870"

PRIMARY_REGIONS=("eastern-ok","maricopa-az","northern-ca","south-central-tx")

REPORT=INSPECT/"ATP-PHONE-P0D-A-operational-impact-report.txt"
ROLE_LOSSES_OUT=OUT/"ATP-PHONE-P0D-A-operational-role-losses.csv"
ROLE_MATCHED_OUT=OUT/"ATP-PHONE-P0D-A-operational-matched-results.csv"
FAMILY_SUMMARY_OUT=INSPECT/"ATP-PHONE-P0D-A-family-summary.csv"
REGION_SUMMARY_OUT=INSPECT/"ATP-PHONE-P0D-A-region-summary.csv"
ANCHORS_OUT=OUT/"ATP-PHONE-P0D-A-frozen-named-anchors.csv"
MANIFEST=INSPECT/"ATP-PHONE-P0D-A-manifest.json"

def emit(s=""):
    print(str(s),flush=True)
    with REPORT.open("a",encoding="utf-8") as f:
        f.write(str(s)+"\n")

def sha(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest().upper()

def fail(msg,status="FAIL"):
    emit(f"ATP_PHONE_P0D_A={status}")
    emit("ATP_PHONE_P0D_B_AUTHORIZED=NO")
    emit(f"FAIL_REASON={msg}")
    raise RuntimeError(msg)

def verify_manifest(path:Path, expected_hash:str, label:str):
    if not path.exists():
        fail(f"missing {label}: {path}")
    actual=sha(path)
    emit(f"{label}={path}|SHA256={actual}")
    if actual!=expected_hash:
        fail(f"{label} hash mismatch expected={expected_hash} actual={actual}")
    m=json.loads(path.read_text(encoding="utf-8"))
    for name,meta in m.get("outputs",{}).items():
        p=Path(meta["path"])
        if not p.exists():
            fail(f"missing parent output {name}: {p}")
        if sha(p)!=meta["sha256"]:
            fail(f"parent output hash mismatch: {name}")
    return m

def anchor_hash(rid,gid):
    return hashlib.sha256(
        f"ATP_PHONE_P0D_A_ANCHOR_v1|{rid}|{gid}".encode("utf-8")
    ).hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    INSPECT.mkdir(parents=True,exist_ok=True)
    for p in (REPORT,ROLE_LOSSES_OUT,ROLE_MATCHED_OUT,FAMILY_SUMMARY_OUT,
              REGION_SUMMARY_OUT,ANCHORS_OUT,MANIFEST):
        p.unlink(missing_ok=True)

    emit("===== ATP-PHONE-P0D-A — OPERATIONAL SERVICE-ROLE IMPACT FREEZE =====")
    emit(f"VERSION={VERSION}|PYTHON={sys.version.split()[0]}")

    pkg=Path(__file__).resolve().parent
    prereg=pkg/PREREG_NAME
    roles_path=pkg/ROLE_NAME
    if not prereg.exists() or not roles_path.exists():
        fail("package preregistration or frozen role taxonomy missing")
    emit(f"PREREGISTRATION={prereg}|SHA256={sha(prereg)}")
    emit(f"ROLE_TAXONOMY={roles_path}|SHA256={sha(roles_path)}")
    if sha(prereg)!=EXPECTED_PREREG:
        fail("preregistration hash mismatch")
    if sha(roles_path)!=EXPECTED_ROLE:
        fail("role-taxonomy hash mismatch")

    p0b=verify_manifest(P0B_MANIFEST,P0B_MANIFEST_SHA,"P0B_MANIFEST")
    p0c=verify_manifest(P0C_MANIFEST,P0C_MANIFEST_SHA,"P0C_MANIFEST")

    if not p0c.get("overall_pass") or not p0c.get("p0d_authorized"):
        fail("P0C does not authorize P0D")

    roles=pd.read_csv(roles_path,dtype=str)
    if roles["primary_category"].duplicated().any():
        fail("frozen taxonomy contains duplicate category assignment")
    role_map=dict(zip(roles["primary_category"],roles["service_family"]))

    exp_path=Path(p0c["outputs"]["ATP-PHONE-P0C-exposed-preoutcome-metadata.csv"]["path"])
    matched_path=Path(p0c["outputs"]["ATP-PHONE-P0C-matched-results.csv"]["path"])
    burden_path=Path(p0c["outputs"]["ATP-PHONE-P0C-tract-burden.csv"]["path"])
    p0b_phone_path=Path(p0b["outputs"]["ATP-PHONE-P0B-frozen-source-phone-universe.csv"]["path"])

    exp=pd.read_csv(exp_path,dtype={"GEOID":str,"gers_id":str,"record_id":str,"region":str})
    matched=pd.read_csv(matched_path,dtype={"GEOID":str,"gers_id":str,"record_id":str,"region":str})
    burden=pd.read_csv(burden_path,dtype={"GEOID":str,"region":str})
    src=pd.read_csv(p0b_phone_path,dtype={"GEOID":str,"gers_id":str,"record_id":str,"region":str})

    for df in (exp,matched,burden,src):
        if "GEOID" in df.columns:
            df["GEOID"]=df["GEOID"].astype(str).str.zfill(11)

    # Full parent loss cohort operational roles.
    op=exp[exp["region"].isin(PRIMARY_REGIONS)].copy()
    op["service_family"]=op["primary_category"].map(role_map)
    op=op[op["service_family"].notna()].copy()

    # attach frozen source name/brand/URI and tract burden
    src_keep=[c for c in ["record_id","gers_id","name","brand","source_uri"] if c in src.columns]
    op=op.merge(
        src[src_keep].drop_duplicates(subset=["record_id","gers_id"]),
        on=["record_id","gers_id"],how="left",validate="one_to_one"
    )
    burden_keep=["region","GEOID","total_pois","ATP_phone_loss_count","loss_burden_share"]
    op=op.merge(
        burden[burden_keep],
        on=["region","GEOID"],how="left",validate="many_to_one"
    )
    op.to_csv(ROLE_LOSSES_OUT,index=False)

    fam=(
        op.groupby("service_family",as_index=False)
        .agg(
            losses=("record_id","size"),
            tracts=("GEOID","nunique"),
            regions=("region","nunique"),
            categories=("primary_category","nunique"),
        )
    )
    fam.to_csv(FAMILY_SUMMARY_OUT,index=False)

    role_support=(
        len(op)>=250
        and op["GEOID"].nunique()>=100
        and op["region"].nunique()==4
        and int((fam["losses"]>=50).sum())>=2
        and op["primary_category"].nunique()>=8
    )

    emit()
    emit("===== FULL LOSS-COHORT OPERATIONAL ROLE SUPPORT =====")
    emit(f"OPERATIONAL_ROLE_LOSSES={len(op)}")
    emit(f"OPERATIONAL_ROLE_TRACTS={op['GEOID'].nunique()}")
    emit(f"OPERATIONAL_ROLE_REGIONS={op['region'].nunique()}/4")
    emit(f"OPERATIONAL_ROLE_CATEGORIES={op['primary_category'].nunique()}")
    emit(f"ROLE_FAMILIES_GE_50_LOSSES={int((fam['losses']>=50).sum())}/3")
    for r in fam.itertuples(index=False):
        emit(
            f"FAMILY={r.service_family}|losses={r.losses}|tracts={r.tracts}|"
            f"regions={r.regions}|categories={r.categories}"
        )

    # Already-frozen P0C matched pairs only. Never rematch.
    rm=matched[matched["region"].isin(PRIMARY_REGIONS)].copy()
    rm["service_family"]=rm["primary_category"].map(role_map)
    rm=rm[rm["service_family"].notna()].copy()
    rm.to_csv(ROLE_MATCHED_OUT,index=False)

    if len(rm):
        overall_ctl=float(rm["control_has_valid_native_phone"].astype(bool).mean())
        overall_exp=float(rm["exposed_has_valid_native_phone"].astype(bool).mean())
        rd=overall_ctl-overall_exp
        control_n=int(rm["control_has_valid_native_phone"].astype(bool).sum())
        reg=(
            rm.groupby("region",as_index=False)
            .agg(
                matched_pairs=("gers_id","size"),
                tracts=("GEOID","nunique"),
                categories=("primary_category","nunique"),
                control_phone_rate=("control_has_valid_native_phone","mean"),
                exposed_phone_rate=("exposed_has_valid_native_phone","mean"),
                controls_with_phone=("control_has_valid_native_phone","sum"),
            )
        )
        reg["risk_difference"]=reg["control_phone_rate"]-reg["exposed_phone_rate"]
    else:
        overall_ctl=overall_exp=rd=0.0
        control_n=0
        reg=pd.DataFrame(columns=["region","matched_pairs","tracts","categories",
                                  "control_phone_rate","exposed_phone_rate",
                                  "controls_with_phone","risk_difference"])
    reg.to_csv(REGION_SUMMARY_OUT,index=False)

    matched_support=(
        len(rm)>=200
        and rm["GEOID"].nunique()>=100
        and rm["region"].nunique()>=3
        and rm["primary_category"].nunique()>=5
    )
    severity=(
        overall_ctl>=0.80
        and int((reg["control_phone_rate"]>=0.70).sum())>=3
        and control_n>=160
    )

    emit()
    emit("===== FROZEN MATCHED OPERATIONAL CONTACTABILITY =====")
    emit(f"OPERATIONAL_MATCHED_PAIRS={len(rm)}")
    emit(f"OPERATIONAL_MATCHED_TRACTS={rm['GEOID'].nunique() if len(rm) else 0}")
    emit(f"OPERATIONAL_MATCHED_REGIONS={rm['region'].nunique() if len(rm) else 0}")
    emit(f"OPERATIONAL_MATCHED_CATEGORIES={rm['primary_category'].nunique() if len(rm) else 0}")
    emit(f"OPERATIONAL_EXPOSED_PHONE_RATE={overall_exp:.9f}")
    emit(f"OPERATIONAL_CONTROL_PHONE_RATE={overall_ctl:.9f}")
    emit(f"OPERATIONAL_MATCHED_RD={rd:+.9f}")
    emit(f"OPERATIONAL_CONTROLS_WITH_PHONE={control_n}")
    emit(f"REGIONS_CONTROL_RATE_GE_0.70={int((reg['control_phone_rate']>=0.70).sum())}/4")
    for r in reg.itertuples(index=False):
        emit(
            f"REGION={r.region}|pairs={r.matched_pairs}|tracts={r.tracts}|"
            f"categories={r.categories}|exposed={r.exposed_phone_rate:.9f}|"
            f"control={r.control_phone_rate:.9f}|rd={r.risk_difference:+.9f}|"
            f"control_phone_n={int(r.controls_with_phone)}"
        )

    # Mechanical anchors.
    op["anchor_hash"]=[
        anchor_hash(rid,gid) for rid,gid in zip(op["record_id"],op["gers_id"])
    ]
    named=op[op["name"].fillna("").astype(str).str.strip().ne("")].copy()
    named=named.sort_values(
        ["region","loss_burden_share","ATP_phone_loss_count","anchor_hash"],
        ascending=[True,False,False,True],
        kind="mergesort"
    )
    anchors=[]
    for region in PRIMARY_REGIONS:
        sub=named[named["region"]==region]
        used=set()
        for row in sub.itertuples(index=False):
            if row.GEOID in used:
                continue
            anchors.append(row._asdict())
            used.add(row.GEOID)
            if len(used)>=3:
                break
    anchor=pd.DataFrame(anchors)
    anchor.to_csv(ANCHORS_OUT,index=False)
    anchor_regions=anchor["region"].nunique() if len(anchor) else 0
    anchor_gate=(len(anchor)>=8 and anchor_regions==4)

    emit()
    emit("===== MECHANICAL NAMED OPERATIONAL ANCHORS =====")
    emit(f"FROZEN_OPERATIONAL_ANCHORS={len(anchor)}")
    emit(f"ANCHOR_REGIONS={anchor_regions}/4")
    if len(anchor):
        for r in anchor.itertuples(index=False):
            emit(
                f"ANCHOR={r.region}|GEOID={r.GEOID}|family={r.service_family}|"
                f"category={r.primary_category}|name={r.name}|brand={r.brand}|"
                f"tract_burden={r.loss_burden_share:.9f}"
            )

    parent_integrity=True
    role_integrity=True
    overall=all([parent_integrity,role_integrity,role_support,matched_support,severity,anchor_gate])

    emit()
    emit("===== P0D-A FROZEN GATES =====")
    emit(f"GATE_A_PARENT_INTEGRITY={'PASS' if parent_integrity else 'FAIL'}")
    emit(f"GATE_B_ROLE_TAXONOMY_INTEGRITY={'PASS' if role_integrity else 'FAIL'}")
    emit(f"GATE_C_OPERATIONAL_ROLE_SUPPORT={'PASS' if role_support else 'FAIL'}")
    emit(f"GATE_D_MATCHED_OPERATIONAL_SUPPORT={'PASS' if matched_support else 'FAIL'}")
    emit(f"GATE_E_OPERATIONAL_CONTACTABILITY_SEVERITY={'PASS' if severity else 'FAIL'}")
    emit(f"GATE_F_MECHANICAL_NAMED_ANCHORS={'PASS' if anchor_gate else 'FAIL'}")

    manifest={
        "version":VERSION,
        "parent_p0b_manifest_sha256":P0B_MANIFEST_SHA,
        "parent_p0c_manifest_sha256":P0C_MANIFEST_SHA,
        "role_taxonomy_sha256":EXPECTED_ROLE,
        "operational_losses":int(len(op)),
        "operational_tracts":int(op["GEOID"].nunique()),
        "operational_categories":int(op["primary_category"].nunique()),
        "operational_matched_pairs":int(len(rm)),
        "operational_control_phone_rate":float(overall_ctl),
        "operational_exposed_phone_rate":float(overall_exp),
        "operational_rd":float(rd),
        "operational_controls_with_phone":int(control_n),
        "frozen_anchor_count":int(len(anchor)),
        "gates":{
            "parent_integrity":parent_integrity,
            "role_taxonomy_integrity":role_integrity,
            "operational_role_support":role_support,
            "matched_operational_support":matched_support,
            "operational_contactability_severity":severity,
            "mechanical_named_anchors":anchor_gate,
        },
        "overall_pass":bool(overall),
        "p0d_b_authorized":bool(overall),
        "submission_authorized":False,
        "outputs":{},
    }
    for p in (ROLE_LOSSES_OUT,ROLE_MATCHED_OUT,FAMILY_SUMMARY_OUT,
              REGION_SUMMARY_OUT,ANCHORS_OUT):
        manifest["outputs"][p.name]={
            "path":str(p),"sha256":sha(p),"bytes":p.stat().st_size
        }
    MANIFEST.write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding="utf-8")

    emit()
    emit(f"ROLE_LOSSES={ROLE_LOSSES_OUT}|SHA256={sha(ROLE_LOSSES_OUT)}")
    emit(f"ROLE_MATCHED={ROLE_MATCHED_OUT}|SHA256={sha(ROLE_MATCHED_OUT)}")
    emit(f"FAMILY_SUMMARY={FAMILY_SUMMARY_OUT}|SHA256={sha(FAMILY_SUMMARY_OUT)}")
    emit(f"REGION_SUMMARY={REGION_SUMMARY_OUT}|SHA256={sha(REGION_SUMMARY_OUT)}")
    emit(f"FROZEN_ANCHORS={ANCHORS_OUT}|SHA256={sha(ANCHORS_OUT)}")
    emit(f"MANIFEST={MANIFEST}|SHA256={sha(MANIFEST)}")
    emit("SUBMISSION_AUTHORIZED=NO")

    if overall:
        emit("ATP_PHONE_P0D_A=PASS")
        emit("ATP_PHONE_P0D_B_AUTHORIZED=YES")
        emit(
            "NEXT=P0D-B INDEPENDENT FROZEN-ANCHOR SOURCE/CURRENTNESS VALIDATION + "
            "DIRECT LIVE-ZINDI DUPLICATION AUTOPSY."
        )
    else:
        emit("ATP_PHONE_P0D_A=FAIL")
        emit("ATP_PHONE_P0D_B_AUTHORIZED=NO")
        emit("NEXT=STOP. NO CATEGORY/ROLE/ANCHOR RESCUE.")

if __name__=="__main__":
    main()

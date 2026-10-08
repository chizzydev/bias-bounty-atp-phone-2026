from __future__ import annotations
from pathlib import Path
import os
import hashlib, json, re, sys
import duckdb
import numpy as np
import pandas as pd

VERSION="ATP-PHONE-P0C-1.0"
ROOT = Path(os.environ.get("ATP_PHONE_ROOT", str(Path.cwd() / "atp_run"))).resolve()
OUT=ROOT/"outputs"
INSPECT=ROOT/"inspections"

P0B_MANIFEST=INSPECT/"ATP-PHONE-P0B-manifest.json"
P0B_MANIFEST_SHA=os.environ.get("ATP_PHONE_P0B_MANIFEST_SHA", "1FDD5B00179D45185DF6A97FD6F19354F93279882BE1B6AA6D5DDDEADE7E0740")

PRIMARY_REGIONS=("eastern-ok","maricopa-az","northern-ca","south-central-tx")
SUPPLEMENTAL_REGIONS=("eastern-wa",)
ALL_REGIONS=PRIMARY_REGIONS+SUPPLEMENTAL_REGIONS

CHALLENGE_BASE="s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"

PREREG_NAME="ATP_PHONE_P0C_MATCHED_CONTACTABILITY_PREREGISTRATION_v1.0.txt"
EXPECTED_PREREG_SHA="D94A8841A13F4EDF35FE856CAB432C7420BE207C600846971F9FEAB212C46D3A"

MIN_MATCHED_PAIRS=1000
MIN_MATCHED_TRACTS=100
MIN_MATCHED_REGIONS=3
MIN_MATCHED_CATEGORIES=10
MIN_RD=0.20
MIN_REGION_RD=0.15
MIN_REGIONS_RD=3
MIN_CONTROL_WITH_PHONE=200

REPORT=INSPECT/"ATP-PHONE-P0C-matched-contactability-report.txt"
EXPOSED_META_OUT=OUT/"ATP-PHONE-P0C-exposed-preoutcome-metadata.csv"
CONTROL_POOL_OUT=OUT/"ATP-PHONE-P0C-control-pool-preoutcome.csv"
PAIR_OUT=OUT/"ATP-PHONE-P0C-frozen-matched-pairs.csv"
RESULT_OUT=OUT/"ATP-PHONE-P0C-matched-results.csv"
REGION_OUT=INSPECT/"ATP-PHONE-P0C-region-summary.csv"
TRACT_OUT=OUT/"ATP-PHONE-P0C-tract-burden.csv"
ANCHOR_OUT=OUT/"ATP-PHONE-P0C-mechanical-tract-anchors.csv"
SVI_OUT=INSPECT/"ATP-PHONE-P0C-secondary-svi-summary.csv"
MANIFEST=INSPECT/"ATP-PHONE-P0C-manifest.json"

def emit(s=""):
    print(str(s),flush=True)
    with REPORT.open("a",encoding="utf-8") as f:
        f.write(str(s)+"\n")

def sha256_file(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest().upper()

def clean(v):
    if v is None: return ""
    try:
        if pd.isna(v): return ""
    except Exception:
        pass
    return str(v).strip()

def q(v): return str(v).replace("'","''")
def qi(v): return '"' + str(v).replace('"','""') + '"'

def fail(msg):
    emit("ATP_PHONE_P0C=FAIL")
    emit("ATP_PHONE_P0D_AUTHORIZED=NO")
    emit("FAIL_REASON="+str(msg))
    raise RuntimeError(msg)

def hh(prefix,gid):
    return hashlib.sha256(f"{prefix}|{gid}".encode()).hexdigest()

def remove_extension(s):
    return re.sub(r"(?i)\s*(?:ext(?:ension)?\.?|x)\s*[:.]?\s*\d+\s*$","",s.strip())

def split_phone_values(v):
    if v is None: return []
    s=str(v).strip()
    return [x.strip() for x in s.split(";") if x.strip()] if s else []

def canon_one(v):
    if v is None: return None
    digits=re.sub(r"\D","",remove_extension(str(v)))
    if len(digits)==11 and digits.startswith("1"): digits=digits[1:]
    return digits if len(digits)==10 else None

def recursive_scalars(obj):
    if obj is None: return
    if isinstance(obj,dict):
        for v in obj.values(): yield from recursive_scalars(v)
    elif isinstance(obj,(list,tuple)):
        for v in obj: yield from recursive_scalars(v)
    elif isinstance(obj,(str,int,float)):
        yield obj

def parse_native_phone(raw_json):
    raw=clean(raw_json)
    if not raw or raw.lower() in ("null","nan","none","[]","{}"): return [],[]
    try: obj=json.loads(raw)
    except Exception: obj=raw
    scalars=[str(x).strip() for x in recursive_scalars(obj) if str(x).strip()]
    cans=[]
    for s in scalars:
        for part in split_phone_values(s):
            c=canon_one(part)
            if c and c not in cans: cans.append(c)
    return scalars,cans

def setup():
    con=duckdb.connect(database=":memory:")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("SET s3_region='us-west-2'")
    con.execute("SET s3_url_style='path'")
    con.execute("SET threads TO 2")
    con.execute("SET memory_limit='4GB'")
    return con

def load_parent():
    if not P0B_MANIFEST.exists(): fail(f"missing P0B manifest {P0B_MANIFEST}")
    actual=sha256_file(P0B_MANIFEST)
    emit(f"P0B_MANIFEST={P0B_MANIFEST}|SHA256={actual}")
    if actual!=P0B_MANIFEST_SHA:
        fail(f"P0B manifest hash mismatch expected={P0B_MANIFEST_SHA} actual={actual}")
    m=json.loads(P0B_MANIFEST.read_text(encoding="utf-8"))
    if not m.get("overall_pass") or not m.get("p0c_authorized"):
        fail("P0B does not authorize P0C")
    if m.get("demographic_or_category_outcomes_read") is not False:
        fail("P0B did not preserve category/demographic outcome blindness")
    for name,meta in m.get("outputs",{}).items():
        p=Path(meta["path"])
        if not p.exists(): fail(f"missing P0B output {name}: {p}")
        h=sha256_file(p)
        if h!=meta["sha256"]:
            fail(f"P0B output hash mismatch {name} expected={meta['sha256']} actual={h}")
    return m

def status_bin(v):
    s=clean(v).lower()
    if s=="open": return "OPEN"
    if s=="permanently_closed": return "CLOSED"
    return "OTHER"

def source_bin(v):
    try: n=int(v)
    except Exception: n=0
    return "ONE" if n<=1 else "MULTI"

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    INSPECT.mkdir(parents=True,exist_ok=True)
    for p in (REPORT,EXPOSED_META_OUT,CONTROL_POOL_OUT,PAIR_OUT,RESULT_OUT,REGION_OUT,TRACT_OUT,ANCHOR_OUT,SVI_OUT,MANIFEST):
        p.unlink(missing_ok=True)

    emit("===== ATP-PHONE-P0C — MATCHED NATIVE-CONTACTABILITY DISPARITY =====")
    emit(f"VERSION={VERSION}|PYTHON={sys.version.split()[0]}|DUCKDB={duckdb.__version__}")
    emit("PRIMARY_REGIONS="+",".join(PRIMARY_REGIONS))
    emit("SUPPLEMENTAL_REGIONS="+",".join(SUPPLEMENTAL_REGIONS))
    emit("CONTROL_PHONE_OUTCOME_READ=NO")
    emit("MATCHED_PAIR_TABLE_FROZEN=NO")
    emit("SVI_OUTCOME_READ=NO")
    emit()

    prereg=Path(__file__).resolve().parent/PREREG_NAME
    ph=sha256_file(prereg)
    emit(f"PREREGISTRATION={prereg}|SHA256={ph}")
    if ph!=EXPECTED_PREREG_SHA: fail(f"prereg hash mismatch expected={EXPECTED_PREREG_SHA} actual={ph}")

    parent=load_parent()
    rp=Path(parent["outputs"]["ATP-PHONE-P0B-transfer-results.csv"]["path"])
    p0b=pd.read_csv(rp,dtype={"record_id":str,"gers_id":str,"GEOID":str,"region":str})
    p0b["GEOID"]=p0b["GEOID"].astype(str).str.zfill(11)
    sc=p0b["transfer_status"].astype(str).value_counts().to_dict()
    if set(sc)!={"ABSENT_ALL_NATIVE_PHONES"}: fail(f"P0B parent status inconsistency: {sc}")
    if len(p0b)!=22437: fail(f"P0B eligible row count changed: {len(p0b)} != 22437")

    con=setup()
    exposed_frames=[]
    control_frames=[]
    tract_count_frames=[]

    for region in ALL_REGIONS:
        poi_url=f"{CHALLENGE_BASE}/reference/{region}/{region}-overture-pois.parquet"
        tract_url=f"{CHALLENGE_BASE}/strata/{region}/{region}-census-tracts.parquet"
        tname="t_"+region.replace("-","_")
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE {tname} AS
            SELECT lpad(CAST(GEOID AS VARCHAR),11,'0') AS GEOID, geometry, bbox
            FROM read_parquet('{q(tract_url)}')
        """)

        exp=p0b[p0b["region"]==region][["record_id","gers_id","GEOID"]].copy()
        if exp.empty: continue
        con.register("exp_ids",exp)

        em=con.execute(f"""
            SELECT '{region}' AS region,e.GEOID,e.record_id,e.gers_id,
                   CAST(p.categories.primary AS VARCHAR) AS primary_category,
                   COALESCE(array_length(p.sources),0) AS source_count,
                   CAST(p.operating_status AS VARCHAR) AS operating_status,
                   CASE WHEN p.brand IS NULL THEN 0 ELSE 1 END AS brand_present
            FROM exp_ids e
            JOIN read_parquet('{q(poi_url)}') p
              ON CAST(p.id AS VARCHAR)=e.gers_id
        """).fetchdf()
        em["GEOID"]=em["GEOID"].astype(str).str.zfill(11)
        em["primary_category"]=em["primary_category"].fillna("").astype(str).str.strip()
        em["source_count_bin"]=em["source_count"].apply(source_bin)
        em["operating_status_bin"]=em["operating_status"].apply(status_bin)
        em["brand_present"]=em["brand_present"].astype(int)
        em["exp_hash"]=[hh("ATP_PHONE_P0C_EXP_v1",x) for x in em["gers_id"].astype(str)]
        exposed_frames.append(em)

        cells=em[em["primary_category"].ne("")][
            ["GEOID","primary_category","source_count_bin","operating_status_bin","brand_present"]
        ].drop_duplicates()
        if not cells.empty:
            con.register("cells",cells)
            rc=con.execute(f"""
                WITH cand AS (
                    SELECT CAST(p.id AS VARCHAR) AS control_gers_id,
                           CAST(p.categories.primary AS VARCHAR) AS primary_category,
                           COALESCE(array_length(p.sources),0) AS source_count,
                           CASE
                             WHEN CAST(p.operating_status AS VARCHAR)='open' THEN 'OPEN'
                             WHEN CAST(p.operating_status AS VARCHAR)='permanently_closed' THEN 'CLOSED'
                             ELSE 'OTHER'
                           END AS operating_status_bin,
                           CASE WHEN p.brand IS NULL THEN 0 ELSE 1 END AS brand_present,
                           p.geometry,p.bbox
                    FROM read_parquet('{q(poi_url)}') p
                    WHERE p.categories.primary IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM UNNEST(p.sources) AS u(src)
                        WHERE lower(CAST(src.dataset AS VARCHAR))='alltheplaces'
                      )
                ),
                located AS (
                    SELECT '{region}' AS region,t.GEOID,c.*
                    FROM cand c
                    JOIN {tname} t
                      ON c.bbox.xmin<=t.bbox.xmax AND c.bbox.xmax>=t.bbox.xmin
                     AND c.bbox.ymin<=t.bbox.ymax AND c.bbox.ymax>=t.bbox.ymin
                     AND ST_Intersects(t.geometry,c.geometry)
                ),
                unamb AS (
                    SELECT *,
                           COUNT(DISTINCT GEOID) OVER (PARTITION BY control_gers_id) AS geoid_memberships
                    FROM located
                )
                SELECT u.region,u.GEOID,u.control_gers_id,u.primary_category,u.source_count,
                       CASE WHEN u.source_count<=1 THEN 'ONE' ELSE 'MULTI' END AS source_count_bin,
                       u.operating_status_bin,u.brand_present
                FROM unamb u
                JOIN cells x
                  ON x.GEOID=u.GEOID
                 AND x.primary_category=u.primary_category
                 AND x.source_count_bin=CASE WHEN u.source_count<=1 THEN 'ONE' ELSE 'MULTI' END
                 AND x.operating_status_bin=u.operating_status_bin
                 AND x.brand_present=u.brand_present
                WHERE u.geoid_memberships=1
            """).fetchdf()
            if len(rc):
                rc["GEOID"]=rc["GEOID"].astype(str).str.zfill(11)
                rc=rc.drop_duplicates(subset=["region","GEOID","control_gers_id","primary_category","source_count_bin","operating_status_bin","brand_present"])
                rc["ctl_hash"]=[hh("ATP_PHONE_P0C_CTL_v1",x) for x in rc["control_gers_id"].astype(str)]
                control_frames.append(rc)

        tc=con.execute(f"""
            SELECT '{region}' AS region,t.GEOID,COUNT(DISTINCT CAST(p.id AS VARCHAR)) AS total_pois
            FROM read_parquet('{q(poi_url)}') p
            JOIN {tname} t
              ON p.bbox.xmin<=t.bbox.xmax AND p.bbox.xmax>=t.bbox.xmin
             AND p.bbox.ymin<=t.bbox.ymax AND p.bbox.ymax>=t.bbox.ymin
             AND ST_Intersects(t.geometry,p.geometry)
            GROUP BY t.GEOID
        """).fetchdf()
        tc["GEOID"]=tc["GEOID"].astype(str).str.zfill(11)
        tract_count_frames.append(tc)

    exposed=pd.concat(exposed_frames,ignore_index=True)
    controls=pd.concat(control_frames,ignore_index=True) if control_frames else pd.DataFrame()
    tract_counts=pd.concat(tract_count_frames,ignore_index=True)

    if len(exposed)!=22437: fail(f"exposed metadata coverage {len(exposed)} != 22437")
    exposed.to_csv(EXPOSED_META_OUT,index=False)
    controls.to_csv(CONTROL_POOL_OUT,index=False)

    emit()
    emit("===== PRE-OUTCOME MATCHING METADATA =====")
    emit(f"EXPOSED_METADATA_ROWS={len(exposed)}")
    emit(f"EXPOSED_NONBLANK_PRIMARY_CATEGORY={(exposed['primary_category']!='').sum()}")
    emit(f"CONTROL_POOL_ROWS={len(controls)}")
    emit(f"EXPOSED_METADATA={EXPOSED_META_OUT}|SHA256={sha256_file(EXPOSED_META_OUT)}")
    emit(f"CONTROL_POOL={CONTROL_POOL_OUT}|SHA256={sha256_file(CONTROL_POOL_OUT)}")
    emit("CONTROL_PHONE_OUTCOME_READ=NO")

    if controls.empty: fail("no exact preoutcome control pool")

    keys=["region","GEOID","primary_category","source_count_bin","operating_status_bin","brand_present"]
    e=exposed[exposed["primary_category"].ne("")].sort_values(keys+["exp_hash","gers_id"],kind="mergesort").copy()
    e["cell_rank"]=e.groupby(keys).cumcount()
    c=controls.sort_values(keys+["ctl_hash","control_gers_id"],kind="mergesort").copy()
    c["cell_rank"]=c.groupby(keys).cumcount()

    pairs=e.merge(c,on=keys+["cell_rank"],how="inner",suffixes=("_exp","_ctl"),validate="one_to_one")
    pairs=pairs[[
        "region","GEOID","primary_category","source_count_bin","operating_status_bin","brand_present","cell_rank",
        "record_id","gers_id","control_gers_id","source_count_exp","source_count_ctl","exp_hash","ctl_hash"
    ]].copy()
    pairs=pairs.sort_values(["region","GEOID","primary_category","cell_rank","gers_id"],kind="mergesort").reset_index(drop=True)
    pairs.to_csv(PAIR_OUT,index=False)
    pair_hash=sha256_file(PAIR_OUT)

    pp=pairs[pairs["region"].isin(PRIMARY_REGIONS)].copy()
    support=(len(pp)>=MIN_MATCHED_PAIRS and pp["GEOID"].nunique()>=MIN_MATCHED_TRACTS and
             pp["region"].nunique()>=MIN_MATCHED_REGIONS and pp["primary_category"].nunique()>=MIN_MATCHED_CATEGORIES)

    emit()
    emit("===== FROZEN MATCH SUPPORT — BEFORE CONTROL PHONE READ =====")
    emit(f"PRIMARY_MATCHED_PAIRS={len(pp)}")
    emit(f"PRIMARY_MATCHED_TRACTS={pp['GEOID'].nunique()}")
    emit(f"PRIMARY_MATCHED_REGIONS={pp['region'].nunique()}")
    emit(f"PRIMARY_MATCHED_CATEGORIES={pp['primary_category'].nunique()}")
    emit(f"ALL_REGION_MATCHED_PAIRS={len(pairs)}")
    emit(f"MATCHED_PAIR_TABLE={PAIR_OUT}|SHA256={pair_hash}")
    emit("MATCHED_PAIR_TABLE_FROZEN=YES")
    emit("CONTROL_PHONE_OUTCOME_READ=NO")
    if not support:
        fail(f"match support failed pairs={len(pp)},tracts={pp['GEOID'].nunique()},regions={pp['region'].nunique()},categories={pp['primary_category'].nunique()}")

    emit()
    emit("===== MATCH FREEZE COMPLETE — CONTROL PHONE READ AUTHORIZED =====")
    emit("CONTROL_PHONE_OUTCOME_READ=YES")

    phone_frames=[]
    for region in ALL_REGIONS:
        ids=pairs[pairs["region"]==region][["control_gers_id"]].drop_duplicates()
        if ids.empty: continue
        con.register("control_ids",ids)
        poi_url=f"{CHALLENGE_BASE}/reference/{region}/{region}-overture-pois.parquet"
        cf=con.execute(f"""
            SELECT '{region}' AS region,c.control_gers_id,to_json(p.phones) AS control_phones_json
            FROM control_ids c
            JOIN read_parquet('{q(poi_url)}') p
              ON CAST(p.id AS VARCHAR)=c.control_gers_id
        """).fetchdf()
        phone_frames.append(cf)

    cp=pd.concat(phone_frames,ignore_index=True)
    expected=set(zip(pairs["region"].astype(str),pairs["control_gers_id"].astype(str)))
    got=set(zip(cp["region"].astype(str),cp["control_gers_id"].astype(str)))
    coverage=len(expected&got)/max(1,len(expected))
    emit(f"EXACT_MATCHED_CONTROL_GERS_COVERAGE={coverage:.9f}")
    if coverage!=1.0: fail(f"control GERS coverage {coverage:.9f} != 1.0")

    cp["control_has_valid_native_phone"]=[bool(parse_native_phone(x)[1]) for x in cp["control_phones_json"]]
    cp["control_phone_canonical"]=["|".join(parse_native_phone(x)[1]) for x in cp["control_phones_json"]]

    result=pairs.merge(cp,on=["region","control_gers_id"],how="left",validate="many_to_one")
    result["exposed_has_valid_native_phone"]=False
    result["paired_rd"]=result["control_has_valid_native_phone"].astype(int)
    result.to_csv(RESULT_OUT,index=False)

    primary=result[result["region"].isin(PRIMARY_REGIONS)].copy()
    er=float(primary["exposed_has_valid_native_phone"].mean())
    cr=float(primary["control_has_valid_native_phone"].mean())
    rd=cr-er
    nphone=int(primary["control_has_valid_native_phone"].sum())

    reg=primary.groupby("region",as_index=False).agg(
        matched_pairs=("gers_id","size"),
        exposed_phone_rate=("exposed_has_valid_native_phone","mean"),
        control_phone_rate=("control_has_valid_native_phone","mean"),
        controls_with_phone=("control_has_valid_native_phone","sum"),
        tracts=("GEOID","nunique"),
        categories=("primary_category","nunique"),
    )
    reg["risk_difference"]=reg["control_phone_rate"]-reg["exposed_phone_rate"]
    reg.to_csv(REGION_OUT,index=False)
    qregs=int((reg["risk_difference"]>=MIN_REGION_RD).sum())

    emit()
    emit("===== PRIMARY MATCHED CONTACTABILITY RESULT =====")
    emit(f"PRIMARY_MATCHED_PAIRS={len(primary)}")
    emit(f"EXPOSED_VALID_NATIVE_PHONE_RATE={er:.9f}")
    emit(f"CONTROL_VALID_NATIVE_PHONE_RATE={cr:.9f}")
    emit(f"MATCHED_NATIVE_CONTACTABILITY_RD={rd:+.9f}")
    emit(f"MATCHED_CONTROLS_WITH_VALID_PHONE={nphone}")
    emit(f"REGIONS_RD_GE_{MIN_REGION_RD:.2f}={qregs}/4")
    for r in reg.itertuples(index=False):
        emit(f"REGION={r.region}|pairs={r.matched_pairs}|exposed={r.exposed_phone_rate:.9f}|control={r.control_phone_rate:.9f}|rd={r.risk_difference:+.9f}|control_phone_n={int(r.controls_with_phone)}|tracts={r.tracts}|categories={r.categories}")

    emit()
    emit("===== SOURCE MULTIPLICITY CHARACTERIZATION =====")
    for b in ("ONE","MULTI"):
        sub=primary[primary["source_count_bin"]==b]
        if len(sub):
            ex=float(sub["exposed_has_valid_native_phone"].mean())
            co=float(sub["control_has_valid_native_phone"].mean())
            emit(f"SOURCE_BIN={b}|pairs={len(sub)}|exposed_native_phone_rate={ex:.9f}|control_native_phone_rate={co:.9f}|rd={co-ex:+.9f}")

    loss_counts=(p0b[p0b["region"].isin(PRIMARY_REGIONS)].groupby(["region","GEOID"],as_index=False)
                 .agg(ATP_phone_loss_count=("record_id","size")))
    burden=tract_counts[tract_counts["region"].isin(PRIMARY_REGIONS)].merge(loss_counts,on=["region","GEOID"],how="left")
    burden["ATP_phone_loss_count"]=burden["ATP_phone_loss_count"].fillna(0).astype(int)
    burden["loss_burden_share"]=np.where(burden["total_pois"]>0,burden["ATP_phone_loss_count"]/burden["total_pois"],np.nan)

    # Secondary literal SVI/pop context is only read now, after primary match freeze.
    contexts=[]
    for region in PRIMARY_REGIONS:
        tract_url=f"{CHALLENGE_BASE}/strata/{region}/{region}-census-tracts.parquet"
        desc=con.execute(f"DESCRIBE SELECT * FROM read_parquet('{q(tract_url)}')").fetchdf()
        actual=list(desc["column_name"].astype(str)); low={x.lower():x for x in actual}
        svi=low.get("svi")
        pop=low.get("population") or low.get("pop_total")
        sel=["lpad(CAST(GEOID AS VARCHAR),11,'0') AS GEOID"]
        if svi: sel.append(f"CAST({qi(svi)} AS DOUBLE) AS SVI")
        if pop: sel.append(f"CAST({qi(pop)} AS DOUBLE) AS population_context")
        ctx=con.execute(f"SELECT {','.join(sel)} FROM read_parquet('{q(tract_url)}')").fetchdf()
        ctx["region"]=region; ctx["GEOID"]=ctx["GEOID"].astype(str).str.zfill(11)
        contexts.append(ctx)
    if contexts:
        burden=burden.merge(pd.concat(contexts,ignore_index=True,sort=False),on=["region","GEOID"],how="left")
    burden.to_csv(TRACT_OUT,index=False)

    anchor=burden[(burden["total_pois"]>=20)&(burden["ATP_phone_loss_count"]>=5)].copy()
    anchor=anchor.sort_values(["region","loss_burden_share","ATP_phone_loss_count","GEOID"],ascending=[True,False,False,True],kind="mergesort")
    anchor["region_rank"]=anchor.groupby("region").cumcount()+1
    anchor=anchor[anchor["region_rank"]<=3]
    anchor.to_csv(ANCHOR_OUT,index=False)

    emit()
    emit("===== MECHANICAL TRACT BURDEN ANCHORS =====")
    emit(f"TRACT_BURDEN_TABLE={TRACT_OUT}|SHA256={sha256_file(TRACT_OUT)}")
    emit(f"MECHANICAL_ANCHORS={ANCHOR_OUT}|SHA256={sha256_file(ANCHOR_OUT)}")
    for r in anchor.itertuples(index=False):
        svi=getattr(r,"SVI",np.nan); pop=getattr(r,"population_context",np.nan)
        emit(f"ANCHOR={r.region}|rank={int(r.region_rank)}|GEOID={r.GEOID}|losses={int(r.ATP_phone_loss_count)}|total_pois={int(r.total_pois)}|burden_share={r.loss_burden_share:.9f}|SVI={svi if not pd.isna(svi) else 'NA'}|population={pop if not pd.isna(pop) else 'NA'}")

    if "SVI" in burden.columns:
        valid=burden[pd.to_numeric(burden["SVI"],errors="coerce").notna()].copy()
        valid["SVI"]=pd.to_numeric(valid["SVI"],errors="coerce")
        hi=valid[valid["SVI"]>=0.75]; lo=valid[valid["SVI"]<0.25]
        diff=(float(hi["loss_burden_share"].mean()-lo["loss_burden_share"].mean()) if len(hi) and len(lo) else np.nan)
        ss=pd.DataFrame([{
            "high_svi_tracts":len(hi),"low_svi_tracts":len(lo),
            "high_mean_loss_burden_share":float(hi["loss_burden_share"].mean()) if len(hi) else np.nan,
            "low_mean_loss_burden_share":float(lo["loss_burden_share"].mean()) if len(lo) else np.nan,
            "high_minus_low":diff
        }])
        ss.to_csv(SVI_OUT,index=False)
        emit("SVI_OUTCOME_READ=YES_SECONDARY_ONLY")
        emit(f"SECONDARY_SVI|high_n={len(hi)}|low_n={len(lo)}|high_mean={hi['loss_burden_share'].mean() if len(hi) else float('nan'):.9f}|low_mean={lo['loss_burden_share'].mean() if len(lo) else float('nan'):.9f}|diff={diff:+.9f}")
    else:
        SVI_OUT.write_text("SVI secondary comparison not run: literal SVI column absent.\n",encoding="utf-8")
        emit("SVI_OUTCOME_READ=NO|REASON=LITERAL_SVI_COLUMN_ABSENT")

    gp=rd>=MIN_RD
    gr=qregs>=MIN_REGIONS_RD
    gn=nphone>=MIN_CONTROL_WITH_PHONE
    overall=bool(support and coverage==1.0 and gp and gr and gn)

    emit()
    emit("===== FROZEN P0C GATES =====")
    emit(f"GATE_A_MATCH_SUPPORT={'PASS' if support else 'FAIL'}")
    emit(f"GATE_B_CONTROL_GERS_RETRIEVAL={'PASS' if coverage==1.0 else 'FAIL'}")
    emit(f"GATE_C_OVERALL_RD_GE_{MIN_RD:.2f}={'PASS' if gp else 'FAIL'}")
    emit(f"GATE_D_REGIONAL_RD={'PASS' if gr else 'FAIL'}")
    emit(f"GATE_E_CONTROL_PHONE_COUNT={'PASS' if gn else 'FAIL'}")

    manifest={
        "version":VERSION,"parent_manifest_sha256":P0B_MANIFEST_SHA,
        "primary_regions":list(PRIMARY_REGIONS),"supplemental_regions":list(SUPPLEMENTAL_REGIONS),
        "matched_pairs_primary":int(len(primary)),"matched_tracts_primary":int(primary["GEOID"].nunique()),
        "matched_categories_primary":int(primary["primary_category"].nunique()),
        "exposed_native_phone_rate":er,"control_native_phone_rate":cr,"matched_risk_difference":rd,
        "controls_with_valid_phone":nphone,"regions_rd_ge_015":qregs,
        "gates":{"match_support":bool(support),"control_gers_retrieval":bool(coverage==1.0),
                 "overall_rd":bool(gp),"regional_rd":bool(gr),"control_phone_count":bool(gn)},
        "overall_pass":overall,"p0d_authorized":overall,
        "novelty_status":"PROVISIONAL_PASS_REQUIRES_DIRECT_LIVE_ZINDI_RECHECK",
        "outputs":{}
    }
    for p in (EXPOSED_META_OUT,CONTROL_POOL_OUT,PAIR_OUT,RESULT_OUT,REGION_OUT,TRACT_OUT,ANCHOR_OUT,SVI_OUT):
        manifest["outputs"][p.name]={"path":str(p),"sha256":sha256_file(p),"bytes":p.stat().st_size}
    MANIFEST.write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding="utf-8")

    emit()
    emit(f"MATCHED_RESULTS={RESULT_OUT}|SHA256={sha256_file(RESULT_OUT)}")
    emit(f"REGION_SUMMARY={REGION_OUT}|SHA256={sha256_file(REGION_OUT)}")
    emit(f"MANIFEST={MANIFEST}|SHA256={sha256_file(MANIFEST)}")
    emit("NOVELTY_STATUS=PROVISIONAL_PASS_REQUIRES_DIRECT_LIVE_ZINDI_RECHECK")

    if overall:
        emit("ATP_PHONE_P0C=PASS")
        emit("ATP_PHONE_P0D_AUTHORIZED=YES")
        emit("SOURCE_LAYER_STRUCTURAL_REOPEN=YES")
        emit("NEXT=P0D FREEZE OPERATIONAL SERVICE-ROLE IMPACT + DIRECT LIVE COMPETITOR AUTOPSY + CLAIM/REPRODUCIBILITY CHAMPIONSHIP REVIEW.")
    else:
        emit("ATP_PHONE_P0C=FAIL")
        emit("ATP_PHONE_P0D_AUTHORIZED=NO")
        emit("SOURCE_LAYER_STRUCTURAL_REOPEN=NO")
        emit("NEXT=RETIRE MATCHED CONTACTABILITY ROUTE. NO MATCHING/CATEGORY/SVI/GEOGRAPHIC RESCUE.")

if __name__=="__main__":
    main()

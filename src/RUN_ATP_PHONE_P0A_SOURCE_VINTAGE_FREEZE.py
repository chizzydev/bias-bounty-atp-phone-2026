from __future__ import annotations

from pathlib import Path
import os
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import urllib.request
import urllib.error

import duckdb
import numpy as np
import pandas as pd

VERSION = "ATP-PHONE-P0A-1.0"
SALT = "ATP_PHONE_P0A_v1"

ROOT = Path(os.environ.get("ATP_PHONE_ROOT", str(Path.cwd() / "atp_run"))).resolve()
OUT = ROOT / "outputs"
INSPECT = ROOT / "inspections"
STATE = INSPECT / "ATP-PHONE-P0A-state"

PREREG_LOCAL_NAME = "ATP_PHONE_P0A_SOURCE_VINTAGE_PREREGISTRATION_v1.0.txt"
EXPECTED_PREREG_SHA256 = "A50AB3CC5481FBB53798CAEBD8EA981CE783EBE396B296FC81161C079F47B86F"

REGIONS = (
    "eastern-ok",
    "maricopa-az",
    "northern-ca",
    "south-central-tx",
    "eastern-wa",
)

CHALLENGE_BASE = (
    "s3://us-west-2.opendata.source.coop/"
    "humane-intelligence/bias-bounty-mapping-equity-challenge"
)
BRIDGE_GLOB_ALL = (
    "s3://overturemaps-us-west-2/bridgefiles/2026-08-19.0/"
    "provider=*/theme=places/type=place/*"
)
ATP_HISTORY_URL = "https://data.alltheplaces.xyz/runs/history.json"

MIN_SOURCE_RECORDS = 60
MIN_TRACTS = 10
MIN_REGIONS = 2
MAX_MEMBERSHIP_AMBIGUITY = 0.02
WITNESS_MAX = 120

REPORT = INSPECT / "ATP-PHONE-P0A-source-vintage-freeze-report.txt"
SOURCE_ROWS_OUT = OUT / "ATP-PHONE-P0A-exact-source-links.csv"
WITNESS_OUT = OUT / "ATP-PHONE-P0A-frozen-witness-sample.csv"
BRIDGE_OUT = OUT / "ATP-PHONE-P0A-bridge-replay.csv"
SOURCE_META_OUT = INSPECT / "ATP-PHONE-P0A-source-provenance-summary.csv"
HISTORY_OUT = STATE / "alltheplaces-runs-history.json"
HISTORY_SUMMARY_OUT = INSPECT / "ATP-PHONE-P0A-atp-history-candidates.csv"
MANIFEST = INSPECT / "ATP-PHONE-P0A-manifest.json"

PHONE_OUTCOME_READ = False

def emit(s=""):
    print(str(s), flush=True)
    with REPORT.open("a", encoding="utf-8") as f:
        f.write(str(s) + "\n")

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest().upper()

def fail(msg: str, status="FAIL"):
    emit(f"ATP_PHONE_P0A={status}")
    emit("ATP_PHONE_P0B_AUTHORIZED=NO")
    emit(f"FAIL_REASON={msg}")
    raise RuntimeError(msg)

def q(v: str) -> str:
    return str(v).replace("'", "''")

def setup() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("SET s3_region='us-west-2'")
    con.execute("SET s3_url_style='path'")
    con.execute("SET threads TO 2")
    con.execute("SET memory_limit='4GB'")
    return con

def hash_order(record_id: str, gers_id: str) -> str:
    return hashlib.sha256(
        f"{SALT}|{record_id}|{gers_id}".encode("utf-8")
    ).hexdigest()

def safe_json(v):
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    s = str(v)
    if not s or s.lower() == "nan":
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}

def clean(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v).strip()

def fetch_bytes(url: str, timeout=180) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "bias-bounty-atp-phone-p0a/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def parse_dt(v: str):
    if not v:
        return None
    s = str(v).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def flatten_runs(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("runs", "history", "items", "results"):
            if isinstance(obj.get(key), list):
                return obj[key]
    return []

def provenance_tokens(df: pd.DataFrame):
    tokens = set()
    for col in ("source_version", "resource"):
        if col not in df:
            continue
        for v in df[col].astype(str):
            s = v.strip()
            if not s or s.lower() in ("nan", "none", "null"):
                continue
            tokens.add(s)
            # Also keep slash/path components and timestamp/date-like substrings.
            for p in re.split(r"[/\\|,;\s]+", s):
                if p:
                    tokens.add(p)
    return tokens

def exact_run_resolution(runs, tokens):
    by_id = {}
    for r in runs:
        rid = clean(r.get("run_id"))
        if rid:
            by_id[rid] = r

    exact = []
    for tok in tokens:
        if tok in by_id:
            exact.append((tok, by_id[tok], "EXACT_RUN_ID_TOKEN"))
    if len({x[1]["run_id"] for x in exact}) == 1:
        return exact[0][1], exact[0][2]

    # Exact unambiguous containment of a full run_id in a provenance token.
    contained = []
    for rid, r in by_id.items():
        for tok in tokens:
            if rid and rid in tok:
                contained.append((rid, r, "RUN_ID_EMBEDDED_IN_PROVENANCE"))
                break
    if len({x[0] for x in contained}) == 1:
        return contained[0][1], contained[0][2]

    # Exact date token only if precisely one historical run has that end date.
    date_tokens = {
        t for t in tokens if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", t)
    }
    date_matches = []
    for dtok in date_tokens:
        cand = []
        for r in runs:
            dt = parse_dt(clean(r.get("end_time")))
            if dt and dt.date().isoformat() == dtok:
                cand.append(r)
        if len(cand) == 1:
            date_matches.append((cand[0], "UNIQUE_EXACT_END_DATE_TOKEN"))
    if len({clean(x[0].get("run_id")) for x in date_matches}) == 1 and date_matches:
        return date_matches[0]

    return None, "UNRESOLVED"

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    INSPECT.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    for p in (
        REPORT, SOURCE_ROWS_OUT, WITNESS_OUT, BRIDGE_OUT,
        SOURCE_META_OUT, HISTORY_SUMMARY_OUT, MANIFEST
    ):
        p.unlink(missing_ok=True)

    emit("===== ATP-PHONE-P0A — SOURCE-LINK / VINTAGE / UNIVERSE FREEZE =====")
    emit(f"VERSION={VERSION}|PYTHON={sys.version.split()[0]}|DUCKDB={duckdb.__version__}")
    emit("OVERTURE_RELEASE=2026-08-19.0")
    emit("OVERTURE_SCHEMA=v1.18.0")
    emit("SOURCE_DATASET=AllThePlaces")
    emit("PHONE_OUTCOME_READ=NO")
    emit("OVERTURE_PHONE_FIELD_READ=NO")
    emit("ATP_PHONE_FIELD_READ=NO")
    emit("SVI_OR_DEMOGRAPHIC_OUTCOME_READ=NO")
    emit("FUZZY_OR_PROXIMITY_ENTITY_MATCHING=NO")
    emit("P0B_AUTHORIZED=NO")
    emit()

    prereg = Path(__file__).resolve().parent / PREREG_LOCAL_NAME
    if not prereg.exists():
        fail(f"missing preregistration: {prereg}")
    ph = sha256_file(prereg)
    emit(f"PREREGISTRATION={prereg}|SHA256={ph}")
    if ph != EXPECTED_PREREG_SHA256:
        fail(f"prereg hash mismatch expected={EXPECTED_PREREG_SHA256} actual={ph}")

    con = setup()
    parts = []

    for region in REGIONS:
        tract_url = f"{CHALLENGE_BASE}/strata/{region}/{region}-census-tracts.parquet"
        poi_url = f"{CHALLENGE_BASE}/reference/{region}/{region}-overture-pois.parquet"
        table = "tract_" + region.replace("-", "_")

        # Explicitly inspect schema names only; never select phones.
        poi_desc = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{q(poi_url)}')"
        ).fetchdf()
        cols = set(poi_desc["column_name"].astype(str))
        required = {"id", "geometry", "bbox", "sources"}
        missing = required - cols
        if missing:
            fail(f"{region}: POI schema missing required columns {sorted(missing)}")

        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE {table} AS
            SELECT
                lpad(CAST(GEOID AS VARCHAR), 11, '0') AS GEOID,
                geometry,
                bbox
            FROM read_parquet('{q(tract_url)}')
            """
        )

        # No phones field is referenced anywhere in this query.
        query = f"""
            WITH raw AS (
                SELECT
                    '{region}' AS region,
                    t.GEOID,
                    CAST(p.id AS VARCHAR) AS gers_id,
                    to_json(src) AS source_json,
                    ST_X(p.geometry) AS longitude,
                    ST_Y(p.geometry) AS latitude
                FROM read_parquet('{q(poi_url)}') p
                JOIN {table} t
                  ON p.bbox.xmin <= t.bbox.xmax
                 AND p.bbox.xmax >= t.bbox.xmin
                 AND p.bbox.ymin <= t.bbox.ymax
                 AND p.bbox.ymax >= t.bbox.ymin
                 AND ST_Intersects(t.geometry, p.geometry)
                CROSS JOIN UNNEST(p.sources) AS u(src)
                WHERE lower(CAST(src.dataset AS VARCHAR)) = 'alltheplaces'
            )
            SELECT * FROM raw
        """
        try:
            df = con.execute(query).fetchdf()
        except Exception as exc:
            fail(f"{region}: failed exact ATP source extraction before phone read: {exc}")

        emit(
            f"ATP_SOURCE_ROWS={region}|rows={len(df)}|"
            f"tracts={df['GEOID'].nunique() if len(df) else 0}|"
            f"gers={df['gers_id'].nunique() if len(df) else 0}"
        )
        if len(df):
            parts.append(df)

    if not parts:
        fail("no AllThePlaces source rows found in scored challenge tracts")

    raw = pd.concat(parts, ignore_index=True)

    # Parse provenance only.
    prov_rows = []
    for r in raw.itertuples(index=False):
        s = safe_json(r.source_json)
        prov_rows.append({
            "region": r.region,
            "GEOID": str(r.GEOID).zfill(11),
            "gers_id": clean(r.gers_id),
            "record_id": clean(s.get("record_id")),
            "dataset": clean(s.get("dataset")),
            "provider": clean(s.get("provider")),
            "resource": clean(s.get("resource")),
            "source_version": clean(s.get("version")),
            "update_time": clean(s.get("update_time")),
            "longitude": float(r.longitude) if r.longitude is not None else np.nan,
            "latitude": float(r.latitude) if r.latitude is not None else np.nan,
        })

    src = pd.DataFrame(prov_rows)
    src = src[
        src["record_id"].str.strip().ne("")
        & src["gers_id"].str.strip().ne("")
    ].copy()
    if src.empty:
        fail("ATP source rows expose no nonblank record_id")

    # Exact source link rows only; duplicate exact rows collapse.
    src = src.drop_duplicates(
        subset=["region","GEOID","gers_id","record_id","provider","resource","source_version","update_time"]
    ).reset_index(drop=True)

    # Quantify membership ambiguity at source-record level.
    membership = (
        src.groupby("record_id", as_index=False)
        .agg(
            region_count=("region","nunique"),
            tract_count=("GEOID","nunique"),
            gers_count=("gers_id","nunique"),
        )
    )
    ambiguous_ids = set(
        membership.loc[
            (membership["region_count"] != 1) | (membership["tract_count"] != 1),
            "record_id"
        ]
    )
    ambiguity_share = len(ambiguous_ids) / max(1, membership["record_id"].nunique())

    eligible = src[~src["record_id"].isin(ambiguous_ids)].copy()
    # A single ATP record mapping to multiple GERS IDs is not automatically invalid, but
    # P0A freezes each exact pair and reports multiplicity for later P0B treatment.
    eligible["hash_order"] = [
        hash_order(rid, gid)
        for rid, gid in zip(eligible["record_id"], eligible["gers_id"])
    ]
    eligible = eligible.sort_values(
        ["hash_order","record_id","gers_id"], kind="mergesort"
    ).reset_index(drop=True)

    eligible.to_csv(SOURCE_ROWS_OUT, index=False)

    source_records = eligible["record_id"].nunique()
    tracts = eligible["GEOID"].nunique()
    regions = eligible["region"].nunique()

    emit()
    emit("===== P0A SUPPORT =====")
    emit(f"DISTINCT_ATP_SOURCE_RECORDS={source_records}")
    emit(f"DISTINCT_SCORED_TRACTS={tracts}")
    emit(f"DISTINCT_CHALLENGE_REGIONS={regions}")
    emit(f"MEMBERSHIP_AMBIGUOUS_RECORDS={len(ambiguous_ids)}")
    emit(f"MEMBERSHIP_AMBIGUITY_SHARE={ambiguity_share:.9f}")
    emit(f"MULTI_GERS_ATP_RECORDS={(membership['gers_count'] > 1).sum()}")

    support_pass = (
        source_records >= MIN_SOURCE_RECORDS
        and tracts >= MIN_TRACTS
        and regions >= MIN_REGIONS
    )
    ambiguity_pass = ambiguity_share <= MAX_MEMBERSHIP_AMBIGUITY

    # Freeze deterministic witness sample before bridge/history checks.
    pair_cols = [
        "region","GEOID","gers_id","record_id","provider",
        "resource","source_version","update_time","longitude","latitude","hash_order"
    ]
    witness = (
        eligible[pair_cols]
        .drop_duplicates(subset=["record_id","gers_id"])
        .sort_values(["hash_order","record_id","gers_id"], kind="mergesort")
        .head(WITNESS_MAX)
        .reset_index(drop=True)
    )
    witness.to_csv(WITNESS_OUT, index=False)
    emit(f"FROZEN_WITNESS_PAIRS={len(witness)}")
    emit(f"WITNESS_SHA256={sha256_file(WITNESS_OUT)}")

    if not support_pass:
        fail(
            f"support gate failed records={source_records}/{MIN_SOURCE_RECORDS}, "
            f"tracts={tracts}/{MIN_TRACTS}, regions={regions}/{MIN_REGIONS}"
        )
    if not ambiguity_pass:
        fail(
            f"membership ambiguity {ambiguity_share:.6f} exceeds "
            f"{MAX_MEMBERSHIP_AMBIGUITY:.6f}"
        )

    # Source provenance summary: outcome-blind.
    meta = (
        eligible.groupby(
            ["provider","resource","source_version","update_time"],
            dropna=False,
            as_index=False
        )
        .agg(
            rows=("record_id","size"),
            distinct_records=("record_id","nunique"),
            distinct_gers=("gers_id","nunique"),
            distinct_tracts=("GEOID","nunique"),
        )
        .sort_values(["rows","provider","resource"], ascending=[False,True,True])
    )
    meta.to_csv(SOURCE_META_OUT, index=False)
    emit(f"SOURCE_PROVENANCE_SUMMARY={SOURCE_META_OUT}|SHA256={sha256_file(SOURCE_META_OUT)}")

    # Bridge replay on the deterministic exact-pair sample.
    providers = sorted({
        p for p in witness["provider"].astype(str)
        if p.strip() and p.strip().lower() not in ("nan","none","null","")
    })
    if providers:
        bridge_paths = [
            (
                "s3://overturemaps-us-west-2/bridgefiles/2026-08-19.0/"
                f"provider={p}/theme=places/type=place/*"
            )
            for p in providers
        ]
    else:
        bridge_paths = [BRIDGE_GLOB_ALL]

    con.register("p0a_witness", witness[["record_id","gers_id"]])

    bridge_frames = []
    bridge_errors = []
    for path in bridge_paths:
        try:
            b = con.execute(
                f"""
                SELECT DISTINCT
                    CAST(b.id AS VARCHAR) AS gers_id,
                    CAST(b.record_id AS VARCHAR) AS record_id,
                    CAST(b.dataset AS VARCHAR) AS dataset,
                    CAST(b.provider AS VARCHAR) AS provider,
                    CAST(b.resource AS VARCHAR) AS resource,
                    CAST(b.version AS VARCHAR) AS version,
                    CAST(b.update_time AS VARCHAR) AS update_time
                FROM read_parquet('{q(path)}', hive_partitioning=1) b
                JOIN p0a_witness w
                  ON CAST(b.id AS VARCHAR) = w.gers_id
                 AND CAST(b.record_id AS VARCHAR) = w.record_id
                WHERE lower(CAST(b.dataset AS VARCHAR)) = 'alltheplaces'
                """
            ).fetchdf()
            if len(b):
                bridge_frames.append(b)
        except Exception as exc:
            bridge_errors.append(f"{path}: {exc}")

    if not bridge_frames and providers:
        # Provider in source provenance may not equal the bridge partition key in older
        # source structs. Retry the official provider=* bridge layout without changing
        # the witness universe.
        try:
            b = con.execute(
                f"""
                SELECT DISTINCT
                    CAST(b.id AS VARCHAR) AS gers_id,
                    CAST(b.record_id AS VARCHAR) AS record_id,
                    CAST(b.dataset AS VARCHAR) AS dataset,
                    CAST(b.provider AS VARCHAR) AS provider,
                    CAST(b.resource AS VARCHAR) AS resource,
                    CAST(b.version AS VARCHAR) AS version,
                    CAST(b.update_time AS VARCHAR) AS update_time
                FROM read_parquet('{q(BRIDGE_GLOB_ALL)}', hive_partitioning=1) b
                JOIN p0a_witness w
                  ON CAST(b.id AS VARCHAR) = w.gers_id
                 AND CAST(b.record_id AS VARCHAR) = w.record_id
                WHERE lower(CAST(b.dataset AS VARCHAR)) = 'alltheplaces'
                """
            ).fetchdf()
            if len(b):
                bridge_frames.append(b)
        except Exception as exc:
            bridge_errors.append(f"{BRIDGE_GLOB_ALL}: {exc}")

    if not bridge_frames:
        fail(
            "August bridge replay returned no exact ATP witness pairs. "
            + (" | ".join(bridge_errors[:3]) if bridge_errors else "")
        )

    bridge = pd.concat(bridge_frames, ignore_index=True).drop_duplicates()
    bridge.to_csv(BRIDGE_OUT, index=False)

    witness_pairs = set(zip(witness["record_id"].astype(str), witness["gers_id"].astype(str)))
    bridge_pairs = set(zip(bridge["record_id"].astype(str), bridge["gers_id"].astype(str)))
    exact_pairs = len(witness_pairs & bridge_pairs)
    bridge_coverage = exact_pairs / max(1, len(witness_pairs))

    emit()
    emit("===== AUGUST BRIDGE REPLAY =====")
    emit(f"WITNESS_EXACT_PAIRS={len(witness_pairs)}")
    emit(f"BRIDGE_EXACT_PAIRS={exact_pairs}")
    emit(f"BRIDGE_EXACT_PAIR_COVERAGE={bridge_coverage:.9f}")
    emit(f"BRIDGE_REPLAY={BRIDGE_OUT}|SHA256={sha256_file(BRIDGE_OUT)}")

    if bridge_coverage != 1.0:
        fail(
            f"bridge exact-pair coverage {bridge_coverage:.9f} != 1.000000000",
            status="METHOD_UNRESOLVED"
        )

    # Freeze ATP historical run metadata, still without opening any output/source phones.
    try:
        raw_history = fetch_bytes(ATP_HISTORY_URL)
    except Exception as exc:
        fail(
            f"AllThePlaces history metadata retrieval failed: {exc}",
            status="METHOD_UNRESOLVED"
        )

    HISTORY_OUT.write_bytes(raw_history)
    hh = sha256_file(HISTORY_OUT)
    emit()
    emit("===== ALLTHEPLACES HISTORY METADATA =====")
    emit(f"ATP_HISTORY={ATP_HISTORY_URL}|SHA256={hh}|BYTES={len(raw_history)}")

    try:
        hobj = json.loads(raw_history.decode("utf-8"))
    except Exception as exc:
        fail(f"ATP history JSON parse failed: {exc}", status="METHOD_UNRESOLVED")

    runs = flatten_runs(hobj)
    if not runs:
        fail("ATP history endpoint yielded no run list", status="METHOD_UNRESOLVED")

    # Save only metadata around the relevant release window for inspection.
    summary_rows = []
    for r in runs:
        start = clean(r.get("start_time"))
        end = clean(r.get("end_time"))
        edt = parse_dt(end)
        if edt and datetime(2026,6,1,tzinfo=timezone.utc) <= edt <= datetime(2026,8,20,tzinfo=timezone.utc):
            summary_rows.append({
                "run_id": clean(r.get("run_id")),
                "start_time": start,
                "end_time": end,
                "output_url": clean(r.get("output_url")),
                "size_bytes": r.get("size_bytes"),
                "spiders": r.get("spiders"),
                "total_lines": r.get("total_lines"),
            })
    hs = pd.DataFrame(summary_rows)
    hs.to_csv(HISTORY_SUMMARY_OUT, index=False)
    emit(
        f"ATP_HISTORY_WINDOW_RUNS={len(hs)}|"
        f"OUTPUT={HISTORY_SUMMARY_OUT}|SHA256={sha256_file(HISTORY_SUMMARY_OUT)}"
    )

    # Resolve source run prospectively from native/bridge provenance tokens only.
    combined_meta = witness.copy()
    # Bridge can provide version/resource even if challenge source struct did not.
    if len(bridge):
        bmeta = bridge[["record_id","gers_id","resource","version","update_time"]].copy()
        bmeta = bmeta.rename(columns={"version":"bridge_version","resource":"bridge_resource",
                                      "update_time":"bridge_update_time"})
        combined_meta = combined_meta.merge(
            bmeta, on=["record_id","gers_id"], how="left"
        )
        combined_meta["bridge_version"] = combined_meta["bridge_version"].fillna("")
        combined_meta["bridge_resource"] = combined_meta["bridge_resource"].fillna("")
        # Fold bridge metadata into token search without altering source-link universe.
        temp = combined_meta.rename(
            columns={"bridge_version":"source_version","bridge_resource":"resource"}
        )[["source_version","resource"]]
        tokens = provenance_tokens(witness) | provenance_tokens(temp)
    else:
        tokens = provenance_tokens(witness)

    resolved, method = exact_run_resolution(runs, tokens)

    if resolved is None:
        emit("ATP_SOURCE_SNAPSHOT_IDENTITY=UNRESOLVED")
        emit("ATP_SOURCE_SNAPSHOT_RESOLUTION_METHOD=UNRESOLVED")
        emit("PHONE_OUTCOME_READ=NO")
        emit("ATP_PHONE_P0B_AUTHORIZED=NO")

        manifest = {
            "version": VERSION,
            "status": "METHOD_UNRESOLVED",
            "phone_outcome_read": False,
            "support": {
                "source_records": int(source_records),
                "tracts": int(tracts),
                "regions": int(regions),
                "membership_ambiguity_share": float(ambiguity_share),
                "bridge_exact_pair_coverage": float(bridge_coverage),
            },
            "history_sha256": hh,
            "outputs": {},
        }
        for p in (SOURCE_ROWS_OUT,WITNESS_OUT,BRIDGE_OUT,SOURCE_META_OUT,HISTORY_SUMMARY_OUT):
            manifest["outputs"][p.name] = {"path": str(p), "sha256": sha256_file(p)}
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        emit(f"MANIFEST={MANIFEST}|SHA256={sha256_file(MANIFEST)}")
        emit("ATP_PHONE_P0A=METHOD_UNRESOLVED")
        emit(
            "NEXT=ADJUDICATE SOURCE-VINTAGE PROVENANCE ONLY. "
            "DO NOT OPEN ATP OR OVERTURE PHONE VALUES."
        )
        return

    run_id = clean(resolved.get("run_id"))
    emit(f"ATP_SOURCE_SNAPSHOT_IDENTITY=RESOLVED")
    emit(f"ATP_SOURCE_SNAPSHOT_RUN_ID={run_id}")
    emit(f"ATP_SOURCE_SNAPSHOT_RESOLUTION_METHOD={method}")
    emit(f"ATP_SOURCE_SNAPSHOT_START={clean(resolved.get('start_time'))}")
    emit(f"ATP_SOURCE_SNAPSHOT_END={clean(resolved.get('end_time'))}")
    emit(f"ATP_SOURCE_SNAPSHOT_OUTPUT_URL={clean(resolved.get('output_url'))}")
    emit("PHONE_OUTCOME_READ=NO")

    manifest = {
        "version": VERSION,
        "status": "PASS",
        "phone_outcome_read": False,
        "overture_release": "2026-08-19.0",
        "atp_snapshot": {
            "run_id": run_id,
            "resolution_method": method,
            "start_time": clean(resolved.get("start_time")),
            "end_time": clean(resolved.get("end_time")),
            "output_url": clean(resolved.get("output_url")),
            "history_sha256": hh,
        },
        "support": {
            "source_records": int(source_records),
            "tracts": int(tracts),
            "regions": int(regions),
            "membership_ambiguity_share": float(ambiguity_share),
            "bridge_exact_pair_coverage": float(bridge_coverage),
        },
        "outputs": {},
    }
    for p in (SOURCE_ROWS_OUT,WITNESS_OUT,BRIDGE_OUT,SOURCE_META_OUT,HISTORY_SUMMARY_OUT):
        manifest["outputs"][p.name] = {"path": str(p), "sha256": sha256_file(p)}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    emit(f"MANIFEST={MANIFEST}|SHA256={sha256_file(MANIFEST)}")
    emit("ATP_PHONE_P0A=PASS")
    emit("ATP_PHONE_P0B_AUTHORIZED=YES")
    emit(
        "NEXT=FREEZE P0B PHONE NORMALIZATION + SOURCE FILE BYTES + "
        "SYMMETRIC PRESERVED/LOST AUDIT BEFORE READING PHONE OUTCOMES."
    )

if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sys
import urllib.request
import zipfile

import duckdb
import ijson
import numpy as np
import pandas as pd

VERSION = "ATP-PHONE-P0B-1.0"
AUDIT_SALT = "ATP_PHONE_P0B_AUDIT_v1"

ROOT = Path(os.environ.get("ATP_PHONE_ROOT", str(Path.cwd() / "atp_run"))).resolve()
OUT = ROOT / "outputs"
INSPECT = ROOT / "inspections"
STATE = INSPECT / "ATP-PHONE-P0B-state"
P0A_STATE = INSPECT / "ATP-PHONE-P0A-state"

P0A_MANIFEST = INSPECT / "ATP-PHONE-P0A-manifest.json"
P0A_MANIFEST_SHA = os.environ.get("ATP_PHONE_P0A_MANIFEST_SHA", "AA378B770DDC30E626C4CF74FAFD1DE36765782BE1E7DB45DDC34103032921C4")
P0A_SOURCE_LINKS = OUT / "ATP-PHONE-P0A-exact-source-links.csv"

ATP_RUN_ID = "2026-08-01-13-32-15"
ATP_OUTPUT_URL = (
    "https://alltheplaces-data.openaddresses.io/runs/"
    "2026-08-01-13-32-15/output.zip"
)
ATP_ZIP = STATE / f"alltheplaces-{ATP_RUN_ID}-output.zip"

CHALLENGE_BASE = (
    "s3://us-west-2.opendata.source.coop/"
    "humane-intelligence/bias-bounty-mapping-equity-challenge"
)

REGIONS = (
    "eastern-ok",
    "maricopa-az",
    "northern-ca",
    "south-central-tx",
    "eastern-wa",
)

PREREG_NAME = "ATP_PHONE_P0B_TRANSFER_DEFECT_PREREGISTRATION_v1.0.txt"
EXPECTED_PREREG_SHA = "D433B931914582774B2AA6DCD9F99B088A6DCAC55309A1E88C6ED06455BA3AF2"

MIN_SNAPSHOT_MATCH = 0.99
MIN_ELIGIBLE = 60
MIN_TRACTS = 10
MIN_REGIONS = 2
MAX_SOURCE_UNPARSEABLE = 0.05
MIN_REAL_NATIVE_CONTROLS = 20

MIN_NOT_PRESERVED = 12
MIN_NOT_PRESERVED_SHARE = 0.20
MIN_LOSS_TRACTS = 5
MIN_LOSS_REGIONS = 2

REPORT = INSPECT / "ATP-PHONE-P0B-transfer-defect-report.txt"
SOURCE_MATCH_OUT = OUT / "ATP-PHONE-P0B-atp-snapshot-match.csv"
SOURCE_PHONE_OUT = OUT / "ATP-PHONE-P0B-frozen-source-phone-universe.csv"
FULL_RESULTS_OUT = OUT / "ATP-PHONE-P0B-transfer-results.csv"
REGION_SUMMARY_OUT = INSPECT / "ATP-PHONE-P0B-region-summary.csv"
AUDIT_OUT = OUT / "ATP-PHONE-P0B-symmetric-audit.csv"
MANIFEST = INSPECT / "ATP-PHONE-P0B-manifest.json"

OVERTURE_PHONE_OUTCOME_READ = False

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

def clean(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except Exception:
        pass
    return str(v).strip()

def fail(msg: str, status="FAIL"):
    emit(f"ATP_PHONE_P0B={status}")
    emit("ATP_PHONE_P0C_AUTHORIZED=NO")
    emit(f"FAIL_REASON={msg}")
    raise RuntimeError(msg)

def q(v: str) -> str:
    return str(v).replace("'", "''")

def download_resume(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = dest.stat().st_size if dest.exists() else 0
    headers = {"User-Agent": "bias-bounty-atp-phone-p0b/1.0"}
    mode = "wb"
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        code = getattr(r, "status", None) or r.getcode()
        if existing > 0 and code != 206:
            existing = 0
            mode = "wb"
        total_header = r.headers.get("Content-Length")
        incoming = int(total_header) if total_header and total_header.isdigit() else None
        with dest.open(mode) as f:
            downloaded = existing
            next_mark = ((downloaded // (100*1024*1024)) + 1) * (100*1024*1024)
            while True:
                b = r.read(1024*1024)
                if not b:
                    break
                f.write(b)
                downloaded += len(b)
                if downloaded >= next_mark:
                    emit(f"ATP_ZIP_DOWNLOAD_PROGRESS_BYTES={downloaded}")
                    next_mark += 100*1024*1024

def remove_extension(s: str) -> str:
    # Strip common trailing extension notation only.
    return re.sub(
        r"(?i)\s*(?:ext(?:ension)?\.?|x)\s*[:.]?\s*\d+\s*$",
        "",
        s.strip()
    )

def split_phone_values(v: str):
    if v is None:
        return []
    s = str(v).strip()
    if not s:
        return []
    return [x.strip() for x in s.split(";") if x.strip()]

def canon_one(v) -> str | None:
    if v is None:
        return None
    s = remove_extension(str(v))
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return None

def canon_source_phone(raw: str):
    vals = split_phone_values(raw)
    out = []
    for v in vals:
        c = canon_one(v)
        if c and c not in out:
            out.append(c)
    return out

def recursive_scalars(obj):
    if obj is None:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from recursive_scalars(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from recursive_scalars(v)
    elif isinstance(obj, (str, int, float)):
        yield obj

def parse_overture_phone_json(raw_json: str):
    raw_json = clean(raw_json)
    if not raw_json or raw_json.lower() in ("null", "nan", "none", "[]", "{}"):
        return [], []
    try:
        obj = json.loads(raw_json)
    except Exception:
        obj = raw_json
    scalars = [str(x).strip() for x in recursive_scalars(obj) if str(x).strip()]
    cans = []
    for scalar in scalars:
        # Native arrays normally hold one number per element, but allow ATP-like
        # semicolon lists defensively.
        for part in split_phone_values(scalar):
            c = canon_one(part)
            if c and c not in cans:
                cans.append(c)
    return scalars, cans

def parser_selftest():
    fixtures = [
        ("+1 210-555-1212", {"2105551212"}),
        ("1 (602) 555-0100", {"6025550100"}),
        ("415-555-9999 ext. 22", {"4155559999"}),
        ("+1 509 555 4444; +1 509 555 5555", {"5095554444","5095555555"}),
    ]
    for raw, expected in fixtures:
        got = set(canon_source_phone(raw))
        if got != expected:
            return False, f"source fixture {raw!r} expected={expected} got={got}"
    native = json.dumps(["+1-210-555-1212", {"value": "(602) 555-0100"}])
    _, got = parse_overture_phone_json(native)
    if set(got) != {"2105551212","6025550100"}:
        return False, f"native recursive fixture failed got={got}"
    return True, "PASS"

def setup():
    con = duckdb.connect(database=":memory:")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-west-2'")
    con.execute("SET s3_url_style='path'")
    con.execute("SET threads TO 2")
    con.execute("SET memory_limit='4GB'")
    return con

def load_parent_manifest():
    if not P0A_MANIFEST.exists():
        fail(f"missing P0A manifest {P0A_MANIFEST}")
    actual = sha256_file(P0A_MANIFEST)
    emit(f"P0A_MANIFEST={P0A_MANIFEST}|SHA256={actual}")
    if actual != P0A_MANIFEST_SHA:
        fail(f"P0A manifest hash mismatch expected={P0A_MANIFEST_SHA} actual={actual}")
    m = json.loads(P0A_MANIFEST.read_text(encoding="utf-8"))
    if m.get("status") != "PASS":
        fail(f"P0A manifest status is not PASS: {m.get('status')}")
    if m.get("phone_outcome_read") is not False:
        fail("P0A manifest does not certify phone_outcome_read=false")
    snap = m.get("atp_snapshot", {})
    if snap.get("run_id") != ATP_RUN_ID:
        fail(f"P0A snapshot run mismatch: {snap.get('run_id')}")
    # Verify all paths/hashes recorded by parent manifest.
    for name, meta in m.get("outputs", {}).items():
        p = Path(meta["path"])
        if not p.exists():
            fail(f"missing P0A output {name}: {p}")
        h = sha256_file(p)
        if h != meta["sha256"]:
            fail(f"P0A output hash mismatch {name} expected={meta['sha256']} actual={h}")
    return m

def scan_atp_zip(target_ids: set[str]):
    found = {}
    member_count = 0
    feature_count = 0
    with zipfile.ZipFile(ATP_ZIP, "r") as z:
        members = [
            n for n in z.namelist()
            if n.lower().endswith((".geojson", ".json"))
            and not n.endswith("/")
        ]
        emit(f"ATP_ZIP_CANDIDATE_JSON_MEMBERS={len(members)}")
        for name in members:
            member_count += 1
            try:
                with z.open(name, "r") as f:
                    # ATP spider output is documented as GeoJSON FeatureCollection.
                    for feat in ijson.items(f, "features.item"):
                        feature_count += 1
                        fid = clean(feat.get("id"))
                        if fid not in target_ids:
                            continue
                        props = feat.get("properties") or {}
                        found[fid] = {
                            "record_id": fid,
                            "spider": clean(props.get("@spider")),
                            "source_uri": clean(props.get("@source_uri")),
                            "name": clean(props.get("name")),
                            "brand": clean(props.get("brand")),
                            "source_phone_raw": clean(props.get("phone")),
                            "source_country": clean(props.get("addr:country")),
                        }
            except (ijson.common.JSONError, UnicodeDecodeError):
                # Non-GeoJSON JSON members are ignored only if they cannot parse as a
                # FeatureCollection. They never count as source matches.
                continue
            if member_count % 250 == 0:
                emit(
                    f"ATP_SCAN_PROGRESS=members:{member_count}/{len(members)}|"
                    f"target_ids_found:{len(found)}/{len(target_ids)}"
                )
    emit(f"ATP_SCAN_FEATURES_VISITED={feature_count}")
    return found

def audit_hash(record_id, gers_id):
    return hashlib.sha256(
        f"{AUDIT_SALT}|{record_id}|{gers_id}".encode("utf-8")
    ).hexdigest()

def main():
    global OVERTURE_PHONE_OUTCOME_READ

    OUT.mkdir(parents=True, exist_ok=True)
    INSPECT.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    for p in (
        REPORT, SOURCE_MATCH_OUT, SOURCE_PHONE_OUT, FULL_RESULTS_OUT,
        REGION_SUMMARY_OUT, AUDIT_OUT, MANIFEST
    ):
        p.unlink(missing_ok=True)

    emit("===== ATP-PHONE-P0B — EXACT SOURCE-LINKED PHONE TRANSFER DEFECT SCREEN =====")
    emit(f"VERSION={VERSION}|PYTHON={sys.version.split()[0]}|DUCKDB={duckdb.__version__}|IJSON={getattr(ijson,'__version__','unknown')}")
    emit("PARENT=ATP-PHONE-P0A")
    emit("ATP_RUN_ID=" + ATP_RUN_ID)
    emit("OVERTURE_PHONE_OUTCOME_READ=NO")
    emit("SVI_OR_DEMOGRAPHIC_OUTCOME_READ=NO")
    emit("CATEGORY_OR_SERVICE_ROLE_OUTCOME_READ=NO")
    emit("FUZZY_OR_PROXIMITY_ENTITY_MATCHING=NO")
    emit()

    prereg = Path(__file__).resolve().parent / PREREG_NAME
    if not prereg.exists():
        fail(f"missing preregistration {prereg}")
    ph = sha256_file(prereg)
    emit(f"PREREGISTRATION={prereg}|SHA256={ph}")
    if ph != EXPECTED_PREREG_SHA:
        fail(f"prereg hash mismatch expected={EXPECTED_PREREG_SHA} actual={ph}")

    parent = load_parent_manifest()

    if not P0A_SOURCE_LINKS.exists():
        fail(f"missing exact P0A source links {P0A_SOURCE_LINKS}")

    emit()
    emit("===== FREEZING EXACT ATP SOURCE ZIP BYTES =====")
    emit(f"ATP_OUTPUT_URL={ATP_OUTPUT_URL}")
    if not ATP_ZIP.exists():
        emit("ATP_ZIP_LOCAL_CACHE=MISS")
        download_resume(ATP_OUTPUT_URL, ATP_ZIP)
    else:
        emit(f"ATP_ZIP_LOCAL_CACHE=HIT|BYTES={ATP_ZIP.stat().st_size}")
    if not zipfile.is_zipfile(ATP_ZIP):
        fail(f"downloaded ATP source is not a valid ZIP: {ATP_ZIP}", status="METHOD_UNRESOLVED")
    atp_zip_hash = sha256_file(ATP_ZIP)
    emit(f"ATP_SOURCE_ZIP={ATP_ZIP}")
    emit(f"ATP_SOURCE_ZIP_BYTES={ATP_ZIP.stat().st_size}")
    emit(f"ATP_SOURCE_ZIP_SHA256={atp_zip_hash}")
    emit("ATP_SOURCE_BYTES_FROZEN=YES")
    emit("OVERTURE_PHONE_OUTCOME_READ=NO")

    p0a = pd.read_csv(
        P0A_SOURCE_LINKS,
        dtype={"record_id":str,"gers_id":str,"GEOID":str,"region":str}
    )
    p0a["record_id"] = p0a["record_id"].astype(str)
    p0a["gers_id"] = p0a["gers_id"].astype(str)
    p0a["GEOID"] = p0a["GEOID"].astype(str).str.zfill(11)

    target_ids = set(p0a["record_id"])
    emit(f"FROZEN_P0A_SOURCE_IDS={len(target_ids)}")

    found = scan_atp_zip(target_ids)

    match = p0a.merge(
        pd.DataFrame(found.values()) if found else pd.DataFrame(columns=["record_id"]),
        on="record_id",
        how="left",
        validate="many_to_one"
    )
    match["snapshot_found"] = match["spider"].fillna("").astype(str).ne("")
    match.to_csv(SOURCE_MATCH_OUT, index=False)

    distinct_found = match.loc[match["snapshot_found"], "record_id"].nunique()
    match_coverage = distinct_found / max(1, len(target_ids))

    emit()
    emit("===== EXACT SNAPSHOT MATCH =====")
    emit(f"P0A_SOURCE_IDS={len(target_ids)}")
    emit(f"EXACT_ATP_IDS_FOUND={distinct_found}")
    emit(f"EXACT_ATP_SNAPSHOT_MATCH_COVERAGE={match_coverage:.9f}")
    emit(f"SNAPSHOT_MATCH_TABLE={SOURCE_MATCH_OUT}|SHA256={sha256_file(SOURCE_MATCH_OUT)}")

    if match_coverage < MIN_SNAPSHOT_MATCH:
        fail(
            f"snapshot exact-ID coverage {match_coverage:.9f} < {MIN_SNAPSHOT_MATCH:.9f}",
            status="METHOD_UNRESOLVED"
        )

    matched = match[match["snapshot_found"]].copy()
    matched["source_phone_nonblank"] = (
        matched["source_phone_raw"].fillna("").astype(str).str.strip().ne("")
    )
    matched["source_phone_canonical"] = matched["source_phone_raw"].apply(
        lambda x: "|".join(canon_source_phone(clean(x)))
    )
    matched["source_phone_valid"] = matched["source_phone_canonical"].str.strip().ne("")

    nonblank = matched[matched["source_phone_nonblank"]]
    eligible = matched[matched["source_phone_valid"]].copy()
    unparseable_count = int(
        (nonblank["source_phone_nonblank"] & ~nonblank["source_phone_valid"]).sum()
    )
    unparseable_share = unparseable_count / max(1, len(nonblank))

    eligible["audit_hash"] = [
        audit_hash(rid, gid)
        for rid, gid in zip(eligible["record_id"], eligible["gers_id"])
    ]
    eligible = eligible.sort_values(
        ["audit_hash","record_id","gers_id"], kind="mergesort"
    ).reset_index(drop=True)

    # Freeze exact source phone universe BEFORE native Overture phone inspection.
    source_cols = [
        "region","GEOID","record_id","gers_id","spider","source_uri",
        "name","brand","source_country","source_phone_raw",
        "source_phone_canonical","audit_hash"
    ]
    eligible[source_cols].to_csv(SOURCE_PHONE_OUT, index=False)
    source_phone_hash = sha256_file(SOURCE_PHONE_OUT)

    emit()
    emit("===== SOURCE PHONE SUPPORT — STILL BEFORE OVERTURE PHONE READ =====")
    emit(f"MATCHED_ATP_RECORDS={matched['record_id'].nunique()}")
    emit(f"MATCHED_NONBLANK_SOURCE_PHONE_ROWS={len(nonblank)}")
    emit(f"SOURCE_PHONE_UNPARSEABLE_ROWS={unparseable_count}")
    emit(f"SOURCE_PHONE_UNPARSEABLE_SHARE={unparseable_share:.9f}")
    emit(f"SOURCE_ELIGIBLE_VALID_NANP_ROWS={len(eligible)}")
    emit(f"SOURCE_ELIGIBLE_TRACTS={eligible['GEOID'].nunique()}")
    emit(f"SOURCE_ELIGIBLE_REGIONS={eligible['region'].nunique()}")
    emit(f"SOURCE_PHONE_UNIVERSE={SOURCE_PHONE_OUT}|SHA256={source_phone_hash}")
    emit("SOURCE_PHONE_UNIVERSE_FROZEN=YES")
    emit("OVERTURE_PHONE_OUTCOME_READ=NO")

    if (
        len(eligible) < MIN_ELIGIBLE
        or eligible["GEOID"].nunique() < MIN_TRACTS
        or eligible["region"].nunique() < MIN_REGIONS
        or unparseable_share > MAX_SOURCE_UNPARSEABLE
    ):
        fail(
            "source phone support gate failed: "
            f"eligible={len(eligible)}/{MIN_ELIGIBLE}, "
            f"tracts={eligible['GEOID'].nunique()}/{MIN_TRACTS}, "
            f"regions={eligible['region'].nunique()}/{MIN_REGIONS}, "
            f"unparseable_share={unparseable_share:.6f}/{MAX_SOURCE_UNPARSEABLE:.6f}"
        )

    ok, why = parser_selftest()
    emit(f"PHONE_PARSER_SELFTEST={'PASS' if ok else 'FAIL'}|DETAIL={why}")
    if not ok:
        fail("phone parser self-test failed")

    # Only NOW read native phone fields.
    OVERTURE_PHONE_OUTCOME_READ = True
    emit()
    emit("===== OVERTURE PHONE READ AUTHORIZED BY SOURCE FREEZE =====")
    emit("OVERTURE_PHONE_OUTCOME_READ=YES")
    emit("SVI_OR_DEMOGRAPHIC_OUTCOME_READ=NO")
    emit("CATEGORY_OR_SERVICE_ROLE_OUTCOME_READ=NO")

    con = setup()

    # Register exact eligible GERS/record pairs.
    exact_pairs = eligible[["region","record_id","gers_id"]].copy()
    con.register("eligible_pairs", exact_pairs)

    frames = []
    real_control_count = 0

    for region in REGIONS:
        poi_url = f"{CHALLENGE_BASE}/reference/{region}/{region}-overture-pois.parquet"
        desc = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{q(poi_url)}')"
        ).fetchdf()
        cols = set(desc["column_name"].astype(str))
        if "phones" not in cols:
            fail(f"{region}: challenge POI schema has no phones column")

        reg = con.execute(
            f"""
            SELECT
                e.region,
                e.record_id,
                e.gers_id,
                to_json(p.phones) AS overture_phones_json
            FROM eligible_pairs e
            JOIN read_parquet('{q(poi_url)}') p
              ON CAST(p.id AS VARCHAR) = e.gers_id
            WHERE e.region = '{q(region)}'
            """
        ).fetchdf()
        frames.append(reg)

        # Real field/parser control outside the ATP transfer classification.
        ctl = con.execute(
            f"""
            SELECT to_json(phones) AS phones_json
            FROM read_parquet('{q(poi_url)}')
            WHERE phones IS NOT NULL
            LIMIT 100
            """
        ).fetchdf()
        for raw in ctl["phones_json"].astype(str):
            _, cans = parse_overture_phone_json(raw)
            if cans:
                real_control_count += 1

    native = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    retrieved_pairs = set(zip(native["record_id"].astype(str), native["gers_id"].astype(str)))
    expected_pairs = set(zip(eligible["record_id"].astype(str), eligible["gers_id"].astype(str)))
    entity_coverage = len(expected_pairs & retrieved_pairs) / max(1, len(expected_pairs))

    emit(f"EXACT_ELIGIBLE_GERS_PAIR_COVERAGE={entity_coverage:.9f}")
    emit(f"REAL_NATIVE_VALID_PHONE_CONTROLS={real_control_count}")

    if entity_coverage != 1.0:
        fail(f"exact eligible GERS retrieval coverage {entity_coverage:.9f} != 1.0")
    if real_control_count < MIN_REAL_NATIVE_CONTROLS:
        fail(
            f"native valid-phone parser controls {real_control_count} < "
            f"{MIN_REAL_NATIVE_CONTROLS}"
        )

    res = eligible.merge(
        native,
        on=["region","record_id","gers_id"],
        how="left",
        validate="one_to_one"
    )

    raw_scalars = []
    overture_canon = []
    statuses = []

    for row in res.itertuples(index=False):
        scalars, cans = parse_overture_phone_json(row.overture_phones_json)
        raw_scalars.append(" || ".join(scalars))
        overture_canon.append("|".join(cans))

        src = {x for x in str(row.source_phone_canonical).split("|") if x}
        nat = set(cans)

        if src & nat:
            status = "PRESERVED"
        elif not scalars and not nat:
            status = "ABSENT_ALL_NATIVE_PHONES"
        elif scalars and not nat:
            status = "OVERTURE_PHONE_UNPARSEABLE"
        else:
            status = "ATP_VALUE_NOT_PRESERVED_OTHER_NATIVE_PHONE"
        statuses.append(status)

    res["overture_phone_raw_scalars"] = raw_scalars
    res["overture_phone_canonical"] = overture_canon
    res["transfer_status"] = statuses
    res["not_preserved"] = res["transfer_status"].ne("PRESERVED")
    res.to_csv(FULL_RESULTS_OUT, index=False)

    total = len(res)
    lost = res[res["not_preserved"]]
    loss_n = len(lost)
    loss_share = loss_n / max(1, total)
    loss_tracts = lost["GEOID"].nunique()
    loss_regions = lost["region"].nunique()

    status_counts = res["transfer_status"].value_counts().to_dict()

    region_summary = (
        res.groupby("region", as_index=False)
        .agg(
            eligible_records=("record_id","size"),
            not_preserved=("not_preserved","sum"),
            tracts=("GEOID","nunique"),
        )
    )
    region_summary["not_preserved_share"] = (
        region_summary["not_preserved"] / region_summary["eligible_records"]
    )
    region_summary.to_csv(REGION_SUMMARY_OUT, index=False)

    # Deterministic symmetric audit packet.
    audit_parts = []
    classes = [
        "PRESERVED",
        "ABSENT_ALL_NATIVE_PHONES",
        "ATP_VALUE_NOT_PRESERVED_OTHER_NATIVE_PHONE",
        "OVERTURE_PHONE_UNPARSEABLE",
    ]
    for cls in classes:
        sub = res[res["transfer_status"] == cls].sort_values(
            ["audit_hash","record_id","gers_id"], kind="mergesort"
        ).head(20)
        audit_parts.append(sub)
    audit = pd.concat(audit_parts, ignore_index=True) if audit_parts else pd.DataFrame()
    audit.to_csv(AUDIT_OUT, index=False)

    emit()
    emit("===== ATP-PHONE-P0B TRANSFER RESULT =====")
    emit(f"ELIGIBLE_EXACT_SOURCE_RECORDS={total}")
    emit(f"PRESERVED={status_counts.get('PRESERVED',0)}")
    emit(f"ABSENT_ALL_NATIVE_PHONES={status_counts.get('ABSENT_ALL_NATIVE_PHONES',0)}")
    emit(
        "ATP_VALUE_NOT_PRESERVED_OTHER_NATIVE_PHONE="
        f"{status_counts.get('ATP_VALUE_NOT_PRESERVED_OTHER_NATIVE_PHONE',0)}"
    )
    emit(
        "OVERTURE_PHONE_UNPARSEABLE="
        f"{status_counts.get('OVERTURE_PHONE_UNPARSEABLE',0)}"
    )
    emit(f"NOT_PRESERVED={loss_n}")
    emit(f"NOT_PRESERVED_SHARE={loss_share:.9f}")
    emit(f"NOT_PRESERVED_TRACTS={loss_tracts}")
    emit(f"NOT_PRESERVED_REGIONS={loss_regions}")

    for r in region_summary.itertuples(index=False):
        emit(
            f"REGION={r.region}|eligible={r.eligible_records}|"
            f"not_preserved={int(r.not_preserved)}|"
            f"share={r.not_preserved_share:.9f}|tracts={r.tracts}"
        )

    gate_a = True
    gate_b = match_coverage >= MIN_SNAPSHOT_MATCH
    gate_c = (
        len(eligible) >= MIN_ELIGIBLE
        and eligible["GEOID"].nunique() >= MIN_TRACTS
        and eligible["region"].nunique() >= MIN_REGIONS
        and unparseable_share <= MAX_SOURCE_UNPARSEABLE
    )
    gate_d = SOURCE_PHONE_OUT.exists() and bool(source_phone_hash)
    gate_e = (
        entity_coverage == 1.0
        and ok
        and real_control_count >= MIN_REAL_NATIVE_CONTROLS
    )
    gate_f = (
        loss_n >= MIN_NOT_PRESERVED
        and loss_share >= MIN_NOT_PRESERVED_SHARE
        and loss_tracts >= MIN_LOSS_TRACTS
        and loss_regions >= MIN_LOSS_REGIONS
    )

    emit()
    emit("===== FROZEN P0B GATES =====")
    emit(f"GATE_A_PARENT_SOURCE_INTEGRITY={'PASS' if gate_a else 'FAIL'}")
    emit(f"GATE_B_EXACT_SNAPSHOT_MATCH={'PASS' if gate_b else 'FAIL'}")
    emit(f"GATE_C_PHONE_SUPPORT={'PASS' if gate_c else 'FAIL'}")
    emit(f"GATE_D_SOURCE_UNIVERSE_FREEZE={'PASS' if gate_d else 'FAIL'}")
    emit(f"GATE_E_OVERTURE_ENTITY_PARSER_CONTROL={'PASS' if gate_e else 'FAIL'}")
    emit(f"GATE_F_TRANSFER_DEFECT={'PASS' if gate_f else 'FAIL'}")

    overall = all([gate_a,gate_b,gate_c,gate_d,gate_e,gate_f])

    manifest = {
        "version": VERSION,
        "parent_manifest_sha256": P0A_MANIFEST_SHA,
        "atp_run_id": ATP_RUN_ID,
        "atp_source_zip": {
            "path": str(ATP_ZIP),
            "bytes": ATP_ZIP.stat().st_size,
            "sha256": atp_zip_hash,
        },
        "source_snapshot_match_coverage": float(match_coverage),
        "source_unparseable_share": float(unparseable_share),
        "eligible_records": int(total),
        "not_preserved": int(loss_n),
        "not_preserved_share": float(loss_share),
        "not_preserved_tracts": int(loss_tracts),
        "not_preserved_regions": int(loss_regions),
        "status_counts": {k:int(v) for k,v in status_counts.items()},
        "gates": {
            "A_parent_source_integrity": gate_a,
            "B_exact_snapshot_match": gate_b,
            "C_phone_support": gate_c,
            "D_source_universe_freeze": gate_d,
            "E_overture_entity_parser_control": gate_e,
            "F_transfer_defect": gate_f,
        },
        "overall_pass": overall,
        "p0c_authorized": overall,
        "demographic_or_category_outcomes_read": False,
        "outputs": {},
    }
    for p in (
        SOURCE_MATCH_OUT, SOURCE_PHONE_OUT, FULL_RESULTS_OUT,
        REGION_SUMMARY_OUT, AUDIT_OUT
    ):
        manifest["outputs"][p.name] = {
            "path": str(p),
            "sha256": sha256_file(p),
            "bytes": p.stat().st_size,
        }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    emit()
    emit(f"FULL_RESULTS={FULL_RESULTS_OUT}|SHA256={sha256_file(FULL_RESULTS_OUT)}")
    emit(f"REGION_SUMMARY={REGION_SUMMARY_OUT}|SHA256={sha256_file(REGION_SUMMARY_OUT)}")
    emit(f"SYMMETRIC_AUDIT={AUDIT_OUT}|SHA256={sha256_file(AUDIT_OUT)}")
    emit(f"MANIFEST={MANIFEST}|SHA256={sha256_file(MANIFEST)}")
    emit("SVI_OR_DEMOGRAPHIC_OUTCOME_READ=NO")
    emit("CATEGORY_OR_SERVICE_ROLE_OUTCOME_READ=NO")

    if overall:
        emit("ATP_PHONE_P0B=PASS")
        emit("ATP_PHONE_P0C_AUTHORIZED=YES")
        emit(
            "NEXT=FREEZE P0C SOURCE-REDUNDANCY / NO-NATIVE-PHONE / "
            "DISPARITY CHARACTERIZATION BEFORE OPENING THOSE OUTCOMES."
        )
    else:
        emit("ATP_PHONE_P0B=FAIL")
        emit("ATP_PHONE_P0C_AUTHORIZED=NO")
        emit(
            "NEXT=RETIRE ATP PHONE-TRANSFER ROUTE FOR CURRENT CHAMPIONSHIP WINDOW. "
            "NO CATEGORY/GEOGRAPHY/SVI RESCUE."
        )

if __name__ == "__main__":
    main()

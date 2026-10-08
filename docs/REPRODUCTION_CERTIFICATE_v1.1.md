# ATP-PHONE v1.1 — Reproduction and publication certificate

**Date:** 8 October 2026. **Environment:** User Windows PowerShell, `py -3.12` with dependencies installed from pinned requirements. **Scope:** P0A -> P0B -> P0C -> P0D-A; no score reconstruction, no new scientific cohorts, no P0D-B live-currentness rerun.

## Source-to-output execution observed

- Fresh execution completed: `PIPELINE_FINISHED_STAGES=P0A,P0B,P0C,P0D-A`.
- P0D-A gates: parent integrity, taxonomy integrity, operational-role support, matched operational support, contactability severity, named anchor construction — all PASS.
- P0D-A operational matched output was byte-identical to original frozen output, as independently checked by subsequent audit.
- P0D-B anchor/currentness and live-competitor review were historically independently assessed in the 7 October P0E adversarial review. Their **original** outcomes, including the one conflicting/stale phone anchor, are preserved.

## Frozen-output equivalence audit — 2026-10-08 user log

Audit result: `AUDIT_GATE=PASS_FROZEN_OUTPUT_EQUIVALENCE`, exit code 0.

| Output comparison | Count | Interpretation |
|---|---:|---|
| `EXACT_BYTES_PASS` | 13 | Original and fresh result bytes equal |
| `SAME_ROWS_DIFFERENT_BYTES` | 3 | Exact row/key/value equivalence, serialization/order only |
| `SEMANTIC_DIFFERENCE_REVIEW` | 0 | No changed fields identified |
| `MISSING` or `READ_ERROR` | 0 | All expected outputs compared |

Three non-identical byte streams without field-level changes: P0A bridge replay (120 rows), P0C tract-burden (9,379 rows), and P0D-A operational-role losses (4,711 rows). **These are not 3 failed experiments.** The original independent review's critique of the TX tract-burden geographic membership *still applies* even though all rows match the historical burden file; this receipt does not repair that methodological limitation.

This receipt is grounded in the user's PowerShell execution output and the preserved offline audit verifier. It does **not** claim an independently run second machine or independently revalidated real-world phone currentness. A judge can reproduce the work by running the public code against documented public inputs.

## Frozen scientific totals and boundaries

- Exact historical AllThePlaces source links across five regions: **31,654**.
- Valid-form upstream source phones omitted in native August Overture `phones`: **22,437 five-region**, including **21,608 primary four-region** and **829 eastern-WA supplemental**.
- **6,505** primary deterministic matched pairs; **6,245** Meta-sourced control records had valid-form native phones, vs. **0** ATP-sourced exposed records.
- Preregistered operational-role losses: **4,711**, of which **3,682** are gas stations and **231** medical-role records. Medical-only matched control phone rate **42/49**, not the pooled operational matched rate.
- Neither source-conditioned matching nor native-field omission establishes successful calling, complete unreachability, causal ingestion effects, demographic exposure, or measured emergency harm.

## Public input and provenance fingerprints

- Overture challenge pinned release: `2026-08-19.0`.
- Exact historical ATP archive: `https://alltheplaces-data.openaddresses.io/runs/2026-08-01-13-32-15/output.zip`; original SHA-256: `15B46EA37C2BD5C4A15723D0E97B65CF7D3B2C7A0ACACE0132F250CC66D9819F`.
- AllThePlaces historical run history: `https://data.alltheplaces.xyz/runs/history.json`; frozen run end `2026-08-05T15:33:36Z`.
- Independent archive/bridge/POI replay is documented by the October 7 reviewer; the reviewer's standalone raw downloads did not rely on this local Windows run.
- Current official sample GEOID authority is distinct from tract polygon inventory; do not erase documented TX sample/polygon differences.

## Secret / sensitive publication gate

- The release candidate includes four audited portability-adapted Python runners, exact preregistrations, deterministic role taxonomy, static aggregate CSVs, full narrative and this receipt.
- It excludes full raw P0E evidence, joined phone/contact exports, credential-bearing raw source URLs, and local Windows run outputs.
- Three apparent phone strings in one runner are synthetic `555` test fixtures, not contacts obtained from the historical source.
- The final GitHub repository and generated final PDF still require public-link verification before the Google Form is submitted.

**Associated numerical Zindi entry:** `Kmiqz6te`. This is an administrative attachment for the separate Discovery form, **not** the source or model that produced the phone-omission findings.

# ATP-PHONE — Best Bias Discovery · Public release candidate v1.2

**Campaign:** Zindi Bias Bounty Mapping Equity Challenge (October 2026).  
**Research entry:** *When an Upstream Phone Number Does Not Reach the Map*.  
**Zindi username:** `chizzydev250`. **Associated numerical submission:** `Kmiqz6te` (V2-21; separately evaluated, reference-free).  
**Research stage:** P0A–P0D-A source-to-output fresh Windows rerun completed 2026-10-08, frozen output equivalence PASS across 16 checked CSVs (13 byte-identical; 3 semantically identical with different serialization/order); P0D-B/P0E historical independent review separately completed.  
**Public repository:** https://github.com/chizzydev/bias-bounty-atp-phone-2026 (created 2026-10-08; confirm the reviewed release files appear after pushing). **Do not submit the final Google Form PDF before verifying this public code link.**

The Discovery analysis is independent of the scored V2-21 numerical submission. This repository does not derive, reconstruct, approximate, train on, or calibrate withdrawn Zindi ground-truth targets. Any external ATP data are used exclusively to audit the *Best Bias Discovery* claim, not the scored output.

## Read first

- `docs/ATP_PHONE_BEST_BIAS_DISCOVERY.md` — complete submitted-science writeup and claim boundaries.
- `docs/REPRODUCTION_CERTIFICATE_v1.1.md` — observed full rerun and equivalence checks, limitations, input hashes, and source-packaging hygiene.
- `docs/SCRIPT_ORIGINS.json` — original frozen science runner SHA256 vs. pathname/parent-manifest portability adapters.

## Reproduce from public inputs

Python **3.12** recommended (tested fresh source-to-output rerun on Windows 11 using Python 3.12):

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 verify_frozen_summary.py
py -3.12 -u run_discovery.py --work-dir atp_run
```

Other operating systems may run using `python` instead of `py -3.12`; Windows is the verified run environment. The full pipeline downloads the exact dated public 2.95 GB ATP archive and other challenge inputs and needs substantial free disk space. Python dependencies are pinned in `requirements.txt`. The offline aggregate verifier does **not** replace the full raw-source pipeline.

The original P0A/P0B/P0C/P0D-A scientific criteria, preregistrations, source-ID links, role taxonomy, anchor cohort, and comparisons have not been changed. The adapter prints a generic conservative caution at the end; the successful 2026-10-08 Windows equivalence receipt is in `docs/REPRODUCTION_CERTIFICATE_v1.1.md`.

## Data and publication safety

Only aggregate CSVs and source/reproduction code are checked in. **Never commit** raw `atp_run/`, private P0E packets, frozen phone/contact tables, historical complete joined evidence, copied downloaded raw datasets, user-local config, or source URLs with embedded `key=` / token parameters. Outputs under `atp_run/` can contain phone numbers and must remain private unless individually reviewed and sanitized. The public code works from publicly licensed inputs under their respective terms; licenses and dates are documented in the writeup.

**Caution:** The finding is descriptive and source-conditioned. It does not establish clinical harm, contact inaccessibility, demographic disparity, intentional ingestion behavior, or a population-valid accuracy rate. See the primary document for adverse evidence including the Texas burden-universe defect and the single conflicting anchor.

# When an Upstream Phone Number Does Not Reach the Map

**A source-conditioned audit of missing native phone attributes in Overture Maps**

**Competition:** Zindi Bias Bounty Mapping Equity Challenge (2026), Best Bias Discovery  
**Participant:** `chizzydev250`  
**Associated numerical submission:** `Kmiqz6te` (an independent, reference-free prediction submission)  
**Overture release:** `2026-08-19.0`  
**AllThePlaces historical run:** `2026-08-01-13-32-15` (completed August 5, 2026)

## Research question

Can a map contain a point of interest yet omit a telephone attribute supplied by its version-matched upstream source, in a way that is invisible to aggregate coverage metrics?

This study links exact AllThePlaces (ATP) source identifiers to Overture GERS records in the fixed August challenge release, audits native `phones` fields, and compares ATP-sourced records with matched Meta-sourced records. The outcome is **native valid-form phone availability**, not verified real-world reachability.

## Principal results

| Measure | Four primary regions | Eastern Washington supplement | Five-package total |
|---|---:|---:|---:|
| Exact-linked records with a valid-form upstream phone and null native Overture `phones` | **21,608** | 829 | **22,437** |
| Deterministic matched pairs | **6,505** | 237 | 6,742 |

Within the **6,505 four-region matched pairs**, **6,245** Meta-sourced controls (96.0031%) expose a valid-form native phone, while **zero** ATP-sourced exposed records do. The matching was frozen before opening the phone outcomes. It conditions on the authoritative scored tract, primary category, recorded provenance-count bin, operating-status bin and structural brand-presence flag.

| Primary region | Native-phone omissions | Matched pairs | Phone-positive controls |
|---|---:|---:|---:|
| Eastern Oklahoma | 2,320 | 589 | 560 |
| Maricopa study package | 2,816 | 732 | 709 |
| Northern California | 1,159 | 318 | 307 |
| South-Central Texas | 15,313 | 4,866 | 4,669 |
| **Total** | **21,608** | **6,505** | **6,245** |

These are **descriptive, source-conditioned findings**. All exposed matched records derive place content from ATP and all controls from Meta; the difference is not an independently identified causal provider effect.

## Operational relevance

A prospectively specified service-role screen contains **4,711** omitted native phone fields among essential-supply and medical categories, including **3,682 gas stations** and **231 medical-role records**. The medical matched subset contains only **49 pairs**, with phones in **42** control records (85.71%).

A null native phone field can eliminate the direct calling action offered by applications using that field. This audit does **not** establish failed calls, inaccessible services, emergency delays, clinical harm, or a demographic disparity. Some POIs retain websites, email or social links; upstream phone strings have not all been validated for currency or branch ownership.

## Methods and reproducibility

The frozen procedure follows four executable stages:

1. **P0A:** Pin exact historical ATP/Overture vintages, source identifiers, GERS bridges and scored-GEOID membership.
2. **P0B:** Apply a predetermined valid-form telephone parser to upstream ATP values and compare linked native Overture phone fields.
3. **P0C:** Construct deterministic, outcome-blind one-to-one matched controls and calculate native-phone availability.
4. **P0D-A:** Apply the frozen service-role taxonomy and select fixed named-source witnesses.

P0D-B and P0E provide separately conducted anchor/currentness and independent adversarial review, including adverse examples and interpretation limits.

**Reproduction requirements:** Python 3.12, open-source dependencies pinned in [`requirements.txt`](requirements.txt), network access and sufficient disk space for a historical ATP archive of approximately 2.95 GB plus the challenge inputs.

```powershell
git clone https://github.com/chizzydev/bias-bounty-atp-phone-2026.git
cd bias-bounty-atp-phone-2026
py -3.12 -m pip install -r requirements.txt
py -3.12 verify_frozen_summary.py
py -3.12 -u run_discovery.py --work-dir atp_run
```

On systems without the Windows Python launcher, use a Python 3.12 executable in place of `py -3.12`. `verify_frozen_summary.py` checks packaged aggregates only; the `run_discovery.py` command performs the raw-source computation.

A fresh Windows source-to-output execution on October 8, 2026 completed P0A–P0D-A. Across **16** outputs compared with the frozen baseline, **13** were byte-identical and **three** contained the same keys and field values with different serialization or ordering. **No semantic differences** were detected. This is a local rerun-equivalence finding, not a claim of independent second-machine certification or telephone currentness verification.

**Research documentation:** [Full methodology](docs/ATP_PHONE_BEST_BIAS_DISCOVERY.md) · [Reproduction certificate](docs/REPRODUCTION_CERTIFICATE_v1.1.md) · [Script provenance](docs/SCRIPT_ORIGINS.json).

## Limitations and alternative explanations

- Provider identity is perfectly separated between matched cohorts; provenance-entry counts do not represent multiple independent place-content providers.
- Structural brand presence, category agreement and tract matching do not establish equivalent businesses, phone-publication practices or service capability.
- Valid-form U.S. phone values are not necessarily assigned, current, branch-specific or answered.
- One selected external anchor has conflicting or stale phone evidence. The Texas all-tract burden table does not exactly match the authoritative scored GEOID list, although the main phone-omission and matched cohorts are unaffected.
- [Overture issue #574](https://github.com/OvertureMaps/data/issues/574) publicly reported the generic ATP-phone omission in September 2026. This study's contribution is the exact historical source-linked audit and fixed matched/operational comparisons, **not** first discovery of the generic problem.

## Sources, licensing and data scope

The study uses the [challenge's August Overture extracts](https://source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/README.md), [Overture GERS bridge documentation](https://docs.overturemaps.org/gers/bridge-files/), [ATP run history](https://data.alltheplaces.xyz/runs/history.json), and the [specific historical ATP archive](https://alltheplaces-data.openaddresses.io/runs/2026-08-01-13-32-15/output.zip). ATP output data are CC0; Overture and challenge extracts retain their applicable release and upstream attribution requirements.

The public repository provides executable source, fixed preregistrations, aggregate evidence and a reproduction receipt. It does not publish raw linked contact records, URLs containing token-like query parameters or private experiment outputs. External ATP data are used for **Bias Discovery evidence only**, not for reconstructing or calibrating withdrawn leaderboard reference targets. The associated submission `Kmiqz6te` is administratively linked to the entry; it did **not** generate the Discovery findings.

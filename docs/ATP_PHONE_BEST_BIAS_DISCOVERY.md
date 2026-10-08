# Best Bias Discovery — When an Upstream Phone Number Does Not Reach the Map

**Entry:** Bias Bounty Mapping Equity Challenge (October 2026)  
**Zindi username:** `chizzydev250`  
**Prize:** Best Bias Discovery ($1,000)  
**Data vintage:** Overture `2026-08-19.0`; exact historical AllThePlaces run `2026-08-01-13-32-15`, ended `2026-08-05T15:33:36Z`.  
**Competition score submission associated with this entry:** **`Kmiqz6te` (V2-21, separately judged numerical submission)**  
**Public source repository:** **https://github.com/chizzydev/bias-bounty-atp-phone-2026** (verify files are publicly readable before submitting)  

## Abstract

A source-conditioned representation problem can remain invisible to a geographically stratified coverage scorecard: a place exists in Overture, yet a valid-form phone string present in the exact historical upstream record does not appear in the place's native `phones` field. By linking AllThePlaces Feature IDs, Overture GERS IDs, and the pinned August release, we isolated **21,608** such omissions in the four primary study-region packages (and **829** additional omissions in supplemental Eastern Washington). Across **6,505** fixed, same-tract, same-primary-category matched pairs, native valid-form phone availability is **0%** in the ATP-sourced exposed records versus **6,245/6,505 = 96.0031%** in Meta-sourced controls.

This is a **descriptive difference in source-conditioned map representation**, not a randomized provider effect, and valid-form phone numbers have not all been verified as correct, live, or site-specific.

## Discovery outside the automated scorecard

The standard scorecard tracks aggregate road, building and selected POI gaps by geographic and vulnerability strata. It does not evaluate **whether a particular upstream contact attribute survives into the consumer-readable POI field**. A tract may have plentiful mapped POIs yet mapped records can omit a first-class phone channel available upstream. Our unit of evidence is a source-ID-linked place rather than a scorecard gap value.

## Frozen methodology and identity chain

1. **P0A — source and vintage freeze (before phone outcomes).** Select the `2026-08-19.0` Overture places extract and link native GERS source records to AllThePlaces records via exact source identifiers and August bridge files. Determine scored membership from each region's authoritative sample GEOID list, not only polygons. Resolve the source archive from a unique exact end-time entry in AllThePlaces run history. Freeze **31,654** source links across five packages. The historical source run and 120 bridge witnesses were independently replayed.
2. **P0B — transfer check (before category and demographic effects).** From the pinned historical ATP archive, parse source phone strings into a specified U.S. 10-digit comparison form (accepting an optional leading `1` and stripping the declared extension convention). Freeze the **22,437** eligible source records before reading the native Overture `phones` arrays. All **22,437** exact linked Overture records have a null native phone field. `Valid-form` is not the same as a verified callable line.
3. **P0C — outcome-blind deterministic matching.** Freeze one-to-one controls without replacement using same scored tract GEOID, primary Overture category, recorded source-count bin, operating-status bin and a structural brand-present flag, with deterministic SHA-256-based ordering. Then read the matched native phone outcomes. The four-region primary analysis yields **6,505** pairs across 3,489 tracts and 90 categories; 6,245 controls expose at least one valid-form phone, and no exposed records do.
4. **P0D-A — preregistered operational-role subset.** Before inspecting role outcomes, freeze a taxonomy of service categories. The four-region screen contains **4,711** missing native-phone fields attached to essential-supply and medical-contact roles, including **3,682 gas stations**, and **231 medical-role records**. The operational matched subset contains 2,086 pairs with a 1,986/2,086 (95.2061%) control phone rate. **The medical-only matched rate is 42/49 (85.71%), not 95.21%.** No emergency-response role losses were found in this frozen category screen.
5. **P0D-B / P0E — independent adversarial checks.** Preserve 12 mechanical anchors and corroborate public witnesses with source-strength labels; one anchor has unresolved/stale phone evidence. The independent October 7 review separately downloaded source data, rechecked native nulls and control matches, examined parser alternatives, considered competitor overlap, and exposed a tract-polygon mismatch relevant to burden-table presentation. It did not certify the original full-code execution chronology on a new machine.

## Primary region evidence

| Package | Frozen upstream phone omissions | Exact matched pairs | Valid-form native control phones |
|---|---:|---:|---:|
| Eastern Oklahoma | 2,320 | 589 | 560 |
| Maricopa package | 2,816 | 732 | 709 |
| Northern California | 1,159 | 318 | 307 |
| South-Central Texas | 15,313 | 4,866 | 4,669 |
| **Four-region total** | **21,608** | **6,505** | **6,245** |
| Eastern Washington, supplemental only | 829 | not included above | not included above |

## Why it matters — and what remains unmeasured

For a map-based relief directory, a null `phones` field eliminates an immediate native click-to-call value even when the upstream source supplied a valid-form number. The affected mapped roles include fuel stations, groceries, convenience stores, pharmacies and medical sites. A user planning for a wildfire, heat event or evacuation may need an additional web search before contacting a facility about hours, supplies, fuel or availability.

**This work does not show that anyone could not contact a facility, experienced a delay, or suffered clinical or evacuation harm.** Some represented venues have websites, email or social channels; some upstream phones may be wrong, stale or shared. The measured consequence is **native telephone-channel visibility**, not overall reachability. Operational counts describe place records and tract coverage, not affected persons. We do not claim a measured demographic/SVI/rural/tribal burden difference or a causal mechanism inside Overture's ingestion.

## Robustness, limitations and adverse evidence

- All exposed primary records have ATP as their content provider; matched controls have Meta as content provider. Additional provenance entries are Overture calculations/status data and **not independent content providers**. Source behavior is confounded with group assignment.
- Structural `brand` presence is not identical to meaningful brand-name equivalence. Same primary category does not guarantee similar real-world services, hours, chain size or phone publication practices.
- Upstream phone format validation is not phone allocation, branch accuracy, successful dialing, or currentness validation. Keep the one conflicting/stale public anchor visible.
- The TX tract polygon set includes seven additional zero-land/zero-population polygon IDs that are not in the official 6,003-ID sample list; the original all-tract burden export was not an exact authoritative-sample-set match. This does **not** change the frozen 21,608 primary omissions, the matched comparisons, or named anchors; do **not** represent the tract-burden CSV as a fully repaired all-scored-tract output.
- Overture issue [#574](https://github.com/OvertureMaps/data/issues/574), filed September 28, 2026, already reported the general phenomenon of AllThePlaces phone omissions. This entry's distinct contribution is the exact historical US source-level audit, frozen matched comparison, and operational-role characterization; it is **not** a first discovery of generic ATP phone omission.
- The comparison uses the frozen August release; current source corrections, newly licensed services or later Overture versions are outside the estimand.
- The 12 external source anchors corroborate selected observations, not the full population. One conflicting example is preserved, not excluded.

## Reproduction and sources

The provided `src/` files are provenance-preserving portability adaptations of the original preregistered P0A/P0B/P0C/P0D-A scripts. Only workspace paths and parent-manifest hash handoff have been adapted; the scientific cohort/threshold logic has not been intentionally changed. Original and transformed source hashes are recorded in `docs/SCRIPT_ORIGINS.json`. **Release rerun:** On 8 October 2026, the adapted P0A through P0D-A pipeline completed on the user’s Windows machine; a separate offline audit compared 16 result CSVs with privacy-preserving fingerprints of the frozen original. Thirteen matched byte-for-byte and three matched semantically with no changed fields. See `REPRODUCTION_CERTIFICATE_v1.1.md`. This is a documented local clean raw-source rerun, not a claim that a second independent new machine has executed the release.

On a compatible machine with Python 3.12 and access to public Overture/ATP inputs:

```bash
python -m pip install -r requirements.txt
python verify_frozen_summary.py
python run_discovery.py --work-dir atp_run
```

The first command installs open-source dependencies; the second checks the included frozen **aggregate evidence only**; the third is the actual full source-to-output pipeline. The full historical AllThePlaces ZIP is roughly **2.95 GB** and should not be re-downloaded merely to run the aggregate certificate. DuckDB extensions may require public-network access. No paid API, removed reference layer or historical leaderboard target values are needed for this Discovery chain.

- [Official competition](https://zindi.world/competitions/bias-bounty-mapping-equity-challenge) and [challenge public package](https://source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/README.md), official sample GEOID authority.
- [Overture August release](https://docs.overturemaps.org/blog/2026/08/19/release-notes/) and [bridge file documentation](https://docs.overturemaps.org/gers/bridge-files/), `2026-08-19.0`.
- [AllThePlaces historical run index](https://data.alltheplaces.xyz/runs/history.json); [exact historical archive](https://alltheplaces-data.openaddresses.io/runs/2026-08-01-13-32-15/output.zip) (SHA-256: `15B46EA37C2BD5C4A15723D0E97B65CF7D3B2C7A0ACACE0132F250CC66D9819F`).
- AllThePlaces data are publicly available under CC0; respect release-specific Overture provenance and source-data attribution conditions. Public challenge-data reuse conditions also apply.
- Public-source retrieval dates: 2026-10-07 (independent review); 2026-10-08 (release preparation). Do not silently substitute the latest live data for the fixed vintage.

## Release integrity and ethics

Raw witness records may contain public source phone numbers and source URLs with credential-like query parameters. They are **not** included in this public kit. Do not upload the raw P0E evidence archive or raw joined CSVs to a public repository without separate review and sanitization. The upstream public datasets remain available for complete execution through the open-source scripts.

**To finalize this special-prize entry:** replace the two identity/link placeholders above with the active numerical-submission IDs and a verified public repository URL, run the clean reproduction, publish code/methodology for all participants, and submit the completed document via Zindi's separate Best Bias Discovery form.

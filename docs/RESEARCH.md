# Research plan — the publication angle

**Version 0.1.0 (2026-08).** Understory's primary framing is a *methods-plus-benchmark
paper*: not "we detected logging" but **"a reproducible open benchmark for
separating anthropogenic disturbance from natural decorrelation in NISAR
L-band coherence time series, evaluated on forest degradation."** The
methods framing is the citable primitive; each new domain (mining,
right-of-way, agriculture) becomes a follow-on application paper reusing the
same harness. Methods papers accumulate citations; application papers don't.

## Positioning claim (defend this sentence)

> The first open, reproducible benchmark for coherence-based *sub-canopy
> degradation* detection on NISAR, with externally documented ground truth
> and published failure analysis.

The novelty boundary, stated honestly: NASA-affiliated work (Flores-Anderson
et al., 2026) detects early *deforestation* from C-/L-band dual-pol
**backscatter**. Understory differs on all three axes that matter to a
reviewer: coherence (not backscatter), degradation under closed canopy (not
clearing), and an open benchmark with versioned labels (not a closed
result). "First open benchmark" is the defensible claim; "first detection"
is not. A systematic prior-art sweep across SAR/forestry literature is an
open task before the related-work section is written.

## Venue ladder (in order)

1. **AGU Fall Meeting 2026** (San Francisco, December) — abstract deadline
   **2026-08-05**. Work-in-progress abstracts are culturally accepted; the
   first-light noise-floor result (below) is the abstract. Requires joining
   AGU (non-member waiver deadline passed 07-22). Forcing function: real
   results by December.
2. **IGARSS 2027** — fall 2026 deadline, lower pressure, the IEEE remote
   sensing flagship. The fallback if AGU is missed.
3. **Journal paper**: two special issues are actively soliciting exactly
   this — *Geo-spatial Information Science*, "Advancing Earth Observation
   with NISAR: Early Results" (comparative coherence performance and error
   sources — nearly a description of this benchmark), and *Remote Sensing*
   (MDPI) standing special issue "NISAR Global Observations for Ecosystem
   Science and Applications". Repo + labels ship as supplementary material.
4. **Data paper** for the label library itself (*Earth System Science Data*
   or *Scientific Data*): a citable dataset artifact, often easier to land
   than the methods paper and cited more. The library's separate versioning
   and CC-BY license were designed for this.

Affiliation: "Independent Researcher" is accepted (MDPI policy is explicit).
arXiv preprinting needs a category endorsement — ask an author we cite;
journal submission needs none.

## The first publishable result (no ground truth required)

The `amazonas-first-light` run yields **the per-pixel coherence distribution
of intact closed-canopy tropical forest at NISAR's 12-day repeat, on
calibrated data** — the natural-decorrelation noise floor. Nobody has
published this number yet. It requires zero labels, ~3 pairs, and it is the
AGU abstract: *"Temporal coherence stability of undisturbed Amazon forest at
L-band 12-day repeat: first results from NISAR."* Every detector anyone ever
builds on NISAR forest data fights this floor; measuring it first is a real
contribution and cites forward into the benchmark paper.

## Reviewer-rejection defenses, mapped to repo work

The three standard kill reasons for remote-sensing papers, and what this
repo does about each — these are roadmap items, not aspirations:

| Rejection reason | Defense | Status |
|---|---|---|
| Insufficient ground truth | ≥50 externally documented events (Imazon SAD / IBAMA transcription into `understory-labels`), rejected events included | label collections scaffolded; transcription is the critical path |
| No comparison baseline | (a) detection lead vs the optical alert record — `optical_alert_date` is already first-class in the schema and scored; (b) Sentinel-1 C-band coherence over the same AOI/windows as a second detector through the same harness | (a) shipped; (b) roadmap |
| Uncalibrated data | Provisional-tier runs now; identical re-run on validated `NISAR_L2_GUNW_V1` (Q4 2026) with a beta/provisional/validated difference table quantifying the artifact effect | tier plumbing shipped; difference table pending validated data |

## Claims discipline (already enforced in code)

Synthetic results are scaffolding, never claims — kill-criteria verdicts on
synthetic benchmarks are auto-marked as such in every report. Published
tables are machine-generated from report JSON. Matching tolerances are
recorded inside every report. The methodology document is versioned so
reviewers can pin the frozen method. This is precisely the reproducibility
posture reviewers reward.

## Sequencing

First-light run (needs only Earthdata creds) → AGU abstract (08-05) → label
transcription toward 50+ events while Pará coverage accumulates (~October)
→ scored benchmark on provisional → Sentinel-1 comparison harness →
validated-tier re-run → journal + data paper submissions.

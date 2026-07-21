# Productisation: a decision record

**Status: decision record, 2026-07-21. Not a roadmap, and deliberately a "no
for now".** It exists so the question is answered against evidence once, rather
than re-litigated every time someone asks whether this should be a product.

Companion to [APPLICATIONS.md](APPLICATIONS.md), which asks what else the method
could detect. This one asks what it would take to put the method in front of
users, what that costs, and whether now is the moment.

## The short version

Productising now conflicts with two of this project's own written rules, and the
market research does not rescue it. The recommendation is: **close the ingest
gaps, publish one real-data benchmark report, and use the report as the ask.**
Total infrastructure for the next twelve months under that plan is **$0–20**.

No AWS account is required, and the usual reason to want one does not apply
here.

## Does this need AWS?

**No — and the reasoning inverts the standard argument.**

The normal case for colocating compute with an archive is egress cost. That does
not apply to NISAR:

- ASF's NISAR buckets are **not requester-pays**, and same-region S3 transfer is
  **free**. You pay GET requests at $0.0004/1,000.
- Out-of-region access is **blocked, not billed** — credentials from
  `https://nisar.asf.earthdatacloud.nasa.gov/s3credentials` are us-west-2 only.
  The HTTPS path is CloudFront-fronted and **NASA bears that cost**, not the
  downloader.

So there is no egress bill to avoid. What in-region access buys is wall-clock
and the `s3Urls` path `understory_core.discovery` already parses — not money.

Costed at the scales that matter (us-west-2 on-demand, S3 Standard
$0.0265/GB-month):

| Scale | Total |
|---|---|
| 10 AOIs — what the benchmark actually needs | **~$20/year** |
| 100 AOIs | $90–330/year |
| Brazilian Legal Amazon (5.02 M km²) | $80/yr at 80 m posting, ~$1,100/yr at 20 m |

[PERFORMANCE.md](PERFORMANCE.md) measured a 100-AOI cycle's 80 m compute at
under four minutes on one laptop. At benchmark scale the AWS question is not an
economic question.

**Cost of being wrong by not adopting AWS:** the Q4 2026 backlog reprocessing.
Pulling a year of Legal Amazon history is ~11.5 TB — roughly 5 days at 200 Mbps
over the internet against ~3 hours in-region. Wall-clock, not dollars.

**Cost of being wrong by adopting it now:** a few hundred dollars you did not
need, plus a permanent engineering tax (hourly credential refresh, IAM, Batch
definitions, a deployment surface) in a repo whose stated rule is no application
layer without a named user.

### The cheapest thing to do instead

Email `uso@asf.alaska.edu` about **ASF OpenScienceLab** — a free, in-region
JupyterHub. Three questions: per-session vCPU and RAM, persistent storage quota,
and whether multi-hour non-interactive jobs are acceptable use. If the answers
are adequate, the benchmark runs next to the data for **$0 with no AWS account
at all**. Cost: one email. This is the highest value-per-effort item in the whole
analysis, and its answer is the largest single unknown.

### Options that are closed, recorded so the question stops recurring

- **Google Earth Engine** carries **zero NISAR datasets**, and holds Sentinel-1
  GRD rather than SLC — so repeat-pass interferometric coherence cannot be
  computed there *at all*. It is not a cheaper option; it is not an option.
  This matters because GEE is how most comparable systems are built (below),
  and that escape hatch is closed to us specifically.
- **Microsoft Planetary Computer**: 135 collections, no NISAR; its free compute
  hub retired in June 2024.
- **ASF HyP3**: Sentinel-1 only.
- **Cheaper clouds** (Hetzner and similar) cost *more* than AWS at benchmark
  scale, and forfeit `s3://` access entirely to the region lock.

## What comparable systems actually do

The pattern is consistent, and it is not a platform build. **The smallest
credible footprint is an algorithm, a periodic batch job, a human review step,
and static files on object storage.**

- **RADD** (Wageningen) runs entirely inside GEE, quoted at ~$0.0075/km² of
  batch compute, served as one ImageCollection under CC-BY and redistributed by
  GFW, SEPAL and EarthMap. One portal, one university group.
- **Forest Foresight** (WWF-NL) is the smallest serving architecture found: a
  GPL-3.0 R package plus an open Azure blob container. **No API, no database, no
  tile server.** Six named people, 17 tropical countries, operational since 2021.
- **RAMI** (ACCA, Peru) is the closest structural analogue — Sentinel-1 change
  detection with masking, 81.3% ± 7.0% user's accuracy for mining, delivered as
  **monthly bulletins** to Peru's environment ministry. Small NGO, manual review
  before publication.
- **Amazon Mining Watch** (Earth Genome) does >100 M patch assessments per
  **quarterly** run, human-reviewed, published as GeoJSON. ~14 people
  organisation-wide; the platform rewrite is attributed to **one engineer**.
- **The anti-pattern — the GFW Data API**: FastAPI + PostGIS + AWS Batch + Spark
  + Terraform + per-PR database instances. Note that **GFW produces none of the
  alerts it serves.** SkyTruth, the nearest nonprofit that does run platforms
  like this, has 19 staff of whom 11 are technical. That is the headcount floor.
- **The one-person existence proof — Protomaps**: a solo developer serving a
  global basemap for ~$12/month on S3, under $5 behind CloudFront. One immutable
  file, HTTP range reads, no server, no database.

**The single most transferable finding: nobody moves granules.** Every
comparable system either never moves the data (GEE) or co-locates production
with the archive. Understory's current ingest — downloading whole 1.9 GB
granules to read one layer — is precisely what everyone else engineered away,
and the GEE route is closed to us. That makes ingest the first thing to fix and
the last thing to scale.

Two further lessons worth importing:

- **RAMI's precision comes substantially from its masking stack** (prior forest
  loss, water, accumulated disturbance), not from its change detector. Our v0
  has persistence, clustering and geometry but **no accumulated-disturbance
  mask**. That ablation is probably the cheapest available precision win, and
  should be run before tuning `anomaly_sigma`.
- **Human review before publication is normal**, not a failure of automation.
  RAMI's 81% and Amazon Mining Watch's figures are *post-review*. Our
  fully-automated numbers are therefore **not directly comparable**, and any
  published comparison must say so.

One place the field disagrees with us, worth stating rather than glossing: RAMI
concluded that operationally it is better to have false positives than to miss
illegal mining. [GOVERNANCE.md](GOVERNANCE.md) says the opposite. Both are
defensible — they encode different partner economics — but our norm should stop
being treated as self-evident, because the closest analogue chose differently.

## Distribution, ranked by leverage per effort

1. **Forest Watcher custom layers** — GFW's free offline field app accepts
   user-uploaded layers and AOIs up to 20,000 km² with **no GFW approval**.
   Days, $0. The cheapest path from this repo to a ranger's phone. Accepted
   formats and size limits are undocumented and must be tested empirically.
2. **Zenodo DOIs** wired to GitHub releases — concept DOI plus per-version DOI.
   Hours, $0. Makes a benchmark release citable, which is the actual product.
3. **GEE community catalog** — one GitHub issue against their template. A day,
   $0. Syndication channel only; single unfunded curator, so never the canonical
   copy.
4. **Static bundles on object storage** — the existing `*-alerts.geojson`, a
   GeoParquet mirror, COGs and a STAC `catalog.json`. Cloudflare R2 is
   $0.015/GB-month with **free egress**; a release sits at or under $0.10/month.
5. **GFW integrated alerts** — a contribution *pathway* is documented (contact
   form, `gfw@wri.org`), but **no acceptance criteria, schema, accuracy
   threshold or timeline is published**, so it cannot be planned or costed. One
   email, after the first real-data report. Not before.

Recommended against, with reasons:

- **A QGIS plugin.** plugins.qgis.org requires GPLv2-or-later; our code is
  Apache-2.0, so it would need separate licensing, plus three-platform
  maintenance. The existing GeoJSON already opens in QGIS with no plugin.
- **SMS/WhatsApp alerting.** Emit a stable machine-readable feed at a stable URL
  and let partners fan it out. Building notification delivery is the fastest
  route to unbounded operational burden for one maintainer.
- **A hosted service**, today. $10–90/month of infrastructure, but the real cost
  is 0.3–0.5 FTE of operations and review, indefinitely — which forecloses the
  benchmark. This is the JJ-FAST failure mode in miniature: that programme
  retreated from 78 tropical countries to Brazil alone in April 2024 when the
  operational commitment outlived its funding.

## Who pays

**There is no paying customer for L-band coherence degradation alerts today, and
EUDR does not create one.**

EUDR's degradation test is a forest-**type conversion** test — primary or
naturally-regenerating forest becoming plantation, planted forest or other
wooded land — it applies only to the **timber** commodity, and it is judged
against a fixed **31 December 2020** cut-off. Selective logging that does not
convert forest type is compliant. That is a historical archive question answered
against a 2020 baseline, which NISAR data (from 2025) cannot address at all —
not a 12-day alerting question. Current application dates are 30 Dec 2026 for
large and medium operators and 30 Jun 2027 for micro and small, twice delayed
already.

> **Verify before reuse.** EUR-Lex would not load during this research, so the
> forest-type-conversion reading rests on WRI and GFW secondary summaries.
> Confirm against Article 2(7) of Reg. (EU) 2023/1115 and the December 2025
> revision before this claim enters GOVERNANCE.md or any funding document — it
> cuts against the EUDR rationale currently stated there.

The rest of the demand side is no better. Verra REDD+ issuance fell from 131.4 Mt
(2021) to ~10.2 Mt (2025 partial) at roughly $2.70/t, and VM0048 still has no
degradation module — the entire 2025 REDD+ issuance is worth about $28 M gross.
Insurance premiums at 2–10% of a $2.70 credit leave no data budget. Enforcement
agencies are users, not customers: Brazil's monitoring is domestic and free, and
IBAMA's enforcement money buys helicopters, not alert subscriptions.

**Where money for this class of work actually is: philanthropy and
institutions.** Bezos Earth Fund → WRI $100 M over five years for satellite
monitoring; WRI onward to UMD GLAD $12.75 M; Smithsonian $12 M for GEO-TREES —
an open independent validation layer for satellite biomass claims. GEO-TREES is
the closest structural analogue: **the validation itself was the product**,
funded at $12 M. The realistic ask here is a fraction of that, and the
justification is exactly what CLAUDE.md already commits to — a reproducible
answer, published favourable or not.

The RADD precedent cuts both ways and is the sharpest evidence available:
commodity buyers demonstrably **will** fund a SAR forest-alert system through a
WRI-brokered precompetitive consortium — and what they bought was then **given
away free**. The revealed structure of this market is funding for development,
not subscriptions. Our open, CC-BY, benchmark-first posture is well matched to
how that money moves and badly matched to a SaaS thesis.

## What has to be true before a product is the right move

All five, in order. Steps 1–3 are physics- and NASA-gated, not effort-gated.

1. A forest AOI with ≥6 consecutive GUNW pairs on the PROVISIONAL or validated
   tier exists and has been processed end-to-end. Currently false — see
   [ARCHIVE_STATUS.md](ARCHIVE_STATUS.md); the Pará AOI had **zero** coverage at
   probe time.
2. One real-data benchmark report exists with a PASS/FAIL verdict on all three
   kill criteria, published either way.
3. That report has been re-validated after the Q4 2026 reprocessing.
4. A **named** organisation has said in writing that it would act on this feed,
   at this cadence, in this format. Not "this is interesting".
5. The ingest path is operationally sound.

On the current evidence the earliest honest product date is **Q1 2027**.

It is worth being blunt about where the science stands: the only sensitivity
figure this project has is synthetic, at roughly 3.7 ha, which **fails its own
≤2 ha kill criterion** and is worse than JJ-FAST's 1–1.5 ha operational L-band
floor. Shipping a product on that basis would mean publishing provisional-grade
alerts that the Q4 reprocessing will supersede. The project's only durable asset
is that its numbers can be trusted, and that asset is spent exactly once.

## The strongest argument against this recommendation

Stated fairly, because it is partly right.

**Waiting for the benchmark may mean waiting past the moment when anyone is
available to partner, and "no named user" can become self-fulfilling.** RADD
entered GFW because ten funders and WRI assembled *around a method that did not
yet have published operational results* — the consortium came first and paid for
the science. Hold strictly to publish-then-partner and you forgo the only
demonstrated funding route in this market; by the time a report lands in 2027,
the WRI/Bezos monitoring money may already be committed to DIST-ALERT and the
integrated layer. NICFI's cancellation also shows that free-data infrastructure
disappears without warning, and a project that is not already inside someone's
programme when budgets are set does not get retrofitted into them.

There is a sharpening that resolves most of this: **a partner conversation is
not an application layer.** Talking to WRI, ACCA or a Congo Basin NGO costs an
email and creates the named user the project's own rule requires. The rule
forbids *building*, not *asking*.

So: **start the conversations now, in parallel; build nothing until one produces
a written commitment and the report exists.** What does not follow is shipping a
service, a public alert feed or a hosted viewer on provisional data.

## What could not be verified

Recorded because a decision document that hides its own uncertainty is worse
than none.

- **EUDR Article 2(7) primary text** — EUR-Lex returned empty on repeated
  attempts. The whole "degradation ≠ selective logging" reading is secondary.
- **ASF OpenScienceLab quotas** — no published quota document. One email
  resolves the single highest-value unknown here.
- **Whether ranged GETs against a real GUNW actually reduce bytes transferred.**
  S3 supports Range and ASF's path is CloudFront-fronted, but whether the HDF5
  chunk layout makes a ranged read efficient is untested.
- **The GUNW coherence posting (20 m vs 80 m).** Arithmetic favours 80 m; not
  settled against a granule. See ARCHIVE_STATUS.md — this changes the 100-AOI
  and Amazon cost lines by roughly 10×.
- **Forest Watcher's accepted formats, geometry counts and size limits.**
- **GFW's acceptance criteria** for the integrated-alerts layer, and whether
  RADD entered via the public form or a pre-existing WRI partnership. That
  distinction determines how to approach them.
- **Any actual contract value** for Satelligence, Meridia, Koltiva, Trase or
  LiveEO. None publish pricing, so the commodity-trader channel cannot be sized.
  Treat published "EUDR software market" figures as vendor market-sizing.
- **Procurement in Peru, Indonesia and the Congo Basin.** The "users, not
  customers" conclusion generalises from the Brazil case and is inference.
- **Whether any NASA or ESA programme grants cloud credits to independent
  open-source projects.** None found — reported as a gap, not a negative
  finding, and moot given a $20–1,100/year true bill.

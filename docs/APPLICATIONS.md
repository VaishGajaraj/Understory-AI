# Adjacent applications of NISAR L-band coherence

**Status: survey, 2026-07-21. Not a roadmap.** Nothing here is scheduled. The
MVP is the forest-degradation benchmark, and this document exists so that
decisions about what comes after are made against the published record rather
than against enthusiasm.

Scope follows the repo's guards: applications sharing the **coherence-change
processing stack**. Deformation/phase-based work (subsidence, tailings,
permafrost) is a different stack and stays out, per `CLAUDE.md`. Defense
applications are out of scope by identity, not by capability.

## The finding that should govern everything else

**No operational near-real-time forest alerting system uses interferometric
coherence.** JJ-FAST, RADD, GLAD-L, GLAD-S2 and DIST-ALERT are all backscatter-
or reflectance-based. NISAR's own baseline ecosystem algorithms are backscatter
change detection — the Science Users' Handbook specifies a CUMSUM change-point
detector on cross-polarised backscatter, and mentions coherence for ecosystems
only to say that "measures of radar cross section are more robust than
interferometric measures of change, such as through the decorrelation
signature, which may be an appealing alternative or augmentation to the
base-algorithm." Coherence ships as a delivered layer, not as the disturbance
observable, and the mission's own documentation ranks it second.

That cuts both ways, and the second edge is sharper than it looks. There is no
incumbent to displace — and no prior art establishing that the method works.
Understory's central question is genuinely open, which is the reason to run the
benchmark and also the reason to expect it might fail.

Worth being precise about how open: **no published spaceborne L-band coherence
time series over intact tropical closed canopy at ~12-day repeat exists.** The
nearest study found only one suitable 14-day PALSAR-2 pair per tropical site in
the entire archive. Understory would be first to fill that gap, which is a
better framing of the contribution than "applying a known method to new data."

Also note the mission's own disturbance requirement is annual, at 1 ha, for
areas losing **at least 50% canopy cover**. Selective logging sits below that
bar by design. Understory is not duplicating a mission product.

Two further constraints shape everything below:

**Background coherence dominates the disturbance signal in humid tropics.** Lei
et al. (2018) measured scene-wide L-band coherence over Tapajós at 0.13–0.49,
discarding most pairs below 0.1, and concluded ALOS-2 could only *qualitatively*
depict the disturbance. The same group's method worked well in subtropical
Queensland — where scene-wide coherence was 0.75. That gap, not the method, is
the story. Background coherence stratification looks mandatory as a benchmark
covariate rather than optional.

**The sign of the coherence response is not universal.** Tanase et al. (2010)
found L-band coherence *decreasing* with burn severity while C- and X-band
*increased*; the same configuration then gave opposite signs at two sites,
which the authors attributed to antecedent dryness. A kill criterion written as
a fixed one-sided coherence threshold would be fragile against this.

## Sizing: why 12 days and 20 m matter

| Sensor | Repeat |
|---|---|
| JERS-1 | 44 d |
| ALOS-1 PALSAR | 46 d |
| ALOS-2 PALSAR-2 | 14 d |
| SAOCOM-1A/1B | 8 d (16 d single satellite) |
| **NISAR** | **12 d** |

Seppi et al. (2022) concluded that 8–16 day temporal baselines are *required* to
mitigate L-band temporal decorrelation over forest. Almost every published
L-band coherence result sits at 42–46 days, outside that window. NISAR's 12-day
repeat is the first free, global, spaceborne L-band data inside it — which is
precisely why the question is worth asking now and could not have been asked
before.

**Open question: what posting is the GUNW coherence layer actually at?** Two
independent passes over the ASF documentation disagreed — one reported the
coherence magnitude carried at both 20 m and 80 m within GUNW, the other that
GUNW and RUNW are posted at 80 m with RIFG at 30 m and the ecosystems
backscatter product GCOV at 20 m. This is not a detail. RADD reports 79.6% of
Congo Basin disturbance events fall between 0.2 and 0.5 ha; at 80 m posting a
1 ha event is one to two pixels and the large majority of events by count are
structurally invisible. **Resolve this against a real granule before designing
around either answer** — `scripts/probe_archive.py` plus one downloaded GUNW
settles it in minutes, and `understory_core.ingest` already walks the product
tree rather than hardcoding paths precisely because this kept moving.

If the fine layer does exist, it is also the one the pipeline cannot currently
process at scale on one node — see [PERFORMANCE.md](PERFORMANCE.md). The science
requirement and the engineering constraint would then collide on the same
number.

## What 12-day L-band coherence over tropical canopy actually measures

The only directly relevant measurements available, from ALOS-2 over AfriSAR
Gabon sites at a 14-day baseline the authors explicitly call comparable to
NISAR's 12 days:

| Site | Baseline | Mean coherence (σ) |
|---|---|---|
| Lopé | 14 d | 0.34 (0.14) |
| Mondah | 14 d | 0.32 (0.18) |
| Ogooué | 14 d | 0.59 (0.11) |

Three cautions, all of which belong in the benchmark's methodology rather than
its discussion section:

- **Multilook bias.** These come from ~9–20 looks, and coherence magnitude is
  positively biased at low true coherence. Work using 324–1764 looks measured
  0.03 over fully decorrelated targets. The 0.32–0.34 values may be
  substantially inflated; 0.59 is clearly real. **Report look count alongside
  every coherence number, or the numbers are not comparable across studies —
  including across our own runs.**
- **Weather beats elapsed time.** An 8-day airborne pair scored *lower* than a
  14-day spaceborne pair at the same site because of intervening rain. Tower
  radar over boreal forest found wind approaching 10 m/s causes total L-band
  decorrelation, with a strong diurnal cycle in which noon is worst and dawn and
  midnight are best. NISAR's dawn–dusk (6 AM/6 PM) sun-synchronous orbit is
  favourable here, which is a point worth making explicitly rather than assuming.
- **Fitted decorrelation time constants in the literature differ by 50×**
  (τ ≈ 12 d vs τ ≈ 616–904 d) purely because some models include a long-term
  coherence floor and some do not. They are not comparable and must not appear
  in the same plot. The defensible parameterisation is
  γ(t) = (1−ρ∞)·e^(−t/τ) + ρ∞.

Whether 12-day L-band coherence over intact tropical canopy is usable at all is
genuinely under-determined by the published record. Two of three Gabon sites sit
near 0.33, which at low look counts is close to where a biased estimator would
report a floor value from pure noise.

## Survey

Ordered by how well the published evidence supports a coherence-based method.
"Adjacency" is how much of Understory's existing stack would be reused.

### Strong evidence

**Burn severity.** The best-evidenced L-band coherence application found, and
the only one where L clearly beats C and X. Tanase et al. (2010), across three
Spanish sites with ALOS PALSAR at a 46-day baseline, fitted burn severity from
coherence at R² 0.912 (HH) and 0.939 (HV), against 0.640 for TerraSAR-X and
0.489–0.650 for C-band. Crucially, L-band was far less sensitive to local
incidence angle — the robustness claim that matters in terrain. The C-band
coherence baseline for burned area is genuinely poor (72% omission, 57%
commission in tropical Africa), so the bar is low.

Caveats: a single 46-day pair immediately post-fire, no recovery time series,
and the site-dependent sign flip noted above. Adjacency is high — same stack,
different label library.

**Wetland inundation dynamics.** Kim et al. (2013) characterized JERS-1 L-band
coherence over the Everglades by vegetation class: woody wetlands 0.2–0.55,
mangrove 0.2–0.5, herbaceous 0.2–0.3, against a measured open-water
decorrelation floor of 0.14–0.16. The operationally useful result is the
persistence structure: woody wetlands hold coherence essentially independent of
temporal baseline out to 2.5 years, while herbaceous wetlands decorrelate
abruptly after 44 days. Zhang et al. (2015) separated flooded from non-flooded
reeds at 0.80 versus 0.35 with ALOS PALSAR.

Note the sign inversion: inundation *raises* coherence via stable double-bounce
off a smooth water surface, while surrounding vegetation decorrelates. A
detector built on "disturbance means coherence loss" will not transfer without
modification — which is a good reason to treat it as a separate detector rather
than a config change.

### Weak or absent evidence

**Selective logging** — the project's own target. The honest position is that no
published study has validated L-band repeat-pass coherence for selective logging
at scale. The nearest results use single-pass TanDEM-X (X-band) or L-band
backscatter. Lei et al. (2018) used ALOS-2 coherence only as qualitative
corroboration. Meanwhile the operational L-band backscatter benchmark, JJ-FAST,
runs at 44.5% producer's accuracy on *clear-cut* deforestation at a 1.5 ha
floor, and selective logging is strictly harder. The best small-gap detector in
the literature is C-band Sentinel-1 backscatter (Dupuis et al. 2023: 0.89 global
accuracy at 10 m, most gaps ≤500 m²).

This is what the benchmark is for, and the prior is not favourable.

**Agriculture / crop phenology.** No published demonstration of L-band coherence
for crop classification or phenology was found across roughly 18 distinct
queries. The mature coherence-for-agriculture literature is entirely C-band; the
L-band agriculture literature is entirely backscatter. Absence of evidence
rather than evidence of absence, but the gap is conspicuous.

**Flood under vegetation.** The mechanism is established, the application is
immature. Tsyganskaya et al. (2018) surveyed 83 flooded-vegetation studies and
found exactly one using coherence alone. Jung & Alsdorf's JERS-1 coherence
statistics show several flooded classes statistically *indistinguishable* from
non-flooded forest at two of three Amazon sites.

**Illegal mining (ASGM).** No peer-reviewed L-band coherence study found. The
field runs on C-band Sentinel-1 intensity, and it works well — 81.3% user's
accuracy with 100% producer's accuracy in Madre de Dios. Mining strips canopy
*and* soil, so the signal is a large backscatter change that needs neither
coherence nor L-band. **Weak target: the incumbent is good and the physics does
not favour us.**

**Roads and trails under canopy.** No L-band coherence evidence. The one
quantitative statement in the literature is a resolution limit from X- and
C-band work: road detection requires sub-5 m resolution. A 4–6 m logging road is
sub-pixel at NISAR's 20 m coherence posting. Understory's linearity filter
targets exactly this, so the constraint deserves stating plainly rather than
discovering it in a benchmark result.

**Snow / freeze-thaw.** L-band retains roughly twice the coherence of C-band
over dry snow at a 10-day span (0.775 vs 0.388). But coherence is used almost
exclusively as a quality gate on phase-based retrievals, not as the detection
observable, and no L-band coherence-magnitude freeze/thaw classifier with
published accuracy was found. The best-validated L-band freeze/thaw work
(90–95%) is backscatter.

### Where L-band is documented to fail

Worth recording so they are not proposed later:

- **Insect defoliation / bark beetle.** The standing review is explicit that
  shorter wavelengths beat L-band, and the mechanism explains it: defoliation is
  a foliage signal, and L-band sees past foliage to woody structure.
- **Windthrow.** In mountainous Europe the tested ordering is X > C; L-band was
  not tested. One small L-band study found HH and HV blind to typhoon damage
  while only VV responded, because windthrow removes structure without removing
  biomass. Notable given that Amazon blowdowns are a documented, growing,
  ≥30 ha disturbance population with a public Landsat reference database and
  essentially no SAR literature — an open niche whose physics is nonetheless
  unpromising for the HV channel.
- **Forest drought stress.** Simulations put the vegetation-water-content
  modulation below the spread between stand types, and a truck-mounted L-band
  scatterometer measured >2 dB *diurnal* swings from internal and surface canopy
  water. That confound is larger than most disturbance signals a benchmark would
  target — and it is a warning for Understory's own detector, not just for
  drought work: acquisition time of day, dew and interception need controlling.

## Data caveats that bite this benchmark specifically

From ASF's own known-issues list, and directly relevant to a coherence detector
over tropical forest:

- **BETA products show radiometric banding across the swath** from incomplete
  antenna-pattern removal, described as most apparent in regions of uniform
  radar cross-section — *tropical forests are the named example.* That is our
  target biome and a systematic false-alarm source.
- **RFI produces decorrelation streaks**, worst in cross-pol. A streak is
  exactly what a linear-feature detector is built to find, so the linearity
  filter that favours roads also favours this artifact.
- **Ionospheric artifacts near solar maximum** leave residual decorrelation
  streaks, particularly in descending tracks and at higher latitudes.
- **Do not mix BETA and PROVISIONAL products in one time series.** Processor
  differences produce artifacts. This is stronger than the existing
  re-validation caveat: it is not "BETA numbers need re-checking" but "a stack
  spanning both tiers is invalid." `discovery.GUNW_COLLECTIONS` already
  separates the tiers; `CoherenceStack.build` should refuse a mixed-tier pair
  list the same way it refuses mixed frame groups.

## What this implies for the current benchmark

Four things worth acting on, none of which require a new application:

1. **Stratify by background coherence.** The Tapajós/Queensland gap (0.13–0.49
   vs 0.75) predicts detector performance better than any parameter currently in
   the config. This belongs in the benchmark report as a covariate.
2. **Do not write one-sided coherence thresholds into kill criteria.** The sign
   of the response is site- and moisture-dependent in the published record.
   `anomaly_deficit` is already a deviation-from-baseline measure rather than an
   absolute threshold, which is the right choice; the kill criteria should not
   quietly reintroduce the assumption.
3. **State the sub-pixel road limit.** The linearity filter targets features
   below the coherence posting. That is a documented limitation, not a tuning
   problem.
4. **Single-pol regions are a stratum, not noise.** Congo DRC acquisitions are a
   mix of single-pol and dual-pol; single-pol loses HV, the channel most
   sensitive to canopy volume. Better encoded explicitly than discovered as
   unexplained variance.

## Evidence quality

Several load-bearing figures come from publisher abstracts or author theses
rather than full text, because MDPI, Elsevier, IEEE and Wiley block automated
retrieval. Specifically flagged: the Tanase et al. (2010) coherence–severity
numbers were recovered from the author's PhD thesis, which reprints the paper in
full, rather than from the journal. Anyone building on a number here should
retrieve the primary source before publishing against it.

Two things do not exist yet and cannot be cited: any peer-reviewed NISAR
coherence result for any application, and any published persistence duration for
a post-logging L-band coherence anomaly. If the benchmark needs the latter, it
is an original contribution rather than a literature value.

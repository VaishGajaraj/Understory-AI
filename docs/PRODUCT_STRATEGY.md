# Product strategy: one operating layer, multiple NISAR signals

Understory should become reusable software without becoming a bundle of unsupported science
claims. The product is a small, reproducible operating layer for turning an area of interest into
versioned NISAR evidence. Forest-disturbance detection is its first application pack and remains the
only one currently implemented.

## What NISAR makes possible

NISAR is not one dataset. The official product families expose different physical measurements and
require different validation:

| Product | Measurement | Defensible application families | Understory posture |
|---|---|---|---|
| **GCOV** | Terrain-corrected polarimetric backscatter | Biomass, crop area, inundation, soil/vegetation condition, disturbance | Best next ingestion adapter; do not reuse the coherence detector unchanged |
| **GSLC** | Geocoded complex signal | Custom backscatter change maps and user-generated interferograms | Expert extension after the GCOV path is understood |
| **GUNW** | Geocoded interferometric phase, coherence, and quality layers | Current coherence experiment; subsidence, landslides, volcanoes, earthquakes | Coherence is implemented; deformation needs a separate phase time-series application |
| **GOFF** | Geocoded dense pixel offsets | Glacier and ice-sheet flow, large surface displacement | Separate offset-processing application |
| **SME2** | Field-scale soil-moisture estimates | Drought, irrigation, reservoir management, crop forecasting | Integrate the Level 3 product; do not rebuild the mission algorithm |

ASF describes GCOV as the primary Level 2 product for biomass estimation, soil moisture estimation,
disturbance detection, inundation mapping, and crop-area delineation. It describes GUNW as primarily
supporting ground-surface displacement, GOFF as primarily supporting cryosphere applications, and
SME2 as a Level 3 agricultural soil-moisture product. This product map - not a shared marketing label -
sets the software boundaries.

Primary product reference: [ASF NISAR Data Products](https://nisar-docs.asf.alaska.edu/products-overview/).

## Opportunity map

### 1. Forest disturbance and managed timber - validate now

**Decision:** finish the current GUNW coherence benchmark before adding another detector. Then compare
it with a GCOV backscatter baseline against the same held-out events.

Potential users include forest managers, conservation groups, commodity due-diligence teams, and
territorial monitoring programs. NASA's forest application paper identifies harvest, fire, storm,
development, disease, and illegal logging as disturbance cases and stresses the value of consistent
cloud-independent observation.

Evidence: [NASA timber and forest disturbance white paper](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_Applications_Timber_and_Forest_Disturbance.pdf).

### 2. Flooded forests, wetlands, and flood extent - closest adjacent product

**Decision:** add as a separate `inundation` application pack after GCOV ingestion. Reuse AOIs,
inventory, provenance, terrain masks, and GeoJSON delivery; add water-history features, flood labels,
and flood-specific quality rules.

This is unusually well matched to L-band because open water and vegetation-water interactions are
observable through cloud and, in some conditions, beneath canopy. The application output should be
extent and duration, not a generic anomaly score.

Evidence: [NASA timely maps of flooding white paper](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_Applications_Floods.pdf).

### 3. Crop area and seasonal condition - valuable, different model

**Decision:** use GCOV polarization time series for crop-area/phenology features. Validate by crop,
region, and season; do not frame a structural disturbance threshold as crop intelligence.

The first credible product is regional crop-area and growth-stage evidence for analysts, not
field-level agronomic recommendations. Optical fusion is likely useful rather than contradictory.

Evidence: [NASA food-security white paper](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_Applications_Food_Security1.pdf).

### 4. Biomass and carbon evidence - high value, high validation burden

**Decision:** treat biomass as an externally calibrated estimation product, not an automatic extension
of disturbance alerts. It requires field plots, saturation/uncertainty analysis, allometry, and clear
separation between activity evidence and carbon-accounting claims.

Understory can first provide change evidence and provenance for MRV workflows. It should not claim
carbon tonnes until an independently reviewed biomass method exists.

### 5. Subsidence, landslides, volcanoes, and infrastructure - separate phase stack

**Decision:** build a sibling `deformation` application only after the ecosystem benchmark. Reuse
discovery, AOIs, manifests, and delivery, but add phase unwrapping/quality, atmospheric correction,
reference-point selection, line-of-sight velocity, time-series inversion, and expert review.

Slow landslides and subsidence are strong NISAR applications, but a coherence-loss detector does not
measure displacement. High-consequence infrastructure outputs must remain decision support and carry
quality flags rather than automated safety conclusions.

Evidence: [NASA landslide hazards white paper](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_Applications_Landslides.pdf) and [NASA subsidence white paper](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_Applications_Subsidence.pdf).

### 6. Glacier and ice motion - separate offset stack

**Decision:** use GOFF/ROFF dense offsets and cryosphere-specific filtering. Share only the operating
layer. Ice motion is a different observable, geometry, temporal interpretation, and validation task.

### 7. Soil moisture and drought - integrate before reinventing

**Decision:** consume SME2 and expose it alongside AOI histories. Add local validation and downstream
decision rules only when a named agricultural or water-management user defines the question.

## The production architecture

```text
AOI + time window
       |
       v
archive inventory ----> frozen product/frame selection
       |                            |
       v                            v
retrieval/cache ------------> immutable run manifest
       |
       +--> GUNW coherence --> forest disturbance (implemented)
       +--> GCOV backscatter -> inundation / crops / biomass (future packs)
       +--> GUNW phase ------> deformation (separate future pack)
       +--> GOFF offsets ----> ice motion (separate future pack)
       +--> SME2 ------------> soil-moisture history (future integration)
                                      |
                                      v
                       GeoJSON + JSON report + review state
```

The reusable layer owns AOI validation, archive inventory, retrieval, caching, provenance, quality
flags, configuration versions, and output contracts. Each application pack owns its signal model,
labels, thresholds, uncertainty, benchmark, and kill criteria.

## Production decisions

1. **One CLI, stable machine output.** `understory doctor`, `understory inventory`,
   `understory build-stack`, and `understory run` are the supported entry points. Human output is
   for operators; `--json` is for automation.
2. **Version every contract.** Inventory and benchmark configurations currently use schema version
   `1`. Reports include the config hash, software version, generation time, application name, and
   stack identity.
3. **Atomic artifacts.** Reports and alert layers replace complete files atomically; interrupted runs
   do not leave apparently valid partial outputs.
4. **No credential echo.** Diagnostics report only whether an Earthdata netrc entry exists. They do
   not print usernames, tokens, or passwords.
5. **Local batch before service.** Keep the tested execution unit as a single AOI on one machine.
   Add a queue/API only after a partner establishes concurrency, latency, and retention requirements.
6. **Review is part of the data model.** Production alerts need `unreviewed`, `confirmed`, and
   `rejected` states plus evidence lineage. A map without a feedback path is a demo, not a product.

## Release gates

| Gate | Evidence required |
|---|---|
| Developer preview | Synthetic end-to-end test, schema checks, deterministic config |
| Engineering preview | One real PROVISIONAL product through every stage; quality flags inspected |
| Research preview | Frozen frame with sufficient history, held-out labels, generated benchmark report |
| Partner pilot | Named user, review protocol, service expectations, incident/contact path |
| Production | Validated NISAR rerun, versioned release, rollback procedure, data-retention policy, monitored cost and failures |

## Sources and freshness

- [ASF NISAR product overview](https://nisar-docs.asf.alaska.edu/products-overview/) - current product levels, measurement contents, maturity guidance, and intended uses.
- [NASA NISAR applications](https://science.nasa.gov/mission/nisar/applications/) - mission application and stakeholder-engagement framing.
- [NASA NISAR science](https://science.nasa.gov/mission/nisar/science-behind-the-mission/) - ecosystems, solid Earth, cryosphere, and coastal science families.
- [NASA NISAR data](https://science.nasa.gov/mission/nisar/data/) - current mission data resources and coverage material.

The application white papers are mission-planning documents from 2017. They establish user problems,
not current service-level guarantees. Current product maturity and availability must be checked
against ASF before every production release.

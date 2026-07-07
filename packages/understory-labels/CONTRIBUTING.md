# Contributing labels

The labeled library is the asset whose integrity matters most; retrofitting rigor onto a contaminated dataset is nearly impossible. So the review standard is documented even while the reviewer is a single maintainer.

## What counts as "confirmed"

An event may be marked `confirmed` only with at least one of:

1. **Field verification** — a person or partner organization observed the disturbance on the ground, with a date.
2. **External institutional record** — the event appears in an independent published source (e.g. Imazon SAD, IBAMA enforcement records, DETER) with location and date window. Cite the record in `evidence_source`.
3. **Controlled experiment** — the disturbance was created deliberately at a known date/size/type (class `controlled-experiment`).

High-resolution optical imagery alone supports `candidate`, not `confirmed` — the whole premise of the project is that optical misses under-canopy activity, so optical absence is not evidence of absence, and optical presence without a date window is weak.

## What counts as "rejected"

A detection that was field-checked or record-checked and found to be natural decorrelation or noise. Rejected events must carry the same evidence quality as confirmed ones — "looked wrong on a screen" is not rejection.

## Mechanics

1. Add features to a GeoJSON FeatureCollection in `data/events/` (new file per source collection).
2. Every feature must validate: `uv run understory-labels-validate data/events/your-file.geojson` (CI enforces this).
3. Open a PR describing the evidence source. Sensitive locations (active enforcement, community monitors' patrol areas) are coarsened or embargoed by agreement with the source — raise this in the PR if in doubt.
4. Data releases are tagged `labels-vX.Y.Z` with a `data/CHANGELOG.md` entry.

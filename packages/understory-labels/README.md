# understory-labels

The open labeled library of forest disturbance events — potentially the most durable artifact of the whole project. A public, biome-indexed, ground-truthed dataset of "human disturbance vs. natural decorrelation" signatures, versioned separately from all code because open data outlives any pipeline.

- **Code** (schema models, validation tooling): Apache 2.0
- **Data** (`data/`): [CC-BY 4.0](LICENSE)

## Structure

- `schema/disturbance-event.schema.json` — the versioned JSON Schema. Breaking changes bump the schema version; data releases pin the schema they conform to.
- `data/events/` — event records as GeoJSON FeatureCollections, one file per source collection (e.g. `amazon-para-imazon.geojson`).
- `data/CHANGELOG.md` — every data release documents what was added, changed, and why.
- `src/understory_labels/` — pydantic models mirroring the schema, loaders, and the `understory-labels-validate` CLI that CI runs over every data file.

## The event record

Every event carries: geometry, a date window (disturbance events are rarely known to the day), a class (`selective-logging`, `access-road`, `mining`, `clearing`, `controlled-experiment`, `other`), a confirmation status (`confirmed` / `rejected` / `candidate`), the biome, and the evidence source. `rejected` events are first-class citizens: verified false alarms are exactly what a detector needs to learn from and what the benchmark needs to punish.

## Contributing labels

Label quality control is editorial work, not code review, and has its own standard — see [CONTRIBUTING.md](CONTRIBUTING.md).

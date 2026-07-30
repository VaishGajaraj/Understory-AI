# Understory viewer

A two-view web map over **one benchmark run**: a triage queue + map of the alerts, and a rendering
of the benchmark report. Vanilla TypeScript + [maplibre-gl], bundled with `bun build`. No React —
the app is read-mostly and re-renders from state on every change.

Everything on screen comes from files the pipeline wrote. There are no fixtures, no demo
detections, and no synthesised curves in `src/`.

## Run it against a real benchmark

```sh
make toy-bench                      # writes benchmarks/toy/reports/toy.json + toy-alerts.geojson
bun run --filter '@understory/viewer' dev      # http://localhost:5173
```

The dev server (`dev-server.ts`) bundles the app and serves the repository read-only alongside it,
so the browser can fetch the run's own output. By default the viewer loads:

| source | default |
| --- | --- |
| report JSON | `/benchmarks/toy/reports/toy.json` |
| alert GeoJSON | `<benchmark>-alerts.geojson` beside the report |
| label collection | `/packages/understory-labels/data/events/toy-fixtures.geojson` |
| AOI outline | none |

Override any of them with query parameters — `?report=…&alerts=…&labels=…&aoi=…`. For example,
once the Pará benchmark has run:

```
http://localhost:5173/?report=/benchmarks/amazon-para/reports/amazon-para.json&labels=/packages/understory-labels/data/events/amazon-para-imazon.geojson
```

A production bundle goes to `dist/`:

```sh
bun run --filter '@understory/viewer' build
```

`dist/` assumes the report, alerts and labels are reachable at the paths above; serve it from the
repository root, or pass absolute URLs in the query string.

If a file is missing or a required field is absent, the app renders a failure panel naming the file
and the field rather than a plausible-looking screen. Benchmark tooling that silently defaults a
metric is broken tooling.

## What the viewer computes itself

- **Detection ↔ label matching** (`src/triage.ts`) mirrors `understory_detect.scoring.match_detections`:
  greedy, one-to-one, highest score first, nearest centroid within the distance and temporal
  tolerances **recorded in the report**. Confirmed labels are matched first, so the matched set
  reproduces the report's true positives; leftover detections are then offered the non-confirmed
  labels, which is how an alert lands on a verified false alarm.
- **Status**: a detection inherits the status of the label it matched (confirmed / rejected),
  otherwise it is a candidate. Confirm/Reject in the inspector overrides this locally for the
  session — promoting a decision into the label library is a reviewed pull request against
  `packages/understory-labels`, never a click here.
- **Centroid Δ, latency, lead over optical** are derived from the matched label using the same
  arithmetic as the Python side (`_distance_m`, date-only differences).
- **Cross-checks** that the three files describe one run. Report and alerts must carry the same
  detection ids. The label collection is checked against the counts the harness derived from it —
  `n_events`, `n_events_with_optical_record`, and which `recall_by_area_ha` bins exist — because
  `?labels=` is free-form and the wrong collection makes the Alerts tab say "no matching label"
  while the Report tab prints a true positive. A collection that disagrees is refused by name. The
  report records no identifier for the collection it scored (`labels_version` is the
  understory-labels *package* version), so a different collection with the same counts still
  passes: the strip under the header says so rather than implying more than was proved.
- **Export** writes `<benchmark>-alerts.geojson` in the pipeline's own format
  (`cli.detections_to_geojson`): snake_case properties, highest score first, same collection-level
  `properties` block, plus two viewer-added fields — `triage_status` and `matched_label_id`.

## Fields the pipeline does not emit (shown honestly, never invented)

| design element | status |
| --- | --- |
| coherence sparkline | **Degraded.** No detector emits a per-detection time series, so the panel says so. If a report ever carries `coherence_series` on a detection, the chart plots that series — and only that series. |
| baseline envelope on the sparkline | **Absent.** The detector's baseline is a rolling median + scaled MAD over a trailing window with `anomaly_sigma` from the benchmark config (`understory_detect/baseline.py`); the report carries none of it. The chart draws no threshold line and no ±σ band, because deriving either from the plotted points would describe a decision rule that never ran. |
| linearity | **Conditional.** Computed in `understory_detect.events`, then dropped before `Detection`. The inspector tile appears only when the field is present. |
| run history | **Degraded.** There is no run index — each benchmark has one report path, overwritten in place. The table shows the loaded run and says why it is alone. |
| run timestamp | **Degraded.** The report records none; the viewer shows the report file's `Last-Modified`. |
| AOI outline | **Degraded.** The report does not carry the AOI, and the AOI files are YAML. Without `?aoi=<geojson>` the map fits the data and the caption says the outline is missing. |
| per-area-bin event counts | **Absent.** `recall_by_area_ha` carries rates only, so the bars show recall without an `n`. |
| lead vs optical, centroid Δ | **Computed** from the report and the label library (see above). |

Worth fixing upstream, in rough order of value to this app: put the AOI geometry, the run
timestamp and the label collection path into the report; carry `linearity` through to `Detection`;
emit per-bin event counts alongside `recall_by_area_ha`.

## Layout

```
index.html          entry; IBM Plex from Google Fonts
dev-server.ts       bundles the app, serves the repo read-only
src/types.ts        mirrors of the Python contracts (report, verdict, labels, alerts)
src/data.ts         fetch + parse + validate; the only place snake_case is mapped
src/triage.ts       pure matching / status / queue logic — no DOM, unit-tested
src/map.ts          MapLibre layers, ported from the prototype
src/alerts-view.ts  triage queue, map furniture, inspector
src/report-view.ts  the benchmark report
src/app.ts          shell, state, event delegation
src/app.css         the visual spec as a real stylesheet
design/             the design source of truth (understory-viewer.dc.html)
```

`design/understory-viewer.dc.html` is the design source of truth for colour, type and layout. It
hardcodes mock data — treat its numbers as illustration, its pixels as specification.

It is an export from Claude Design, not a runnable page: it references a `support.js` runtime that
interprets its `<x-dc>` elements and `{{ }}` bindings, and that runtime is not vendored here. Opening
it in a browser shows unstyled markup. Read it as a spec, or view it in the design tool.

## Checks

```sh
bun run fmt && bun run lint && bun run typecheck && bun test
```

[maplibre-gl]: https://maplibre.org/maplibre-gl-js/docs/

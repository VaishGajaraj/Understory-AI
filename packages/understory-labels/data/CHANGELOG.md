# Label data changelog

Every data release is tagged `labels-vX.Y.Z` and documented here.

## Unreleased

- Added `toy-fixtures.geojson`: two synthetic events (one confirmed linear feature, one rejected rain-decorrelation blob) used by the toy benchmark and CI. Not real disturbances.
- Schema: added optional `optical_alert_date` (first appearance in GLAD/RADD/DETER), enabling the detection-lead-over-optical metric. Toy road fixture carries a synthetic value.
- Enlarged the toy road to a ~2 km corridor (24 ha) so it exceeds the detector's minimum cluster size, matching realistic access-road geometry.

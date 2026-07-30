/**
 * Understory viewer — a thin web map over one benchmark run.
 *
 * It renders exactly what the pipeline wrote: the report JSON from
 * `understory-bench`, the `<benchmark>-alerts.geojson` beside it, and the
 * versioned label collection they were scored against. Nothing on screen is
 * synthesised by this app; README.md lists the fields the pipeline does not
 * emit yet and how each is degraded.
 */

import { bootstrap } from './app'

export type * from './types'

const root = document.getElementById('root')
if (root) {
  void bootstrap(root)
}

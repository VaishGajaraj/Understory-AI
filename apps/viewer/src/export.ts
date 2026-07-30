/**
 * Export the loaded, triaged detections back out in the pipeline's own alert
 * format (cli.detections_to_geojson): snake_case properties, highest score
 * first, same top-level `properties` block.
 *
 * Two fields are added, both of them the viewer's own opinion rather than the
 * pipeline's:
 *
 * - `triage_status` — the resolved status, which is the label-derived one
 *   unless a click in this session overrode it;
 * - `matched_label_id` — the label this detection matched, according to the
 *   viewer's reimplementation of the matcher in ./triage.ts. It reproduces
 *   understory_detect.scoring.match_detections rather than being read off the
 *   report, which carries no per-detection match, so it is the viewer's answer
 *   and not the harness's.
 */

import type { FeatureCollection } from 'geojson'

import type { TriageRow } from './triage'
import type { BenchmarkReport } from './types'

export function detectionsToGeoJson(rows: TriageRow[], report: BenchmarkReport): FeatureCollection {
  const ordered = [...rows].sort((a, b) => b.detection.score - a.detection.score)
  return {
    type: 'FeatureCollection',
    properties: {
      benchmark: report.benchmark,
      detector: `${report.detector} ${report.detectorVersion}`,
      methodology_version: report.methodologyVersion,
    },
    features: ordered.map((row) => ({
      type: 'Feature',
      geometry: row.detection.geometry,
      properties: {
        id: row.detection.id,
        score: row.detection.score,
        first_seen: row.detection.firstSeen,
        last_seen: row.detection.lastSeen,
        persistence_passes: row.detection.persistencePasses,
        area_ha: row.detection.areaHa ?? null,
        triage_status: row.status,
        matched_label_id: row.match?.label.id ?? null,
      },
    })),
  } as FeatureCollection
}

export function downloadAlerts(rows: TriageRow[], report: BenchmarkReport): void {
  const collection = detectionsToGeoJson(rows, report)
  const blob = new Blob([`${JSON.stringify(collection, null, 2)}\n`], {
    type: 'application/geo+json',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${report.benchmark}-alerts.geojson`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

import { describe, expect, test } from 'bun:test'

import { detectionsToGeoJson } from './export'
import { buildRows } from './triage'
import type { BenchmarkReport, Detection, DisturbanceEvent, MatchingTolerances } from './types'

const TOLERANCES: MatchingTolerances = {
  maxCentroidDistanceM: 500,
  minSpatialIou: 0,
  temporalWindowDays: 36,
}

const point = (lon: number, lat: number): Detection['geometry'] => ({
  type: 'Point',
  coordinates: [lon, lat],
})

const detections: Detection[] = [
  {
    id: 'v0-filters-toy-002',
    geometry: point(-55.5, -7),
    firstSeen: '2026-03-07T00:00:00',
    lastSeen: '2026-03-19T00:00:00',
    score: 0.42,
    persistencePasses: 2,
    areaHa: 3.1,
  },
  {
    id: 'v0-filters-toy-001',
    geometry: point(-55, -7),
    firstSeen: '2026-02-23T00:00:00',
    lastSeen: '2026-03-07T00:00:00',
    score: 0.875,
    persistencePasses: 3,
    areaHa: 24.7,
  },
]

const labels: DisturbanceEvent[] = [
  {
    id: 'toy-road-001',
    geometry: point(-55, -7),
    dateWindow: { start: '2026-02-01', end: '2026-02-13' },
    eventClass: 'access-road',
    status: 'confirmed',
    biome: 'toy',
    evidenceSource: 'synthetic fixture — generated, not observed',
    locationPrecision: 'exact',
  },
]

const report = {
  benchmark: 'toy',
  detector: 'v0-filters',
  detectorVersion: '0.1.0',
  methodologyVersion: '0.1.0',
} as BenchmarkReport

describe('alert export', () => {
  const rows = buildRows(detections, labels, TOLERANCES, { 'v0-filters-toy-002': 'rejected' })
  const collection = detectionsToGeoJson(rows, report)

  test('matches the collection header the pipeline writes', () => {
    expect(collection).toMatchObject({
      type: 'FeatureCollection',
      properties: {
        benchmark: 'toy',
        detector: 'v0-filters 0.1.0',
        methodology_version: '0.1.0',
      },
    })
  })

  test('highest score first, snake_case properties', () => {
    expect(collection.features.map((f) => f.properties?.id)).toEqual([
      'v0-filters-toy-001',
      'v0-filters-toy-002',
    ])
    expect(collection.features[0]?.properties).toEqual({
      id: 'v0-filters-toy-001',
      score: 0.875,
      first_seen: '2026-02-23T00:00:00',
      last_seen: '2026-03-07T00:00:00',
      persistence_passes: 3,
      area_ha: 24.7,
      triage_status: 'confirmed',
      matched_label_id: 'toy-road-001',
    })
  })

  test('carries the triage decision made in the browser', () => {
    expect(collection.features[1]?.properties?.triage_status).toBe('rejected')
    expect(collection.features[1]?.properties?.matched_label_id).toBeNull()
  })
})

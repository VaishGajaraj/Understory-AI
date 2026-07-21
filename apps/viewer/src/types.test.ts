import { describe, expect, test } from 'bun:test'

import type { DisturbanceEvent } from './types'

// Mirrors packages/understory-labels/data/events/toy-fixtures.geojson —
// if the schema and these types drift apart, this fixture is where it shows.
const toyRoad: DisturbanceEvent = {
  id: 'toy-road-001',
  geometry: { type: 'Point', coordinates: [-55.0, -7.001] },
  dateWindow: { start: '2026-02-01', end: '2026-02-13' },
  eventClass: 'access-road',
  status: 'confirmed',
  biome: 'toy',
  evidenceSource: 'synthetic fixture — generated, not observed',
  areaHa: 24.0,
  opticalAlertDate: '2026-03-20',
  locationPrecision: 'exact',
}

describe('label type contract', () => {
  test('toy fixture event satisfies DisturbanceEvent', () => {
    expect(toyRoad.status).toBe('confirmed')
    expect(toyRoad.dateWindow.start < toyRoad.dateWindow.end).toBe(true)
  })
})

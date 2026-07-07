/**
 * TypeScript mirrors of the Python-side data contracts.
 *
 * The source of truth is the JSON Schema in packages/understory-labels/schema/
 * and the detection GeoParquet/GeoJSON emitted by understory-detect. These
 * types must track those schemas — when the schema versions bump, update here.
 */

export type ConfirmationStatus = 'confirmed' | 'rejected' | 'candidate'

export type DisturbanceClass =
  | 'selective-logging'
  | 'access-road'
  | 'mining'
  | 'clearing'
  | 'controlled-experiment'
  | 'other'

/** One labeled event from the understory-labels library. */
export interface DisturbanceEvent {
  id: string
  geometry: GeoJSON.Geometry
  dateWindow: { start: string; end: string }
  class: DisturbanceClass
  status: ConfirmationStatus
  biome: string
  evidenceSource: string
  areaHa?: number
}

/** One detection emitted by a detector run. */
export interface Detection {
  id: string
  geometry: GeoJSON.Geometry
  firstSeen: string
  lastSeen: string
  score: number
  persistencePasses: number
}

/** A machine-generated benchmark report (never hand-assembled). */
export interface BenchmarkReport {
  benchmark: string
  detector: string
  labelsVersion: string
  methodologyVersion: string
  eventPrecision: number
  eventRecall: number
  f1: number
  medianDetectionLatencyDays: number | null
  medianLeadOverOpticalDays: number | null
}

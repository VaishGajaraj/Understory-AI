/**
 * TypeScript mirrors of the Python-side data contracts.
 *
 * The source of truth is the JSON Schema in packages/understory-labels/schema/
 * and the report JSON + alert GeoJSON emitted by understory-detect
 * (scoring.BenchmarkReport, kill_criteria.KillCriteriaVerdict,
 * interface.Detection, cli.detections_to_geojson). These types must track
 * those schemas — when the schema versions bump, update here.
 *
 * Python speaks snake_case on the wire; everything below is camelCase and the
 * mapping happens in exactly one place (./data.ts). The one exception is
 * `AlertProperties`, which is the on-disk shape of the alert GeoJSON and so
 * keeps the pipeline's property names verbatim.
 */

import type { Geometry } from 'geojson'

export type ConfirmationStatus = 'confirmed' | 'rejected' | 'candidate'

export type DisturbanceClass =
  | 'selective-logging'
  | 'access-road'
  | 'mining'
  | 'clearing'
  | 'controlled-experiment'
  | 'other'

export type LocationPrecision = 'exact' | 'coarsened'

export interface DateWindow {
  start: string
  end: string
}

/** One labeled event from the understory-labels library. */
export interface DisturbanceEvent {
  id: string
  geometry: Geometry
  dateWindow: DateWindow
  eventClass: DisturbanceClass
  status: ConfirmationStatus
  biome: string
  evidenceSource: string
  areaHa?: number
  /** First appearance in GLAD/RADD/DETER, when known — drives lead-over-optical. */
  opticalAlertDate?: string
  notes?: string
  locationPrecision: LocationPrecision
}

/** Per-pair coherence sample. No detector emits these yet — see Detection. */
export interface CoherenceSample {
  /** Midpoint of the interferometric pair. */
  date: string
  coherence: number
}

/** One detection emitted by a detector run (understory_detect.interface.Detection). */
export interface Detection {
  id: string
  geometry: Geometry
  firstSeen: string
  lastSeen: string
  score: number
  persistencePasses: number
  areaHa?: number
  /**
   * Computed in understory_detect.events but dropped before Detection, so it is
   * absent from every current report. Read, never invented: the viewer omits
   * the inspector tile when the field is missing.
   */
  linearity?: number
  /**
   * Per-detection coherence series. No detector emits this yet; the inspector
   * shows an explicit placeholder rather than a synthesised curve.
   */
  coherenceSeries?: CoherenceSample[]
}

/** scoring.MatchingTolerances — the matching rules, recorded in every report. */
export interface MatchingTolerances {
  maxCentroidDistanceM: number
  minSpatialIou: number
  temporalWindowDays: number
}

/** scoring.CalibrationBin, plus the bin key it was stored under. */
export interface CalibrationBin {
  bin: string
  meanScore: number
  confirmRate: number
  n: number
}

/** scoring.CalibrationReport. */
export interface CalibrationReport {
  bins: CalibrationBin[]
  expectedCalibrationError: number | null
}

/** One entry of scoring.BenchmarkReport.recall_by_area_ha. */
export interface RecallByAreaBin {
  bin: string
  recall: number
}

export type KillCriterionStatus = 'PASS' | 'FAIL' | 'INSUFFICIENT_DATA'

/** kill_criteria.Criterion. */
export interface KillCriterion {
  name: string
  threshold: string
  observed: string
  status: KillCriterionStatus
  note: string
}

/**
 * kill_criteria.KillCriteriaVerdict. `alive` is a Python @property and so is
 * not serialised — the viewer recomputes it under the same rule (nothing FAILs).
 */
export interface KillCriteriaVerdict {
  criteria: KillCriterion[]
  synthetic: boolean
  alive: boolean
}

/** A machine-generated benchmark report (never hand-assembled). */
export interface BenchmarkReport {
  benchmark: string
  detector: string
  detectorVersion: string
  labelsVersion: string
  methodologyVersion: string
  tolerances: MatchingTolerances
  nEvents: number
  nDetections: number
  truePositives: number
  falsePositives: number
  falseNegatives: number
  eventPrecision: number
  eventRecall: number
  f1: number
  medianDetectionLatencyDays: number | null
  medianLeadOverOpticalDays: number | null
  nEventsWithOpticalRecord: number
  recallByAreaHa: RecallByAreaBin[]
  calibration: CalibrationReport
  killCriteria: KillCriteriaVerdict
  detections: Detection[]
}

/**
 * Properties of one feature in `<benchmark>-alerts.geojson`, verbatim as
 * cli.detections_to_geojson writes them. The export button round-trips this
 * shape, so the names stay snake_case.
 */
export interface AlertProperties {
  id: string
  score: number
  first_seen: string
  last_seen: string
  persistence_passes: number
  area_ha: number | null
}

/** Top-level `properties` block of the alert FeatureCollection. */
export interface AlertCollectionProperties {
  benchmark: string
  detector: string
  methodology_version: string
}

/**
 * Triage logic — pure, DOM-free, unit-tested.
 *
 * Detection-to-label matching mirrors understory_detect.scoring.match_detections
 * exactly: greedy, one-to-one, highest score first, nearest centroid inside the
 * distance and temporal tolerances the report itself records. Confirmed labels
 * are matched first (that pass reproduces the report's true positives); the
 * remaining detections are then offered the non-confirmed labels, which is how
 * a detection lands on a verified false alarm.
 */

import type { Geometry, Position } from 'geojson'

import type { Detection, DisturbanceEvent, MatchingTolerances } from './types'

export type TriageStatus = 'candidate' | 'confirmed' | 'rejected'
export type QueueFilter = 'all' | TriageStatus
export type QueueSort = 'score' | 'recent'

export const TRIAGE_STATUSES: TriageStatus[] = ['candidate', 'confirmed', 'rejected']
export const QUEUE_FILTERS: QueueFilter[] = ['all', 'candidate', 'confirmed', 'rejected']

export interface LabelMatch {
  label: DisturbanceEvent
  /** Centroid separation in metres, same approximation as scoring._distance_m. */
  distanceM: number
  /** first_seen minus the label window start, in days (negative = early). */
  latencyDays: number
  /** optical_alert_date minus first_seen, in days. Positive = radar saw it first. */
  leadOverOpticalDays: number | null
}

export interface TriageRow {
  detection: Detection
  match: LabelMatch | null
  status: TriageStatus
  /** True when the status came from a click in this session, not from the labels. */
  overridden: boolean
}

/** Local, session-only triage decisions keyed by detection id. */
export type TriageOverrides = Record<string, TriageStatus>

export function buildRows(
  detections: Detection[],
  labels: DisturbanceEvent[],
  tolerances: MatchingTolerances,
  overrides: TriageOverrides = {},
): TriageRow[] {
  const matches = matchDetections(detections, labels, tolerances)
  return detections.map((detection) => {
    const match = matches.get(detection.id) ?? null
    const override = overrides[detection.id]
    return {
      detection,
      match,
      status: override ?? statusFromMatch(match),
      overridden: override !== undefined,
    }
  })
}

/** A detection inherits the status of the label it matched; otherwise it is a candidate. */
export function statusFromMatch(match: LabelMatch | null): TriageStatus {
  if (!match) return 'candidate'
  return match.label.status === 'confirmed'
    ? 'confirmed'
    : match.label.status === 'rejected'
      ? 'rejected'
      : 'candidate'
}

export function matchDetections(
  detections: Detection[],
  labels: DisturbanceEvent[],
  tolerances: MatchingTolerances,
): Map<string, LabelMatch> {
  const matched = new Map<string, LabelMatch>()
  const confirmed = labels.filter((l) => l.status === 'confirmed')
  const rest = labels.filter((l) => l.status !== 'confirmed')
  const taken = new Set<string>()
  greedyPass(detections, confirmed, tolerances, matched, taken)
  const leftovers = detections.filter((d) => !matched.has(d.id))
  greedyPass(leftovers, rest, tolerances, matched, taken)
  return matched
}

function greedyPass(
  detections: Detection[],
  labels: DisturbanceEvent[],
  tolerances: MatchingTolerances,
  matched: Map<string, LabelMatch>,
  taken: Set<string>,
): void {
  const byScore = [...detections].sort((a, b) => b.score - a.score)
  for (const detection of byScore) {
    const centre = centroid(detection.geometry)
    let best: DisturbanceEvent | null = null
    let bestDistance = Number.POSITIVE_INFINITY
    for (const label of labels) {
      if (taken.has(label.id)) continue
      if (!temporallyCompatible(detection, label, tolerances.temporalWindowDays)) continue
      const distance = distanceM(centre, centroid(label.geometry))
      if (distance <= tolerances.maxCentroidDistanceM && distance < bestDistance) {
        best = label
        bestDistance = distance
      }
    }
    if (best) {
      taken.add(best.id)
      matched.set(detection.id, {
        label: best,
        distanceM: bestDistance,
        latencyDays: daysBetween(best.dateWindow.start, detection.firstSeen),
        leadOverOpticalDays: best.opticalAlertDate
          ? daysBetween(detection.firstSeen, best.opticalAlertDate)
          : null,
      })
    }
  }
}

export function temporallyCompatible(
  detection: Detection,
  label: DisturbanceEvent,
  windowDays: number,
): boolean {
  const firstSeen = dayNumber(detection.firstSeen)
  return (
    dayNumber(label.dateWindow.start) - windowDays <= firstSeen &&
    firstSeen <= dayNumber(label.dateWindow.end) + windowDays
  )
}

// --- queue -----------------------------------------------------------------

export type FilterCounts = Record<QueueFilter, number>

export function filterCounts(rows: TriageRow[]): FilterCounts {
  const counts: FilterCounts = { all: rows.length, candidate: 0, confirmed: 0, rejected: 0 }
  for (const row of rows) counts[row.status] += 1
  return counts
}

export function applyFilter(rows: TriageRow[], filter: QueueFilter): TriageRow[] {
  return filter === 'all' ? [...rows] : rows.filter((row) => row.status === filter)
}

export function sortQueue(rows: TriageRow[], sort: QueueSort): TriageRow[] {
  const sorted = [...rows]
  sorted.sort((a, b) =>
    sort === 'recent'
      ? b.detection.firstSeen.localeCompare(a.detection.firstSeen) ||
        b.detection.score - a.detection.score
      : b.detection.score - a.detection.score ||
        b.detection.firstSeen.localeCompare(a.detection.firstSeen),
  )
  return sorted
}

export function queueFor(rows: TriageRow[], filter: QueueFilter, sort: QueueSort): TriageRow[] {
  return sortQueue(applyFilter(rows, filter), sort)
}

/** The detection window actually covered by this run: earliest first, latest last. */
export function detectionWindow(detections: Detection[]): { start: string; end: string } | null {
  if (detections.length === 0) return null
  let start = detections[0]?.firstSeen ?? ''
  let end = detections[0]?.lastSeen ?? ''
  for (const d of detections) {
    if (d.firstSeen < start) start = d.firstSeen
    if (d.lastSeen > end) end = d.lastSeen
  }
  return { start: isoDate(start), end: isoDate(end) }
}

// --- geometry --------------------------------------------------------------

/**
 * Centroid, reproducing shapely's `shape(geometry).centroid` — the Python
 * matcher takes distances between those points, so anything else here would
 * make the two sides disagree on a geometry type the label schema allows.
 *
 * GEOS (shapely's engine) walks every component of a geometry once and keeps
 * three running sums — area, length, points — then answers with the highest
 * dimension actually present:
 *
 * - non-zero total area  → area-weighted centroid, interior rings subtracted;
 * - else non-zero length → length-weighted midpoint of every segment;
 * - else                 → arithmetic mean of the points.
 *
 * That single rule covers every case: a MultiPolygon is area-weighted across
 * its parts, a collapsed (zero-area) polygon answers with the line centroid of
 * its own boundary, a zero-length line answers with its vertex, and a
 * GeometryCollection answers from its highest-dimension members because the
 * lower-dimension sums are never consulted.
 */
export function centroid(geometry: Geometry): [number, number] {
  const sums = emptySums()
  accumulate(sums, geometry)
  return resolve(sums)
}

/** The three running sums GEOS keeps while it walks a geometry. */
interface CentroidSums {
  /** Signed 2×area, sign normalised so shells subtract and holes add. */
  areaSum2: number
  areaX: number
  areaY: number
  length: number
  lengthX: number
  lengthY: number
  points: number
  pointX: number
  pointY: number
}

function emptySums(): CentroidSums {
  return {
    areaSum2: 0,
    areaX: 0,
    areaY: 0,
    length: 0,
    lengthX: 0,
    lengthY: 0,
    points: 0,
    pointX: 0,
    pointY: 0,
  }
}

function accumulate(sums: CentroidSums, geometry: Geometry): void {
  switch (geometry.type) {
    case 'Point':
      addPoint(sums, xy(geometry.coordinates))
      break
    case 'MultiPoint':
      for (const point of geometry.coordinates) addPoint(sums, xy(point))
      break
    case 'LineString':
      addSegments(sums, geometry.coordinates)
      break
    case 'MultiLineString':
      for (const line of geometry.coordinates) addSegments(sums, line)
      break
    case 'Polygon':
      addPolygon(sums, geometry.coordinates)
      break
    case 'MultiPolygon':
      for (const polygon of geometry.coordinates) addPolygon(sums, polygon)
      break
    case 'GeometryCollection':
      for (const member of geometry.geometries) accumulate(sums, member)
      break
  }
}

function resolve(sums: CentroidSums): [number, number] {
  if (sums.areaSum2 !== 0) {
    return [sums.areaX / (3 * sums.areaSum2), sums.areaY / (3 * sums.areaSum2)]
  }
  if (sums.length > 0) return [sums.lengthX / sums.length, sums.lengthY / sums.length]
  if (sums.points > 0) return [sums.pointX / sums.points, sums.pointY / sums.points]
  // Shapely answers POINT EMPTY here and the Python matcher raises when it
  // reads .x off it. NaN travels through distanceM to a comparison that is
  // false, so an empty geometry matches nothing instead of matching at 0°,0°.
  return [Number.NaN, Number.NaN]
}

function addPolygon(sums: CentroidSums, rings: Position[][]): void {
  const [shell, ...holes] = rings
  if (!shell || shell.length === 0) return
  addRing(sums, shell, false)
  for (const hole of holes) addRing(sums, hole, true)
}

/**
 * One ring: area triangles fanned from its first vertex, plus its own segments.
 * GEOS keeps both, because the segments are what answers for a ring whose area
 * cancels to zero.
 *
 * The triangle sign is taken from the ring's own signed area so that shells
 * always subtract and holes always add whichever way the ring is wound — GEOS
 * reads the winding with Orientation::isCCW instead, which agrees with the
 * signed area for every ring that does not cross itself.
 */
function addRing(sums: CentroidSums, coordinates: Position[], isHole: boolean): void {
  addSegments(sums, coordinates)
  const base = xy(coordinates[0])
  let signed2 = 0
  let x = 0
  let y = 0
  for (let i = 1; i < coordinates.length - 1; i++) {
    const p1 = xy(coordinates[i])
    const p2 = xy(coordinates[i + 1])
    const area2 = (p1[0] - base[0]) * (p2[1] - base[1]) - (p2[0] - base[0]) * (p1[1] - base[1])
    signed2 += area2
    x += area2 * (base[0] + p1[0] + p2[0])
    y += area2 * (base[1] + p1[1] + p2[1])
  }
  const sign = (signed2 > 0 ? -1 : 1) * (isHole ? -1 : 1)
  sums.areaSum2 += sign * signed2
  sums.areaX += sign * x
  sums.areaY += sign * y
}

/** Length-weighted segment midpoints; a zero-length component adds its vertex. */
function addSegments(sums: CentroidSums, coordinates: Position[]): void {
  let length = 0
  for (let i = 0; i < coordinates.length - 1; i++) {
    const a = xy(coordinates[i])
    const b = xy(coordinates[i + 1])
    const segment = Math.hypot(a[0] - b[0], a[1] - b[1])
    if (segment === 0) continue
    length += segment
    sums.lengthX += (segment * (a[0] + b[0])) / 2
    sums.lengthY += (segment * (a[1] + b[1])) / 2
  }
  sums.length += length
  if (length === 0 && coordinates.length > 0) addPoint(sums, xy(coordinates[0]))
}

function addPoint(sums: CentroidSums, point: [number, number]): void {
  sums.points += 1
  sums.pointX += point[0]
  sums.pointY += point[1]
}

function xy(position: Position | undefined): [number, number] {
  return [position?.[0] ?? 0, position?.[1] ?? 0]
}

/** Same approximation as scoring._distance_m, so distances agree with the report. */
export function distanceM(a: [number, number], b: [number, number]): number {
  const lat = (((a[1] + b[1]) / 2) * Math.PI) / 180
  const dx = (a[0] - b[0]) * 111_320 * Math.cos(lat)
  const dy = (a[1] - b[1]) * 110_540
  return Math.hypot(dx, dy)
}

export function bboxOf(geometries: Geometry[]): [number, number, number, number] | null {
  let west = Number.POSITIVE_INFINITY
  let south = Number.POSITIVE_INFINITY
  let east = Number.NEGATIVE_INFINITY
  let north = Number.NEGATIVE_INFINITY
  for (const geometry of geometries) {
    for (const [lon, lat] of positionsOf(geometry)) {
      west = Math.min(west, lon)
      east = Math.max(east, lon)
      south = Math.min(south, lat)
      north = Math.max(north, lat)
    }
  }
  return Number.isFinite(west) ? [west, south, east, north] : null
}

function positionsOf(geometry: Geometry): [number, number][] {
  switch (geometry.type) {
    case 'Point':
      return [[geometry.coordinates[0] ?? 0, geometry.coordinates[1] ?? 0]]
    case 'MultiPoint':
    case 'LineString':
      return geometry.coordinates.map((p) => [p[0] ?? 0, p[1] ?? 0])
    case 'MultiLineString':
    case 'Polygon':
      return geometry.coordinates.flat().map((p) => [p[0] ?? 0, p[1] ?? 0])
    case 'MultiPolygon':
      return geometry.coordinates.flat(2).map((p) => [p[0] ?? 0, p[1] ?? 0])
    case 'GeometryCollection':
      return geometry.geometries.flatMap(positionsOf)
  }
}

// --- dates -----------------------------------------------------------------

/** Date part of an ISO date or datetime — the pipeline compares dates, not instants. */
export function isoDate(value: string): string {
  return value.slice(0, 10)
}

function dayNumber(value: string): number {
  const parsed = Date.parse(`${isoDate(value)}T00:00:00Z`)
  if (Number.isNaN(parsed)) throw new Error(`not an ISO date: ${value}`)
  return Math.round(parsed / 86_400_000)
}

/** Whole days from `from` to `to`, both ISO dates or datetimes. */
export function daysBetween(from: string, to: string): number {
  return dayNumber(to) - dayNumber(from)
}

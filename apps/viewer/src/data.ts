/**
 * Load the three files a benchmark run leaves behind and turn them into the
 * types in ./types.ts. This is the only module that knows the pipeline's
 * snake_case names.
 *
 * Nothing here invents a value. A missing file or a missing required field is
 * a hard error with the file name and the field path in the message: this is a
 * benchmark tool, and a silently defaulted metric is a defect, not a nicety.
 */

import type { Feature, FeatureCollection, Geometry } from 'geojson'

import type {
  AlertCollectionProperties,
  AlertProperties,
  BenchmarkReport,
  CalibrationBin,
  CalibrationReport,
  CoherenceSample,
  ConfirmationStatus,
  Detection,
  DisturbanceClass,
  DisturbanceEvent,
  KillCriteriaVerdict,
  KillCriterion,
  KillCriterionStatus,
  LocationPrecision,
  MatchingTolerances,
  RecallByAreaBin,
} from './types'

export class DataError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'DataError'
  }
}

/** Where the viewer reads from. Overridable per query parameter. */
export interface DataSources {
  /** Report JSON written by `understory-bench` (cli.run_benchmark). */
  report: string
  /** Alert GeoJSON. Defaults to `<benchmark>-alerts.geojson` beside the report. */
  alerts?: string
  /** Label collection GeoJSON from packages/understory-labels/data/events/. */
  labels: string
  /** Optional AOI outline (GeoJSON). The report does not carry one — see README. */
  aoi?: string
}

/** The toy benchmark is the only run that exists on a clean checkout. */
export const DEFAULT_SOURCES: DataSources = {
  report: '/benchmarks/toy/reports/toy.json',
  labels: '/packages/understory-labels/data/events/toy-fixtures.geojson',
}

export function sourcesFromQuery(search: string): DataSources {
  const params = new URLSearchParams(search)
  const report = params.get('report') ?? DEFAULT_SOURCES.report
  const labels = params.get('labels') ?? DEFAULT_SOURCES.labels
  const alerts = params.get('alerts') ?? undefined
  const aoi = params.get('aoi') ?? undefined
  return { report, labels, alerts, aoi }
}

export interface LoadedBenchmark {
  report: BenchmarkReport
  /** The alert layer as written next to the report, id-checked against it. */
  alerts: Feature<Geometry, AlertProperties>[]
  alertCollectionProperties: AlertCollectionProperties
  labels: DisturbanceEvent[]
  /** How far the loaded labels could be tied back to the run — see below. */
  labelCheck: LabelCrossCheck
  aoi: Geometry | null
  /**
   * The report file's Last-Modified header. The report itself records no run
   * timestamp, so this is the closest honest answer to "when did this run?" —
   * null when the server does not send one.
   */
  reportLastModified: string | null
  resolved: { report: string; alerts: string; labels: string; aoi: string | null }
}

type Fetcher = (url: string) => Promise<Response>

export async function loadBenchmark(
  sources: DataSources,
  fetcher: Fetcher = (url) => fetch(url),
): Promise<LoadedBenchmark> {
  const reportResponse = await fetchJson(sources.report, fetcher)
  const report = parseReport(reportResponse.json, sources.report)

  const alertsUrl =
    sources.alerts ?? siblingPath(sources.report, `${report.benchmark}-alerts.geojson`)
  const alertsJson = (await fetchJson(alertsUrl, fetcher)).json
  const { features: alerts, properties: alertCollectionProperties } = parseAlerts(
    alertsJson,
    alertsUrl,
  )
  assertSameRun(report, alerts, sources.report, alertsUrl)

  const labelsJson = (await fetchJson(sources.labels, fetcher)).json
  const labels = parseLabels(labelsJson, sources.labels)
  const labelCheck = crossCheckLabels(report, labels, sources.report, sources.labels)

  let aoi: Geometry | null = null
  if (sources.aoi) {
    aoi = parseAoi((await fetchJson(sources.aoi, fetcher)).json, sources.aoi)
  }

  return {
    report,
    alerts,
    alertCollectionProperties,
    labels,
    labelCheck,
    aoi,
    reportLastModified: reportResponse.lastModified,
    resolved: {
      report: sources.report,
      alerts: alertsUrl,
      labels: sources.labels,
      aoi: sources.aoi ?? null,
    },
  }
}

interface FetchedJson {
  json: unknown
  lastModified: string | null
}

async function fetchJson(url: string, fetcher: Fetcher): Promise<FetchedJson> {
  let response: Response
  try {
    response = await fetcher(url)
  } catch (cause) {
    throw new DataError(`${url}: request failed (${String(cause)})`)
  }
  if (!response.ok) {
    throw new DataError(
      [
        `${url}: HTTP ${response.status}.`,
        'Run `make toy-bench` (or point ?report= at a report your pipeline has actually written).',
      ].join(' '),
    )
  }
  try {
    return { json: await response.json(), lastModified: response.headers.get('last-modified') }
  } catch (cause) {
    throw new DataError(`${url}: not valid JSON (${String(cause)})`)
  }
}

export function siblingPath(path: string, filename: string): string {
  const cut = path.lastIndexOf('/')
  return cut < 0 ? filename : `${path.slice(0, cut + 1)}${filename}`
}

// --- report ----------------------------------------------------------------

export function parseReport(json: unknown, source: string): BenchmarkReport {
  const root = asObject(json, source, '')
  return {
    benchmark: str(root, 'benchmark', source),
    detector: str(root, 'detector', source),
    detectorVersion: str(root, 'detector_version', source),
    labelsVersion: str(root, 'labels_version', source),
    methodologyVersion: str(root, 'methodology_version', source),
    tolerances: parseTolerances(root.tolerances, source),
    nEvents: num(root, 'n_events', source),
    nDetections: num(root, 'n_detections', source),
    truePositives: num(root, 'true_positives', source),
    falsePositives: num(root, 'false_positives', source),
    falseNegatives: num(root, 'false_negatives', source),
    eventPrecision: num(root, 'event_precision', source),
    eventRecall: num(root, 'event_recall', source),
    f1: num(root, 'f1', source),
    medianDetectionLatencyDays: numOrNull(root, 'median_detection_latency_days', source),
    medianLeadOverOpticalDays: numOrNull(root, 'median_lead_over_optical_days', source),
    nEventsWithOpticalRecord: num(root, 'n_events_with_optical_record', source),
    recallByAreaHa: parseRecallByArea(root.recall_by_area_ha, source),
    calibration: parseCalibration(root.calibration, source),
    killCriteria: parseKillCriteria(root.kill_criteria, source),
    detections: parseDetections(root.detections, source),
  }
}

function parseTolerances(json: unknown, source: string): MatchingTolerances {
  const obj = asObject(json, source, 'tolerances')
  return {
    maxCentroidDistanceM: num(obj, 'max_centroid_distance_m', source, 'tolerances'),
    minSpatialIou: num(obj, 'min_spatial_iou', source, 'tolerances'),
    temporalWindowDays: num(obj, 'temporal_window_days', source, 'tolerances'),
  }
}

/** scoring.AREA_BINS_HA verbatim: name, inclusive lower edge, exclusive upper. */
const AREA_BIN_EDGES: [string, number, number][] = [
  ['0-1', 0, 1],
  ['1-2', 1, 2],
  ['2-5', 2, 5],
  ['5-20', 5, 20],
  ['20+', 20, Number.POSITIVE_INFINITY],
]

/** Area bins in the order scoring.AREA_BINS_HA declares them. */
export const AREA_BINS_HA = AREA_BIN_EDGES.map(([name]) => name)

function parseRecallByArea(json: unknown, source: string): RecallByAreaBin[] {
  const obj = asObject(json, source, 'recall_by_area_ha')
  const bins = Object.entries(obj).map(([bin, value]) => {
    if (typeof value !== 'number') {
      throw new DataError(`${source}: recall_by_area_ha.${bin} must be a number`)
    }
    return { bin, recall: value }
  })
  return bins.sort((a, b) => binOrder(a.bin) - binOrder(b.bin))
}

function binOrder(bin: string): number {
  const known = AREA_BINS_HA.indexOf(bin)
  return known >= 0 ? known : AREA_BINS_HA.length
}

function parseCalibration(json: unknown, source: string): CalibrationReport {
  const obj = asObject(json, source, 'calibration')
  const binsObj = asObject(obj.bins, source, 'calibration.bins')
  const bins: CalibrationBin[] = Object.entries(binsObj).map(([bin, value]) => {
    const path = `calibration.bins.${bin}`
    const binObj = asObject(value, source, path)
    return {
      bin,
      meanScore: num(binObj, 'mean_score', source, path),
      confirmRate: num(binObj, 'confirm_rate', source, path),
      n: num(binObj, 'n', source, path),
    }
  })
  bins.sort((a, b) => b.meanScore - a.meanScore)
  const ece = obj.expected_calibration_error
  if (ece !== null && ece !== undefined && typeof ece !== 'number') {
    throw new DataError(
      `${source}: calibration.expected_calibration_error must be a number or null`,
    )
  }
  return { bins, expectedCalibrationError: ece ?? null }
}

const KILL_STATUSES: KillCriterionStatus[] = ['PASS', 'FAIL', 'INSUFFICIENT_DATA']

function parseKillCriteria(json: unknown, source: string): KillCriteriaVerdict {
  const obj = asObject(json, source, 'kill_criteria')
  const rawCriteria = obj.criteria
  if (!Array.isArray(rawCriteria)) {
    throw new DataError(`${source}: kill_criteria.criteria must be an array`)
  }
  const criteria: KillCriterion[] = rawCriteria.map((raw, i) => {
    const path = `kill_criteria.criteria[${i}]`
    const c = asObject(raw, source, path)
    const status = str(c, 'status', source, path)
    if (!(KILL_STATUSES as string[]).includes(status)) {
      throw new DataError(`${source}: ${path}.status is "${status}", not one of ${KILL_STATUSES}`)
    }
    return {
      name: str(c, 'name', source, path),
      threshold: str(c, 'threshold', source, path),
      observed: str(c, 'observed', source, path),
      status: status as KillCriterionStatus,
      note: typeof c.note === 'string' ? c.note : '',
    }
  })
  // kill_criteria.KillCriteriaVerdict.alive is a @property, not a serialised
  // field; recompute it here under exactly the same rule.
  return {
    criteria,
    synthetic: bool(obj, 'synthetic', source, 'kill_criteria'),
    alive: criteria.every((c) => c.status !== 'FAIL'),
  }
}

function parseDetections(json: unknown, source: string): Detection[] {
  if (!Array.isArray(json)) {
    throw new DataError(
      `${source}: "detections" must be an array — cli.run_benchmark writes one per run`,
    )
  }
  return json.map((raw, i) => {
    const path = `detections[${i}]`
    const d = asObject(raw, source, path)
    return {
      id: str(d, 'id', source, path),
      geometry: geometry(d.geometry, source, `${path}.geometry`),
      firstSeen: str(d, 'first_seen', source, path),
      lastSeen: str(d, 'last_seen', source, path),
      score: num(d, 'score', source, path),
      persistencePasses: num(d, 'persistence_passes', source, path),
      areaHa: optionalNum(d.area_ha, source, `${path}.area_ha`),
      linearity: optionalNum(d.linearity, source, `${path}.linearity`),
      coherenceSeries: parseCoherenceSeries(d.coherence_series, source, path),
    }
  })
}

function parseCoherenceSeries(
  json: unknown,
  source: string,
  path: string,
): CoherenceSample[] | undefined {
  if (json === undefined || json === null) return undefined
  if (!Array.isArray(json)) {
    throw new DataError(`${source}: ${path}.coherence_series must be an array when present`)
  }
  return json.map((raw, i) => {
    const at = `${path}.coherence_series[${i}]`
    const sample = asObject(raw, source, at)
    return {
      date: str(sample, 'date', source, at),
      coherence: num(sample, 'coherence', source, at),
    }
  })
}

// --- alerts ----------------------------------------------------------------

export function parseAlerts(
  json: unknown,
  source: string,
): { features: Feature<Geometry, AlertProperties>[]; properties: AlertCollectionProperties } {
  const collection = asFeatureCollection(json, source)
  // The collection-level `properties` block is an Understory extension to
  // GeoJSON (cli.detections_to_geojson writes it), so it is read off the raw
  // object rather than the typed FeatureCollection.
  const props = asObject(asObject(json, source, '').properties, source, 'properties')
  const features = collection.features.map((raw, i) => {
    const path = `features[${i}]`
    const feature = asObject(raw, source, path)
    // Property failures are reported at features[i].properties.<key> — the path
    // that exists in the file, so it can be pasted straight into a debugger.
    const props = `${path}.properties`
    const p = asObject(feature.properties, source, props)
    return {
      type: 'Feature' as const,
      geometry: geometry(feature.geometry, source, `${path}.geometry`),
      properties: {
        id: str(p, 'id', source, props),
        score: num(p, 'score', source, props),
        first_seen: str(p, 'first_seen', source, props),
        last_seen: str(p, 'last_seen', source, props),
        persistence_passes: num(p, 'persistence_passes', source, props),
        area_ha: optionalNum(p.area_ha, source, `${props}.area_ha`) ?? null,
      },
    }
  })
  return {
    features,
    properties: {
      benchmark: str(props, 'benchmark', source, 'properties'),
      detector: str(props, 'detector', source, 'properties'),
      methodology_version: str(props, 'methodology_version', source, 'properties'),
    },
  }
}

/** The two files are written by one run; if their ids differ they are not. */
function assertSameRun(
  report: BenchmarkReport,
  alerts: Feature<Geometry, AlertProperties>[],
  reportSource: string,
  alertSource: string,
): void {
  const inReport = new Set(report.detections.map((d) => d.id))
  const inAlerts = new Set(alerts.map((f) => f.properties.id))
  const missing = [...inReport].filter((id) => !inAlerts.has(id))
  const extra = [...inAlerts].filter((id) => !inReport.has(id))
  if (missing.length || extra.length) {
    throw new DataError(
      [
        `${reportSource} and ${alertSource} describe different runs:`,
        `${missing.length} detection(s) only in the report (${missing.slice(0, 3).join(', ')}),`,
        `${extra.length} only in the alerts (${extra.slice(0, 3).join(', ')}).`,
        'Re-run the benchmark so both files come from one run.',
      ].join(' '),
    )
  }
}

// --- labels ----------------------------------------------------------------

/**
 * What could be proved about the loaded label collection, and what could not.
 *
 * `?labels=` is a free query parameter, so the collection on screen need not be
 * the one the run was scored against. When it is not, every detection falls
 * through to "candidate / no matching label" in the Alerts tab while the Report
 * tab keeps printing the stored precision, recall and true-positive counts —
 * two tabs contradicting each other, neither saying why.
 */
export interface LabelCrossCheck {
  /** The agreements that were actually established, shortest first. */
  agreed: string[]
  /** What this check cannot rule out. Rendered in the UI, never swallowed. */
  limits: string
}

/**
 * Cross-check the label collection against the report.
 *
 * The report carries no identifier for the collection it scored:
 * `labels_version` is `understory_labels.__version__` — the version of the
 * package that ran (cli.run_benchmark) — not a fingerprint of the events, and
 * the collection file carries no counterpart to compare it with. So the check
 * is over the three facts the harness derived from the collection and wrote
 * down: `n_events` (scoring.score counts confirmed labels),
 * `n_events_with_optical_record` (of those, the ones with an optical date) and
 * which `recall_by_area_ha` bins exist (the harness omits empty bins). A
 * collection disagreeing on any of them cannot be the one that was scored.
 *
 * The converse does not hold, which is what `limits` says out loud: a
 * different collection with the same counts passes this check.
 */
export function crossCheckLabels(
  report: BenchmarkReport,
  labels: DisturbanceEvent[],
  reportSource: string,
  labelsSource: string,
): LabelCrossCheck {
  const confirmed = labels.filter((label) => label.status === 'confirmed')
  const withOptical = confirmed.filter((label) => label.opticalAlertDate !== undefined)
  const bins = AREA_BIN_EDGES.filter(([, lo, hi]) =>
    confirmed.some(
      (label) => label.areaHa !== undefined && lo <= label.areaHa && label.areaHa < hi,
    ),
  ).map(([name]) => name)
  const reportedBins = report.recallByAreaHa.map((entry) => entry.bin)

  const disagreements = [
    report.nEvents === confirmed.length
      ? null
      : `the report scored ${report.nEvents} confirmed event(s), this collection has ${confirmed.length}`,
    report.nEventsWithOpticalRecord === withOptical.length
      ? null
      : `the report scored ${report.nEventsWithOpticalRecord} confirmed event(s) with an optical alert date, this collection has ${withOptical.length}`,
    sameSet(reportedBins, bins)
      ? null
      : `the report has recall for area bin(s) [${reportedBins.join(', ')}], this collection populates [${bins.join(', ')}]`,
  ].filter((line): line is string => line !== null)

  if (disagreements.length > 0) {
    throw new DataError(
      [
        `${labelsSource} is not the label collection ${reportSource} was scored against:`,
        `${disagreements.join('; ')}.`,
        'Every metric in the report was computed against a different label set, so the two tabs',
        'would contradict each other. Pass ?labels= the collection the run used, or re-run the',
        'benchmark against this one.',
      ].join(' '),
    )
  }

  return {
    agreed: [
      `${confirmed.length} confirmed event(s)`,
      `${withOptical.length} with an optical alert date`,
      bins.length ? `area bins ${bins.join(', ')}` : 'no event carries an area',
    ],
    limits: [
      'Counts only: the report records no identifier for the label collection it scored',
      `(labels_version ${report.labelsVersion} is the understory-labels package version, not a`,
      'fingerprint of these events), so a different collection with the same counts would pass.',
    ].join(' '),
  }
}

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((value) => b.includes(value))
}

const EVENT_CLASSES: DisturbanceClass[] = [
  'selective-logging',
  'access-road',
  'mining',
  'clearing',
  'controlled-experiment',
  'other',
]
const STATUSES: ConfirmationStatus[] = ['confirmed', 'rejected', 'candidate']

/**
 * The label schema versions ./types.ts is written against.
 *
 * `schema_version` is required on every label feature and is a `const` in
 * packages/understory-labels/schema/disturbance-event.schema.json — 0.1.0 is
 * the only version that has ever existed. A collection announcing a different
 * one may have renamed or re-semanticised the fields underneath, and mapping
 * whatever still matches would render new data under the old reading with
 * nothing on screen saying so. Bump this list in the same change that updates
 * ./types.ts to the new schema.
 */
export const SUPPORTED_LABEL_SCHEMA_VERSIONS = ['0.1.0']

export function parseLabels(json: unknown, source: string): DisturbanceEvent[] {
  const collection = asFeatureCollection(json, source)
  return collection.features.map((raw, i) => {
    const path = `features[${i}]`
    const feature = asObject(raw, source, path)
    // Property failures are reported at features[i].properties.<key> — the path
    // that exists in the file, so it can be pasted straight into a debugger.
    const props = `${path}.properties`
    const p = asObject(feature.properties, source, props)
    const schemaVersion = str(p, 'schema_version', source, props)
    if (!SUPPORTED_LABEL_SCHEMA_VERSIONS.includes(schemaVersion)) {
      throw new DataError(
        [
          `${source}: ${props}.schema_version is "${schemaVersion}", and this viewer reads`,
          `${SUPPORTED_LABEL_SCHEMA_VERSIONS.join(', ')}.`,
          'Its label types mirror that schema field for field; a newer collection may have',
          'renamed or re-semanticised fields, so reading it here would show new data under the',
          'old interpretation. Update apps/viewer/src/types.ts to the new schema first.',
        ].join(' '),
      )
    }
    const window = asObject(p.date_window, source, `${props}.date_window`)
    const eventClass = str(p, 'event_class', source, props)
    if (!(EVENT_CLASSES as string[]).includes(eventClass)) {
      throw new DataError(`${source}: ${props}.event_class is "${eventClass}", not in the schema`)
    }
    const status = str(p, 'status', source, props)
    if (!(STATUSES as string[]).includes(status)) {
      throw new DataError(`${source}: ${props}.status is "${status}", not in the schema`)
    }
    const precision = p.location_precision
    if (precision !== undefined && precision !== 'exact' && precision !== 'coarsened') {
      throw new DataError(`${source}: ${props}.location_precision is "${String(precision)}"`)
    }
    return {
      id: str(p, 'id', source, props),
      geometry: geometry(feature.geometry, source, `${path}.geometry`),
      dateWindow: {
        start: str(window, 'start', source, `${props}.date_window`),
        end: str(window, 'end', source, `${props}.date_window`),
      },
      eventClass: eventClass as DisturbanceClass,
      status: status as ConfirmationStatus,
      biome: str(p, 'biome', source, props),
      evidenceSource: str(p, 'evidence_source', source, props),
      areaHa: optionalNum(p.area_ha, source, `${props}.area_ha`),
      opticalAlertDate: optionalStr(p.optical_alert_date, source, `${props}.optical_alert_date`),
      notes: optionalStr(p.notes, source, `${props}.notes`),
      locationPrecision: (precision ?? 'exact') as LocationPrecision,
    }
  })
}

// --- aoi -------------------------------------------------------------------

export function parseAoi(json: unknown, source: string): Geometry {
  const obj = asObject(json, source, '')
  if (obj.type === 'FeatureCollection') {
    const collection = asFeatureCollection(json, source)
    const first = collection.features[0]
    if (!first) throw new DataError(`${source}: AOI FeatureCollection has no features`)
    return geometry(asObject(first, source, 'features[0]').geometry, source, 'features[0].geometry')
  }
  if (obj.type === 'Feature') {
    return geometry(obj.geometry, source, 'geometry')
  }
  return geometry(json, source, '')
}

// --- primitives ------------------------------------------------------------

type Json = Record<string, unknown>

function asObject(json: unknown, source: string, path: string): Json {
  if (typeof json !== 'object' || json === null || Array.isArray(json)) {
    throw new DataError(`${source}: ${path || '<root>'} must be an object, got ${typeName(json)}`)
  }
  return json as Json
}

function asFeatureCollection(json: unknown, source: string): FeatureCollection {
  const obj = asObject(json, source, '')
  if (obj.type !== 'FeatureCollection') {
    throw new DataError(`${source}: expected a GeoJSON FeatureCollection, got type "${obj.type}"`)
  }
  if (!Array.isArray(obj.features)) {
    throw new DataError(`${source}: FeatureCollection.features must be an array`)
  }
  return obj as unknown as FeatureCollection
}

function geometry(json: unknown, source: string, path: string): Geometry {
  const obj = asObject(json, source, path)
  if (typeof obj.type !== 'string') {
    throw new DataError(`${source}: ${path} has no geometry type`)
  }
  if (obj.type !== 'GeometryCollection' && !Array.isArray(obj.coordinates)) {
    throw new DataError(`${source}: ${path} has no coordinates`)
  }
  return obj as unknown as Geometry
}

function at(path: string | undefined, key: string): string {
  return path ? `${path}.${key}` : key
}

function str(obj: Json, key: string, source: string, path?: string): string {
  const value = obj[key]
  if (typeof value !== 'string') {
    throw new DataError(`${source}: ${at(path, key)} must be a string, got ${typeName(value)}`)
  }
  return value
}

function num(obj: Json, key: string, source: string, path?: string): number {
  const value = obj[key]
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new DataError(`${source}: ${at(path, key)} must be a number, got ${typeName(value)}`)
  }
  return value
}

function numOrNull(obj: Json, key: string, source: string, path?: string): number | null {
  const value = obj[key]
  if (value === null) return null
  if (value === undefined) {
    throw new DataError(`${source}: ${at(path, key)} is missing (write null when unmeasured)`)
  }
  return num(obj, key, source, path)
}

function bool(obj: Json, key: string, source: string, path?: string): boolean {
  const value = obj[key]
  if (typeof value !== 'boolean') {
    throw new DataError(`${source}: ${at(path, key)} must be a boolean, got ${typeName(value)}`)
  }
  return value
}

/**
 * An optional string field. Absent (or JSON null, which is how the Python side
 * writes an unset `optical_alert_date`) is undefined; present but of the wrong
 * type is a hard error naming the path, not a silent drop — a discarded
 * `optical_alert_date` would read on screen as "no optical alert date" while
 * the report still counts that label in n_events_with_optical_record.
 */
function optionalStr(value: unknown, source: string, path: string): string | undefined {
  if (value === undefined || value === null) return undefined
  if (typeof value !== 'string') {
    throw new DataError(`${source}: ${path} must be a string when present, got ${typeName(value)}`)
  }
  return value
}

function optionalNum(value: unknown, source: string, path: string): number | undefined {
  if (value === undefined || value === null) return undefined
  if (typeof value !== 'number' || Number.isNaN(value)) {
    throw new DataError(`${source}: ${path} must be a number when present, got ${typeName(value)}`)
  }
  return value
}

function typeName(value: unknown): string {
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  return typeof value
}

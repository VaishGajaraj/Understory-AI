import { describe, expect, test } from 'bun:test'

import {
  DEFAULT_SOURCES,
  DataError,
  crossCheckLabels,
  loadBenchmark,
  parseAlerts,
  parseAoi,
  parseLabels,
  parseReport,
  siblingPath,
  sourcesFromQuery,
} from './data'

/**
 * Shaped after a real `make toy-bench` run (benchmarks/toy/reports/toy.json):
 * same field names, same nesting, geometry trimmed to four corners.
 */
const TOY_GEOMETRY = {
  type: 'Polygon',
  coordinates: [
    [
      [-54.9904, -7.0098],
      [-54.9804, -7.0098],
      [-54.9804, -6.9998],
      [-54.9904, -6.9998],
      [-54.9904, -7.0098],
    ],
  ],
}

function toyReport(): Record<string, unknown> {
  return {
    benchmark: 'toy',
    detector: 'v0-filters',
    detector_version: '0.1.0',
    labels_version: '0.1.0',
    methodology_version: '0.1.0',
    tolerances: {
      max_centroid_distance_m: 500.0,
      min_spatial_iou: 0.0,
      temporal_window_days: 36,
    },
    n_events: 1,
    n_detections: 1,
    true_positives: 1,
    false_positives: 0,
    false_negatives: 0,
    event_precision: 1.0,
    event_recall: 1.0,
    f1: 1.0,
    median_detection_latency_days: 22.0,
    median_lead_over_optical_days: 25.0,
    n_events_with_optical_record: 1,
    recall_by_area_ha: { '20+': 1.0 },
    calibration: {
      bins: { '0.8-1.0': { mean_score: 0.875, confirm_rate: 1.0, n: 1 } },
      expected_calibration_error: 0.125,
    },
    kill_criteria: {
      criteria: [
        {
          name: 'precision',
          threshold: '>= 70%',
          observed: '100% (1/1)',
          status: 'PASS',
          note: 'recall 100% synthetic data — scaffolding, not a claim',
        },
        {
          name: 'min-detectable-size',
          threshold: 'events <= 2 ha detectable',
          observed: 'no labeled events at or below the threshold size',
          status: 'INSUFFICIENT_DATA',
          note: 'needs controlled-disturbance ground truth (eastern-woodland benchmark)',
        },
      ],
      synthetic: true,
    },
    detections: [
      {
        id: 'v0-filters-toy-001',
        geometry: TOY_GEOMETRY,
        first_seen: '2026-02-23T00:00:00',
        last_seen: '2026-03-07T00:00:00',
        score: 0.875,
        persistence_passes: 3,
        area_ha: 24.7,
      },
    ],
  }
}

function toyAlerts(): Record<string, unknown> {
  return {
    type: 'FeatureCollection',
    properties: {
      benchmark: 'toy',
      detector: 'v0-filters 0.1.0',
      methodology_version: '0.1.0',
    },
    features: [
      {
        type: 'Feature',
        geometry: TOY_GEOMETRY,
        properties: {
          id: 'v0-filters-toy-001',
          score: 0.875,
          first_seen: '2026-02-23T00:00:00',
          last_seen: '2026-03-07T00:00:00',
          persistence_passes: 3,
          area_ha: 24.7,
        },
      },
    ],
  }
}

function toyLabels(): Record<string, unknown> {
  return {
    type: 'FeatureCollection',
    description: 'Synthetic fixture events for the toy benchmark and CI.',
    features: [
      {
        type: 'Feature',
        geometry: TOY_GEOMETRY,
        properties: {
          id: 'toy-road-001',
          schema_version: '0.1.0',
          date_window: { start: '2026-02-01', end: '2026-02-13' },
          event_class: 'access-road',
          status: 'confirmed',
          biome: 'toy',
          evidence_source: 'synthetic fixture — generated, not observed',
          area_ha: 24.0,
          optical_alert_date: '2026-03-20',
          notes: '~2 km diagonal linear feature injected into the toy coherence stack',
        },
      },
    ],
  }
}

function fetcherFor(files: Record<string, unknown>): (url: string) => Promise<Response> {
  return async (url: string) => {
    const body = files[url]
    if (body === undefined) return new Response('not found', { status: 404 })
    return new Response(JSON.stringify(body), {
      headers: {
        'content-type': 'application/json',
        'last-modified': 'Tue, 21 Jul 2026 01:12:00 GMT',
      },
    })
  }
}

describe('parseReport', () => {
  test('maps the whole report to camelCase', () => {
    const report = parseReport(toyReport(), 'toy.json')
    expect(report.benchmark).toBe('toy')
    expect(report.detectorVersion).toBe('0.1.0')
    expect(report.tolerances).toEqual({
      maxCentroidDistanceM: 500,
      minSpatialIou: 0,
      temporalWindowDays: 36,
    })
    expect(report.truePositives).toBe(1)
    expect(report.medianLeadOverOpticalDays).toBe(25)
    expect(report.nEventsWithOpticalRecord).toBe(1)
    expect(report.recallByAreaHa).toEqual([{ bin: '20+', recall: 1 }])
    expect(report.calibration.expectedCalibrationError).toBe(0.125)
    expect(report.calibration.bins).toEqual([
      { bin: '0.8-1.0', meanScore: 0.875, confirmRate: 1, n: 1 },
    ])
    expect(report.detections[0]?.persistencePasses).toBe(3)
    expect(report.detections[0]?.areaHa).toBe(24.7)
  })

  test('recomputes the verdict the same way Python does', () => {
    const alive = parseReport(toyReport(), 'toy.json')
    expect(alive.killCriteria.alive).toBe(true)
    expect(alive.killCriteria.synthetic).toBe(true)

    const raw = toyReport()
    const killed = structuredClone(raw) as Record<string, Record<string, unknown[]>>
    ;(killed.kill_criteria?.criteria?.[0] as Record<string, unknown>).status = 'FAIL'
    expect(parseReport(killed, 'toy.json').killCriteria.alive).toBe(false)
  })

  test('linearity and coherence series stay absent when the pipeline omits them', () => {
    const report = parseReport(toyReport(), 'toy.json')
    expect(report.detections[0]?.linearity).toBeUndefined()
    expect(report.detections[0]?.coherenceSeries).toBeUndefined()
  })

  test('reads linearity and a coherence series when a detector does emit them', () => {
    const raw = toyReport()
    const detections = raw.detections as Record<string, unknown>[]
    const first = detections[0] as Record<string, unknown>
    first.linearity = 0.78
    first.coherence_series = [
      { date: '2026-01-08', coherence: 0.63 },
      { date: '2026-01-20', coherence: 0.31 },
    ]
    const report = parseReport(raw, 'toy.json')
    expect(report.detections[0]?.linearity).toBe(0.78)
    expect(report.detections[0]?.coherenceSeries).toHaveLength(2)
  })

  test('a missing required field is a loud failure, not a default', () => {
    const raw = toyReport()
    // biome-ignore lint/performance/noDelete: exercising a genuinely absent key
    delete raw.event_precision
    expect(() => parseReport(raw, 'reports/toy.json')).toThrow(DataError)
    expect(() => parseReport(raw, 'reports/toy.json')).toThrow(
      /reports\/toy\.json: event_precision/,
    )
  })

  test('an unmeasured metric must be null, not missing', () => {
    const raw = toyReport()
    raw.median_lead_over_optical_days = null
    expect(parseReport(raw, 'toy.json').medianLeadOverOpticalDays).toBeNull()

    // biome-ignore lint/performance/noDelete: exercising a genuinely absent key
    delete raw.median_lead_over_optical_days
    expect(() => parseReport(raw, 'toy.json')).toThrow(/write null when unmeasured/)
  })

  test('an unknown kill-criterion status is rejected', () => {
    const raw = toyReport()
    const criteria = (raw.kill_criteria as { criteria: Record<string, unknown>[] }).criteria
    const first = criteria[0]
    if (first) first.status = 'PROBABLY_FINE'
    expect(() => parseReport(raw, 'toy.json')).toThrow(/status is "PROBABLY_FINE"/)
  })

  test('a report without detections is rejected', () => {
    const raw = toyReport()
    // biome-ignore lint/performance/noDelete: exercising a genuinely absent key
    delete raw.detections
    expect(() => parseReport(raw, 'toy.json')).toThrow(/"detections" must be an array/)
  })
})

describe('parseAlerts', () => {
  test('keeps the on-disk property names', () => {
    const { features, properties } = parseAlerts(toyAlerts(), 'toy-alerts.geojson')
    expect(properties.detector).toBe('v0-filters 0.1.0')
    expect(features[0]?.properties.first_seen).toBe('2026-02-23T00:00:00')
    expect(features[0]?.properties.area_ha).toBe(24.7)
  })

  test('a non-collection is rejected', () => {
    expect(() => parseAlerts({ type: 'Feature' }, 'toy-alerts.geojson')).toThrow(
      /expected a GeoJSON FeatureCollection/,
    )
  })

  test('a property failure names a path that exists in the file', () => {
    const raw = toyAlerts() as { features: { properties: Record<string, unknown> }[] }
    // biome-ignore lint/performance/noDelete: exercising a genuinely absent key
    delete raw.features[0]?.properties.score
    expect(() => parseAlerts(raw, 'toy-alerts.geojson')).toThrow(
      /toy-alerts\.geojson: features\[0\]\.properties\.score must be a number/,
    )
  })
})

describe('crossCheckLabels', () => {
  const report = parseReport(toyReport(), 'toy.json')
  const labels = parseLabels(toyLabels(), 'labels.geojson')

  test('the collection the run was scored against passes, and says what it proved', () => {
    const check = crossCheckLabels(report, labels, 'toy.json', 'labels.geojson')
    expect(check.agreed).toEqual([
      '1 confirmed event(s)',
      '1 with an optical alert date',
      'area bins 20+',
    ])
    expect(check.limits).toContain('a different collection with the same counts would pass')
  })

  test('a collection with a different confirmed-event count is refused', () => {
    const extra = parseLabels(
      {
        ...toyLabels(),
        features: [
          ...(toyLabels().features as unknown[]),
          {
            type: 'Feature',
            geometry: TOY_GEOMETRY,
            properties: {
              id: 'toy-road-002',
              schema_version: '0.1.0',
              date_window: { start: '2026-02-01', end: '2026-02-13' },
              event_class: 'clearing',
              status: 'confirmed',
              biome: 'toy',
              evidence_source: 'synthetic fixture',
              area_ha: 3.0,
            },
          },
        ],
      },
      'other-labels.geojson',
    )
    expect(() => crossCheckLabels(report, extra, 'toy.json', 'other-labels.geojson')).toThrow(
      DataError,
    )
    expect(() => crossCheckLabels(report, extra, 'toy.json', 'other-labels.geojson')).toThrow(
      /the report scored 1 confirmed event\(s\), this collection has 2/,
    )
    // The extra event lands in the 2-5 bin, which the report has no recall for.
    expect(() => crossCheckLabels(report, extra, 'toy.json', 'other-labels.geojson')).toThrow(
      /this collection populates \[2-5, 20\+\]/,
    )
  })

  test('a collection with a different optical-record count is refused', () => {
    const noOptical = parseLabels(
      (() => {
        const raw = toyLabels() as { features: { properties: Record<string, unknown> }[] }
        // biome-ignore lint/performance/noDelete: exercising a genuinely absent key
        delete raw.features[0]?.properties.optical_alert_date
        return raw
      })(),
      'labels.geojson',
    )
    expect(() => crossCheckLabels(report, noOptical, 'toy.json', 'labels.geojson')).toThrow(
      /the report scored 1 confirmed event\(s\) with an optical alert date, this collection has 0/,
    )
  })

  test('rejected labels are not counted — only confirmed ones were scored', () => {
    const withRejected = [
      ...labels,
      { ...labels[0], id: 'toy-rain-001', status: 'rejected' as const, areaHa: undefined },
    ].filter((label): label is (typeof labels)[number] => label !== undefined)
    expect(() => crossCheckLabels(report, withRejected, 'toy.json', 'labels.geojson')).not.toThrow()
  })
})

describe('parseLabels', () => {
  /** The toy collection with the first feature's properties overridden. */
  function labelProperties(over: Record<string, unknown>): Record<string, unknown> {
    const raw = toyLabels() as { features: { properties: Record<string, unknown> }[] }
    const first = raw.features[0]
    if (first) Object.assign(first.properties, over)
    return raw
  }

  test('maps every field of the label schema', () => {
    const labels = parseLabels(toyLabels(), 'toy-fixtures.geojson')
    expect(labels).toHaveLength(1)
    expect(labels[0]?.id).toBe('toy-road-001')
    expect(labels[0]?.eventClass).toBe('access-road')
    expect(labels[0]?.dateWindow).toEqual({ start: '2026-02-01', end: '2026-02-13' })
    expect(labels[0]?.opticalAlertDate).toBe('2026-03-20')
    expect(labels[0]?.locationPrecision).toBe('exact')
  })

  test('an off-schema event class is rejected', () => {
    const raw = toyLabels() as { features: { properties: Record<string, unknown> }[] }
    const first = raw.features[0]
    if (first) first.properties.event_class = 'deforestation'
    expect(() => parseLabels(raw, 'toy-fixtures.geojson')).toThrow(/not in the schema/)
  })

  test('a label with no geometry is rejected', () => {
    const raw = toyLabels() as { features: Record<string, unknown>[] }
    const first = raw.features[0]
    if (first) first.geometry = { type: 'Polygon' }
    expect(() => parseLabels(raw, 'toy-fixtures.geojson')).toThrow(/has no coordinates/)
  })

  test('a schema version the viewer does not mirror is refused, not mapped', () => {
    expect(() =>
      parseLabels(labelProperties({ schema_version: '0.2.0' }), 'labels.geojson'),
    ).toThrow(/schema_version is "0\.2\.0", and this viewer reads 0\.1\.0/)
    expect(() =>
      parseLabels(labelProperties({ schema_version: '0.2.0' }), 'labels.geojson'),
    ).toThrow(/types\.ts/)
  })

  test('a label with no schema_version is rejected — the schema requires one', () => {
    const raw = toyLabels() as { features: { properties: Record<string, unknown> }[] }
    // biome-ignore lint/performance/noDelete: exercising a genuinely absent key
    delete raw.features[0]?.properties.schema_version
    expect(() => parseLabels(raw, 'labels.geojson')).toThrow(
      /features\[0\]\.properties\.schema_version must be a string/,
    )
  })

  test('an optional field of the wrong type is refused, not silently dropped', () => {
    // Dropping it would print "no optical alert date" in the inspector while
    // the report still counts the label in n_events_with_optical_record.
    expect(() =>
      parseLabels(labelProperties({ optical_alert_date: 20260320 }), 'l.geojson'),
    ).toThrow(
      /features\[0\]\.properties\.optical_alert_date must be a string when present, got number/,
    )
    expect(() => parseLabels(labelProperties({ notes: ['a', 'b'] }), 'l.geojson')).toThrow(
      /features\[0\]\.properties\.notes must be a string when present, got array/,
    )
  })

  test('an unset optional field stays absent whether it is null or missing', () => {
    expect(
      parseLabels(labelProperties({ optical_alert_date: null }), 'l.geojson')[0]?.opticalAlertDate,
    ).toBeUndefined()
    expect(parseLabels(toyLabels(), 'l.geojson')[0]?.notes).toBe(
      '~2 km diagonal linear feature injected into the toy coherence stack',
    )
  })

  test('a property failure names a path that exists in the file', () => {
    const raw = toyLabels() as { features: { properties: Record<string, unknown> }[] }
    // biome-ignore lint/performance/noDelete: exercising a genuinely absent key
    delete raw.features[0]?.properties.biome
    expect(() => parseLabels(raw, 'labels.geojson')).toThrow(
      /labels\.geojson: features\[0\]\.properties\.biome must be a string/,
    )
  })
})

describe('parseAoi', () => {
  test('accepts a bare geometry, a Feature, or a FeatureCollection', () => {
    expect(parseAoi(TOY_GEOMETRY, 'aoi.json').type).toBe('Polygon')
    expect(parseAoi({ type: 'Feature', geometry: TOY_GEOMETRY }, 'aoi.json').type).toBe('Polygon')
    expect(
      parseAoi(
        { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: TOY_GEOMETRY }] },
        'aoi.json',
      ).type,
    ).toBe('Polygon')
  })

  test('an empty collection is rejected', () => {
    expect(() => parseAoi({ type: 'FeatureCollection', features: [] }, 'aoi.json')).toThrow(
      /no features/,
    )
  })
})

describe('sources', () => {
  test('defaults to the toy benchmark', () => {
    expect(sourcesFromQuery('')).toMatchObject({
      report: DEFAULT_SOURCES.report,
      labels: DEFAULT_SOURCES.labels,
    })
  })

  test('query parameters override every source', () => {
    const sources = sourcesFromQuery(
      '?report=/r/amazon.json&alerts=/r/a.geojson&labels=/l.geojson&aoi=/aoi.json',
    )
    expect(sources).toEqual({
      report: '/r/amazon.json',
      alerts: '/r/a.geojson',
      labels: '/l.geojson',
      aoi: '/aoi.json',
    })
  })

  test('alerts default to the sibling path the pipeline writes', () => {
    expect(siblingPath('/benchmarks/toy/reports/toy.json', 'toy-alerts.geojson')).toBe(
      '/benchmarks/toy/reports/toy-alerts.geojson',
    )
  })
})

describe('loadBenchmark', () => {
  const files = {
    '/reports/toy.json': toyReport(),
    '/reports/toy-alerts.geojson': toyAlerts(),
    '/labels.geojson': toyLabels(),
  }

  test('loads report, sibling alerts and labels', async () => {
    const loaded = await loadBenchmark(
      { report: '/reports/toy.json', labels: '/labels.geojson' },
      fetcherFor(files),
    )
    expect(loaded.report.benchmark).toBe('toy')
    expect(loaded.alerts).toHaveLength(1)
    expect(loaded.labels).toHaveLength(1)
    expect(loaded.aoi).toBeNull()
    expect(loaded.resolved.alerts).toBe('/reports/toy-alerts.geojson')
    expect(loaded.reportLastModified).toBe('Tue, 21 Jul 2026 01:12:00 GMT')
    expect(loaded.labelCheck.agreed).toContain('1 confirmed event(s)')
  })

  test('a label collection the run was never scored against is refused', async () => {
    const wrong = { ...files }
    const labels = toyLabels() as { features: { properties: Record<string, unknown> }[] }
    const first = labels.features[0]
    if (first) first.properties.status = 'candidate'
    wrong['/labels.geojson'] = labels
    const promise = loadBenchmark(
      { report: '/reports/toy.json', labels: '/labels.geojson' },
      fetcherFor(wrong),
    )
    await expect(promise).rejects.toThrow(
      /\/labels\.geojson is not the label collection \/reports\/toy\.json was scored against/,
    )
    await expect(promise).rejects.toThrow(/Pass \?labels= the collection the run used/)
  })

  test('a missing file names the file and the fix', async () => {
    const promise = loadBenchmark(
      { report: '/reports/missing.json', labels: '/labels.geojson' },
      fetcherFor(files),
    )
    await expect(promise).rejects.toThrow(/\/reports\/missing\.json: HTTP 404/)
    await expect(promise).rejects.toThrow(/make toy-bench/)
  })

  test('report and alerts from different runs are refused', async () => {
    const mismatched = { ...files }
    const alerts = toyAlerts() as { features: { properties: Record<string, unknown> }[] }
    const first = alerts.features[0]
    if (first) first.properties.id = 'v0-filters-toy-999'
    mismatched['/reports/toy-alerts.geojson'] = alerts
    await expect(
      loadBenchmark(
        { report: '/reports/toy.json', labels: '/labels.geojson' },
        fetcherFor(mismatched),
      ),
    ).rejects.toThrow(/describe different runs/)
  })
})

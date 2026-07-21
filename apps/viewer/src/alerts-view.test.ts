import { describe, expect, test } from 'bun:test'

import { renderSparkline } from './alerts-view'
import type { CoherenceSample } from './types'

/** A real drop: the case that used to push the fabricated −3σ line off-canvas. */
const SERIES: CoherenceSample[] = [
  { date: '2026-01-08', coherence: 0.62 },
  { date: '2026-01-20', coherence: 0.64 },
  { date: '2026-02-01', coherence: 0.61 },
  { date: '2026-02-13', coherence: 0.22 },
  { date: '2026-02-25', coherence: 0.19 },
]

describe('renderSparkline', () => {
  test('says so rather than drawing anything when no series was emitted', () => {
    expect(renderSparkline(undefined).value).toContain('not emitted by this detector version')
    expect(renderSparkline(undefined).value).not.toContain('<svg')
    expect(renderSparkline([{ date: '2026-01-08', coherence: 0.6 }]).value).not.toContain('<svg')
  })

  test('draws the series and only the series', () => {
    const svg = renderSparkline(SERIES).value
    expect(svg).toContain('<polyline')
    // The detector's baseline is a rolling median + scaled MAD over a trailing
    // window with anomaly_sigma from config (understory_detect.baseline). None
    // of that is in the report, so nothing here may stand in for it.
    expect(svg).not.toContain('<line')
    expect(svg).not.toContain('<rect')
    expect(svg).not.toContain('σ')
    expect(svg).not.toContain('threshold')
    expect(svg).not.toContain('baseline ±')
  })

  test('captions only what the data says', () => {
    const svg = renderSparkline(SERIES).value
    expect(svg).toContain('0.19–0.64')
    expect(svg).toContain('no baseline envelope in the report')
    expect(svg).toContain('2026-01-08')
    expect(svg).toContain('2026-02-25')
  })

  test('every plotted point is inside the viewBox', () => {
    const svg = renderSparkline(SERIES).value
    const points = /points="([^"]+)"/.exec(svg)?.[1]
    expect(points).toBeDefined()
    const coordinates = (points ?? '').split(' ').map((pair) => pair.split(',').map(Number))
    expect(coordinates).toHaveLength(SERIES.length)
    for (const [x, y] of coordinates) {
      expect(x).toBeGreaterThanOrEqual(0)
      expect(x).toBeLessThanOrEqual(240)
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y).toBeLessThanOrEqual(84)
    }
  })

  test('a flat series still plots inside the viewBox', () => {
    const flat = SERIES.map((sample) => ({ ...sample, coherence: 0.5 }))
    const points = /points="([^"]+)"/.exec(renderSparkline(flat).value)?.[1] ?? ''
    for (const pair of points.split(' ')) {
      const y = Number(pair.split(',')[1])
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y).toBeLessThanOrEqual(84)
    }
  })
})

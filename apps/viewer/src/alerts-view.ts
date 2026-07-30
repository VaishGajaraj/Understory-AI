/**
 * The alerts view: triage queue, map furniture, inspector.
 *
 * Every number here comes from the loaded report, the alert GeoJSON or the
 * label library. Where the design showed a field the pipeline does not emit,
 * the panel says so instead of filling in a plausible value.
 */

import { type Raw, fixed, html, signedDays } from './dom'
import {
  type FilterCounts,
  QUEUE_FILTERS,
  type QueueFilter,
  type QueueSort,
  type TriageRow,
  centroid,
  isoDate,
} from './triage'
import type { CoherenceSample, MatchingTolerances } from './types'

export interface QueueViewModel {
  queue: TriageRow[]
  counts: FilterCounts
  filter: QueueFilter
  sort: QueueSort
  selectedId: string | null
}

export function renderQueue(model: QueueViewModel): Raw {
  return html`
    <div class="queue-head">
      <div class="queue-head-row">
        <div class="section-label">Triage queue</div>
        <div class="queue-head-right">
          <span class="queue-count">${model.queue.length} shown</span>
          <button class="filter-chip" data-cycle-sort title="Sort the queue" type="button">
            by ${model.sort === 'score' ? 'score' : 'recency'}
          </button>
        </div>
      </div>
      <div class="filters">
        ${QUEUE_FILTERS.map(
          (filter) => html`
            <button
              class="filter-chip ${filter === model.filter ? 'is-active' : ''}"
              data-filter="${filter}"
            >
              ${filter} ${model.counts[filter]}
            </button>
          `,
        )}
      </div>
    </div>
    <div class="queue-list">${model.queue.length ? model.queue.map(queueRow(model.selectedId)) : emptyQueue()}</div>
    <div class="queue-note">
      Scores are calibrated: of alerts at ~0.8, ~80% should confirm. Overconfidence is a defect.
    </div>
  `
}

function emptyQueue(): Raw {
  return html`<div class="queue-empty">No detections in this filter.</div>`
}

function queueRow(selectedId: string | null) {
  return (row: TriageRow): Raw => {
    const d = row.detection
    return html`
      <button
        class="queue-row ${d.id === selectedId ? 'is-selected' : ''}"
        data-select="${d.id}"
        type="button"
      >
        <span class="row-top">
          <span class="status-dot ${row.status}"></span>
          <span class="row-id">${d.id}</span>
          <span class="spacer"></span>
          <span class="row-score ${d.score >= 0.7 ? 'is-high' : ''}">${fixed(d.score, 2)}</span>
        </span>
        <span class="row-meta">
          <span>${d.areaHa === undefined ? 'area n/a' : `${fixed(d.areaHa, 1)} ha`}</span>
          <span>${d.persistencePasses} passes</span>
          <span>first ${isoDate(d.firstSeen).slice(5)}</span>
        </span>
        <span class="row-tags">
          <span class="pill ${row.status}">${row.status}${row.overridden ? ' ·' : ''}</span>
          ${row.match ? html`<span class="match-tag">⌖ ${row.match.label.id}</span>` : ''}
        </span>
      </button>
    `
  }
}

export function renderLegend(labelsVisible: boolean, labelCount: number): Raw {
  return html`
    <div class="legend-title">Layers</div>
    <div class="legend-items">
      <div class="legend-item">
        <span class="legend-swatch detection"></span>Detection (coherence anomaly)
      </div>
      <button class="legend-item ${labelsVisible ? '' : 'is-off'}" data-toggle-labels type="button">
        <span class="legend-swatch label"></span>Ground-truth label · ${labelCount} ·
        ${labelsVisible ? 'on' : 'off'}
      </button>
    </div>
  `
}

export function renderMapCaption(benchmark: string, aoiLoaded: boolean): Raw {
  return html`AOI ${benchmark}${aoiLoaded ? '' : ' — no AOI outline supplied (?aoi=), view fitted to the data'}`
}

// --- inspector -------------------------------------------------------------

export function renderInspector(row: TriageRow | null, tolerances: MatchingTolerances): Raw {
  if (!row) {
    return html`<div class="inspector-empty">Select a detection from the queue or map.</div>`
  }
  const d = row.detection
  const [lon, lat] = centroid(d.geometry)
  return html`
    <div class="inspector-head">
      <div class="inspector-title">
        <div class="inspector-id">${d.id}</div>
        <span class="pill ${row.status}">${row.status}</span>
      </div>
      <div class="inspector-coords">
        ${fixed(lat, 3)}°, ${fixed(lon, 3)}° · first seen ${isoDate(d.firstSeen)} · last
        ${isoDate(d.lastSeen)}
      </div>
    </div>
    <div class="tile-grid">
      <div class="tile">
        <div class="tile-label">Score</div>
        <div class="tile-value ${d.score >= 0.7 ? 'is-high' : ''}">${fixed(d.score, 2)}</div>
      </div>
      <div class="tile">
        <div class="tile-label">Area</div>
        <div class="tile-value">
          ${d.areaHa === undefined ? 'n/a' : fixed(d.areaHa, 1)}<span class="tile-unit"> ha</span>
        </div>
      </div>
      <div class="tile">
        <div class="tile-label">Persistence</div>
        <div class="tile-value">
          ${d.persistencePasses}<span class="tile-unit"> passes</span>
        </div>
      </div>
      ${
        d.linearity === undefined
          ? ''
          : html`
            <div class="tile">
              <div class="tile-label">Linearity</div>
              <div class="tile-value">${fixed(d.linearity, 2)}</div>
              <div class="tile-hint">${d.linearity >= 0.6 ? 'road / trail shaped' : 'compact patch'}</div>
            </div>
          `
      }
    </div>
    <div class="panel">
      <div class="panel-label">Coherence · consecutive-pass pairs</div>
      ${renderSparkline(d.coherenceSeries)}
    </div>
    <div class="panel">
      <div class="panel-label">Ground truth</div>
      ${renderGroundTruth(row, tolerances)}
    </div>
    <div class="panel">
      <div class="panel-label">Triage</div>
      <div class="triage-actions">
        <button class="triage-btn confirm ${row.status === 'confirmed' ? 'is-active' : ''}" data-triage="confirmed" type="button">
          ✓ Confirm
        </button>
        <button class="triage-btn reject ${row.status === 'rejected' ? 'is-active' : ''}" data-triage="rejected" type="button">
          ✕ Reject
        </button>
      </div>
      <div class="triage-note">
        Rejections feed the label library as verified natural decorrelation — exactly what the
        detector must learn not to fire on. Decisions here are local to this browser session;
        promoting one into the library is a reviewed pull request against
        packages/understory-labels.
      </div>
    </div>
  `
}

function renderGroundTruth(row: TriageRow, tolerances: MatchingTolerances): Raw {
  const match = row.match
  if (!match) {
    return html`
      <div class="placeholder">
        No matching label within ${tolerances.maxCentroidDistanceM} m / ±${tolerances.temporalWindowDays} d.
        Unverified — confirm only with independent evidence (optical, field, enforcement record).
      </div>
    `
  }
  const label = match.label
  return html`
    <div class="match-card">
      <div class="match-head">
        ⌖ ${label.id}<span class="match-class">${label.eventClass} · ${label.status}</span>
      </div>
      <div class="match-grid">
        <span class="match-key">evidence</span><span>${label.evidenceSource}</span>
        <span class="match-key">event window</span>
        <span class="match-mono">${label.dateWindow.start} → ${label.dateWindow.end}</span>
        <span class="match-key">centroid Δ</span>
        <span class="match-mono">${Math.round(match.distanceM)} m</span>
        <span class="match-key">latency</span>
        <span class="match-mono">${signedDays(match.latencyDays)} d after window start</span>
        <span class="match-key">lead vs optical</span>
        ${
          match.leadOverOpticalDays === null
            ? html`<span class="match-mono">no optical alert date on this label</span>`
            : html`<span class="match-mono match-lead">${signedDays(match.leadOverOpticalDays)} d</span>`
        }
      </div>
    </div>
  `
}

const SPARK_W = 240
const SPARK_H = 84

/**
 * The prototype drew this curve from a sine wave. No detector emits a
 * per-detection coherence series, so this renders only when the data carries
 * one — and says plainly when it does not.
 *
 * The series and nothing else. An earlier version drew a "−3σ threshold" line
 * and a "baseline ±σ" band derived from the plotted points themselves: the
 * detector's baseline is a rolling median and scaled MAD over a trailing
 * window (understory_detect.baseline) with `anomaly_sigma` from the benchmark
 * config, so those two overlays described a decision rule that never existed —
 * and the line fell outside the viewBox as soon as the series held a real drop.
 * If a report ever carries the baseline envelope next to the series, draw it
 * from those numbers; never from these.
 */
export function renderSparkline(series: CoherenceSample[] | undefined): Raw {
  if (!series || series.length < 2) {
    return html`
      <div class="placeholder">
        Per-detection coherence series not emitted by this detector version. The report carries
        first/last anomalous pair dates and a score, not the underlying curve.
      </div>
    `
  }
  const values = series.map((s) => s.coherence)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const y = (value: number) => 74 - ((value - min) / span) * 62
  const x = (i: number) => 10 + (i * (SPARK_W - 20)) / (series.length - 1)
  const points = series.map((s, i) => `${x(i).toFixed(1)},${y(s.coherence).toFixed(1)}`).join(' ')
  const first = series[0]
  const last = series[series.length - 1]
  return html`
    <svg viewBox="0 0 ${SPARK_W} ${SPARK_H}" style="width:100%;display:block">
      <polyline points="${points}" fill="none" stroke="#6fc48d" stroke-width="1.8" stroke-linejoin="round"></polyline>
    </svg>
    <div style="display:flex;justify-content:space-between;font-family:var(--mono);font-size:9.5px;color:var(--dimmer);margin-top:4px">
      <span>${first ? isoDate(first.date) : ''}</span>
      <span>γ ${fixed(min, 2)}–${fixed(max, 2)} · no baseline envelope in the report</span>
      <span>${last ? isoDate(last.date) : ''}</span>
    </div>
  `
}

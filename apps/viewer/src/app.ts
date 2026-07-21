/**
 * The shell: header tabs, footer, export, and the state that the two views
 * render from. Small enough that a re-render on every state change is the
 * right answer — no framework, no virtual DOM.
 */

import { renderInspector, renderLegend, renderMapCaption, renderQueue } from './alerts-view'
import { DataError, type LoadedBenchmark, loadBenchmark, sourcesFromQuery } from './data'
import { type Raw, html, setHtml } from './dom'
import { downloadAlerts } from './export'
import { type DetectionMap, createDetectionMap } from './map'
import { renderReport } from './report-view'
import {
  type QueueFilter,
  type QueueSort,
  type TriageOverrides,
  type TriageRow,
  type TriageStatus,
  buildRows,
  detectionWindow,
  filterCounts,
  queueFor,
} from './triage'

type View = 'alerts' | 'report'

interface State {
  view: View
  selectedId: string | null
  filter: QueueFilter
  sort: QueueSort
  labelsVisible: boolean
  overrides: TriageOverrides
}

export async function bootstrap(root: HTMLElement): Promise<void> {
  const sources = sourcesFromQuery(window.location.search)
  let loaded: LoadedBenchmark
  try {
    loaded = await loadBenchmark(sources)
  } catch (error) {
    setHtml(root, fatal(error))
    return
  }
  mount(root, loaded)
}

function fatal(error: unknown): Raw {
  const message = error instanceof Error ? error.message : String(error)
  return html`
    <div class="fatal">
      <div class="fatal-title">CANNOT LOAD BENCHMARK OUTPUT</div>
      <div class="fatal-message">${message}</div>
      <div class="fatal-hint">
        The viewer only renders files the pipeline wrote. Produce them with
        <code>make toy-bench</code> (writes <code>benchmarks/toy/reports/toy.json</code> and
        <code>toy-alerts.geojson</code>), or point the viewer elsewhere with
        <code>?report=…&amp;labels=…</code>.
        ${error instanceof DataError ? '' : 'This was not a data error — see the console.'}
      </div>
    </div>
  `
}

function mount(root: HTMLElement, loaded: LoadedBenchmark): void {
  const { report } = loaded
  const state: State = {
    view: 'alerts',
    selectedId: null,
    filter: 'all',
    sort: 'score',
    labelsVisible: true,
    overrides: {},
  }

  setHtml(root, shell(loaded))
  const queueEl = required(root, '[data-queue]')
  const inspectorEl = required(root, '[data-inspector]')
  const legendEl = required(root, '[data-legend]')
  const captionEl = required(root, '[data-caption]')
  const reportEl = required(root, '[data-report-view]')
  const alertsEl = required(root, '[data-alerts-view]')
  const mapEl = required(root, '[data-map]')

  const rowsFor = (overrides: TriageOverrides): TriageRow[] =>
    buildRows(report.detections, loaded.labels, report.tolerances, overrides)

  let rows = rowsFor(state.overrides)
  state.selectedId = queueFor(rows, state.filter, state.sort)[0]?.detection.id ?? null

  let map: DetectionMap | null = null

  function render(): void {
    rows = rowsFor(state.overrides)
    const queue = queueFor(rows, state.filter, state.sort)
    setHtml(
      queueEl,
      renderQueue({
        queue,
        counts: filterCounts(rows),
        filter: state.filter,
        sort: state.sort,
        selectedId: state.selectedId,
      }),
    )
    const selected = rows.find((row) => row.detection.id === state.selectedId) ?? null
    setHtml(inspectorEl, renderInspector(selected, report.tolerances))
    setHtml(legendEl, renderLegend(state.labelsVisible, loaded.labels.length))
    setHtml(captionEl, renderMapCaption(report.benchmark, loaded.aoi !== null))
    setHtml(reportEl, renderReport(loaded))

    alertsEl.style.display = state.view === 'alerts' ? 'flex' : 'none'
    reportEl.style.display = state.view === 'report' ? 'block' : 'none'
    for (const tab of root.querySelectorAll('[data-view]')) {
      tab.classList.toggle('is-active', tab.getAttribute('data-view') === state.view)
    }

    map?.update({
      rows,
      labels: loaded.labels,
      selectedId: state.selectedId,
      labelsVisible: state.labelsVisible,
    })
  }

  root.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) return

    const view = target.closest('[data-view]')?.getAttribute('data-view')
    if (view === 'alerts' || view === 'report') {
      state.view = view
      render()
      // MapLibre sizes itself to a hidden pane as 0x0; tell it to look again.
      if (view === 'alerts') map?.resize()
      return
    }

    const selectId = target.closest('[data-select]')?.getAttribute('data-select')
    if (selectId) {
      state.selectedId = selectId
      render()
      return
    }

    const filter = target.closest('[data-filter]')?.getAttribute('data-filter')
    if (filter) {
      state.filter = filter as QueueFilter
      render()
      return
    }

    if (target.closest('[data-cycle-sort]')) {
      state.sort = state.sort === 'score' ? 'recent' : 'score'
      render()
      return
    }

    if (target.closest('[data-toggle-labels]')) {
      state.labelsVisible = !state.labelsVisible
      render()
      return
    }

    const triage = target.closest('[data-triage]')?.getAttribute('data-triage')
    if (triage && state.selectedId) {
      const status = triage as TriageStatus
      const current = state.overrides[state.selectedId]
      if (current === status) {
        delete state.overrides[state.selectedId]
      } else {
        state.overrides[state.selectedId] = status
      }
      render()
      return
    }

    if (target.closest('[data-export]')) {
      downloadAlerts(rows, report)
    }
  })

  render()

  map = createDetectionMap(
    {
      container: mapEl,
      aoi: loaded.aoi,
      onSelect: (id) => {
        state.selectedId = id
        render()
      },
    },
    {
      rows,
      labels: loaded.labels,
      selectedId: state.selectedId,
      labelsVisible: state.labelsVisible,
    },
  )
}

function required(root: ParentNode, selector: string): HTMLElement {
  const found = root.querySelector(selector)
  if (!(found instanceof HTMLElement)) throw new Error(`viewer shell is missing ${selector}`)
  return found
}

/**
 * `?labels=` is free-form, so the collection on screen may not be the one the
 * run was scored against. data.crossCheckLabels refuses the collections it can
 * prove wrong; what it cannot prove belongs on screen, above both tabs, rather
 * than in a comment — the Alerts tab saying "no matching label" while the
 * Report tab prints a true positive is exactly the failure this names.
 */
export function labelCheckStrip(loaded: LoadedBenchmark): Raw {
  const check = loaded.labelCheck
  return html`
    <div class="load-note">
      <span class="load-note-key">labels ⚖</span>
      <span>
        ${loaded.resolved.labels} agrees with the report on ${check.agreed.join(' · ')}.
        ${check.limits}
      </span>
    </div>
  `
}

function shell(loaded: LoadedBenchmark): Raw {
  const { report } = loaded
  const window_ = detectionWindow(report.detections)
  const range = window_ ? `${window_.start} → ${window_.end}` : 'no detections in this run'
  const stack = report.killCriteria.synthetic
    ? 'synthetic coherence stack'
    : 'NISAR L-band · 12-day repeat'
  return html`
    <div class="app">
      <header class="header">
        <div class="brand">
          <div class="brand-mark">U</div>
          <div class="brand-name">Understory</div>
          <div class="chip-mono">${report.benchmark}</div>
        </div>
        <nav class="tabs">
          <button class="tab is-active" data-view="alerts" type="button">Alerts</button>
          <button class="tab" data-view="report" type="button">Benchmark report</button>
        </nav>
        <div class="spacer"></div>
        <div class="header-meta">${range} · ${stack}</div>
        <button class="export-btn" data-export type="button">↓ Export alerts.geojson</button>
      </header>

      ${labelCheckStrip(loaded)}

      <div class="alerts" data-alerts-view>
        <aside class="queue" data-queue></aside>
        <main class="map-pane">
          <div class="map-canvas" data-map></div>
          <div class="map-caption" data-caption></div>
          <div class="map-legend" data-legend></div>
        </main>
        <aside class="inspector" data-inspector></aside>
      </div>

      <div class="report" data-report-view style="display:none"></div>

      <footer class="footer">
        <span>methodology v${report.methodologyVersion}</span>
        <span>labels v${report.labelsVersion} · CC-BY 4.0</span>
        <span>detector ${report.detector} ${report.detectorVersion}</span>
        <div class="spacer"></div>
        <span class="footer-source">${loaded.resolved.report}</span>
        <span class="footer-warn">⚠ pre-calibration NISAR stream</span>
      </footer>
    </div>
  `
}

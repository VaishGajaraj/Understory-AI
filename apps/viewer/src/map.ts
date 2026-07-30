/**
 * The MapLibre view, ported layer-for-layer from the design prototype.
 *
 * The one deliberate change: geometries are the real ones. The prototype
 * synthesised squares around a lon/lat with `sqPoly`; here detection polygons
 * come from the report (and the alert GeoJSON), and label polygons from the
 * label library.
 */

import type { Feature, FeatureCollection, Geometry, Point } from 'geojson'
import {
  type GeoJSONSource,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  ScaleControl,
  type StyleSpecification,
} from 'maplibre-gl'

import { LABEL_COLOR, STATUS_COLOR } from './dom'
import { type TriageRow, bboxOf, centroid } from './triage'
import type { DisturbanceEvent } from './types'

const ESRI_WORLD_IMAGERY =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

/** Padding, in degrees, around the data when no AOI outline is supplied. */
const BBOX_PAD_DEG = 0.004

export interface MapData {
  rows: TriageRow[]
  labels: DisturbanceEvent[]
  selectedId: string | null
  labelsVisible: boolean
}

export interface DetectionMapOptions {
  container: HTMLElement
  aoi: Geometry | null
  onSelect: (id: string) => void
}

export interface DetectionMap {
  update(data: MapData): void
  resize(): void
  destroy(): void
}

export function createDetectionMap(options: DetectionMapOptions, initial: MapData): DetectionMap {
  let data = initial
  let ready = false

  const bounds = fitBounds(options.aoi, data)
  const map = new MapLibreMap({
    container: options.container,
    style: baseStyle(),
    bounds,
    fitBoundsOptions: { padding: 36 },
    attributionControl: { compact: true },
  })
  map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-right')
  map.addControl(new NavigationControl({ showCompass: false }), 'top-right')

  const pulse = document.createElement('div')
  pulse.className = 'pulse-marker'
  const marker = new Marker({ element: pulse })

  // The map is created before the stylesheet has necessarily been applied, so
  // the container can still be 0 px tall — MapLibre would then size itself to
  // its 400x300 default and fit the data to the wrong viewport. Re-fit once the
  // pane has real dimensions, and follow it thereafter.
  let fitted = false
  const observer = new ResizeObserver(() => {
    map.resize()
    if (!fitted && options.container.clientHeight > 0 && options.container.clientWidth > 0) {
      map.fitBounds(bounds, { padding: 36, animate: false })
      fitted = true
    }
  })
  observer.observe(options.container)

  map.on('load', () => {
    if (options.aoi) {
      map.addSource('aoi', {
        type: 'geojson',
        data: { type: 'Feature', geometry: options.aoi, properties: {} },
      })
      map.addLayer({
        id: 'aoi-line',
        type: 'line',
        source: 'aoi',
        paint: {
          'line-color': '#6fc48d',
          'line-width': 1.2,
          'line-dasharray': [3, 2],
          'line-opacity': 0.55,
        },
      })
    }

    map.addSource('labels', { type: 'geojson', data: labelFeatures(data.labels) })
    map.addLayer({
      id: 'labels-line',
      type: 'line',
      source: 'labels',
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 1.6,
        'line-dasharray': [2.5, 1.8],
        'line-opacity': 0.85,
      },
    })

    map.addSource('det-pts', { type: 'geojson', data: detectionPoints(data.rows) })
    map.addSource('det-shape', { type: 'geojson', data: detectionShapes(data.rows) })
    map.addLayer({
      id: 'det-glow',
      type: 'circle',
      source: 'det-pts',
      paint: {
        'circle-color': ['get', 'color'],
        'circle-blur': 1.1,
        'circle-opacity': 0.55,
        'circle-radius': ['get', 'glowR'],
      },
    })
    map.addLayer({
      id: 'det-fill',
      type: 'fill',
      source: 'det-shape',
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.75 },
    })
    map.addLayer({
      id: 'det-sel',
      type: 'line',
      source: 'det-shape',
      filter: ['==', ['get', 'id'], data.selectedId ?? ''],
      paint: { 'line-color': '#ffe0a8', 'line-width': 2.4 },
    })

    map.on('click', 'det-fill', (event) => {
      const id = event.features?.[0]?.properties?.id
      if (typeof id === 'string') options.onSelect(id)
    })
    map.on('mouseenter', 'det-fill', () => {
      map.getCanvas().style.cursor = 'pointer'
    })
    map.on('mouseleave', 'det-fill', () => {
      map.getCanvas().style.cursor = ''
    })

    ready = true
    sync()
  })

  function sync(): void {
    if (!ready) return
    setData(map, 'det-pts', detectionPoints(data.rows))
    setData(map, 'det-shape', detectionShapes(data.rows))
    setData(map, 'labels', labelFeatures(data.labels))
    map.setFilter('det-sel', ['==', ['get', 'id'], data.selectedId ?? ''])
    map.setLayoutProperty('labels-line', 'visibility', data.labelsVisible ? 'visible' : 'none')

    const selected = data.rows.find((row) => row.detection.id === data.selectedId)
    if (selected) {
      marker.setLngLat(centroid(selected.detection.geometry)).addTo(map)
    } else {
      marker.remove()
    }
  }

  return {
    update(next: MapData) {
      data = next
      sync()
    },
    resize() {
      map.resize()
    },
    destroy() {
      observer.disconnect()
      marker.remove()
      map.remove()
    },
  }
}

function setData(map: MapLibreMap, id: string, collection: FeatureCollection): void {
  const source = map.getSource(id) as GeoJSONSource | undefined
  source?.setData(collection)
}

function baseStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      sat: {
        type: 'raster',
        tiles: [ESRI_WORLD_IMAGERY],
        tileSize: 256,
        attribution: 'Esri World Imagery',
      },
    },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': '#0c1410' } },
      {
        id: 'sat',
        type: 'raster',
        source: 'sat',
        paint: {
          'raster-brightness-max': 0.62,
          'raster-saturation': -0.3,
          'raster-contrast': 0.08,
        },
      },
    ],
  }
}

function detectionPoints(rows: TriageRow[]): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: rows.map((row) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: centroid(row.detection.geometry) },
      properties: {
        id: row.detection.id,
        color: STATUS_COLOR[row.status],
        // Glow radius scales with event size, as in the prototype. Detections
        // without an area get the minimum dot rather than an invented one.
        glowR: row.detection.areaHa ? Math.round(Math.sqrt(row.detection.areaHa) * 5) : 6,
      },
    })),
  }
}

function detectionShapes(rows: TriageRow[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: rows.map((row) => ({
      type: 'Feature',
      geometry: row.detection.geometry,
      properties: { id: row.detection.id, color: STATUS_COLOR[row.status] },
    })),
  }
}

function labelFeatures(labels: DisturbanceEvent[]): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: labels.map(
      (label): Feature => ({
        type: 'Feature',
        geometry: label.geometry,
        properties: { id: label.id, color: LABEL_COLOR[label.status] },
      }),
    ),
  }
}

function fitBounds(aoi: Geometry | null, data: MapData): [number, number, number, number] {
  const geometries = aoi
    ? [aoi]
    : [...data.rows.map((row) => row.detection.geometry), ...data.labels.map((l) => l.geometry)]
  const box = bboxOf(geometries)
  if (!box) return [-180, -60, 180, 70]
  const [west, south, east, north] = box
  const pad = aoi ? 0 : BBOX_PAD_DEG
  return [west - pad, south - pad, east + pad, north + pad]
}

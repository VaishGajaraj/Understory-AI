/**
 * The smallest amount of DOM machinery this app needs: an escaping template
 * tag, a mount helper, and the shared presentation constants. No framework —
 * two read-mostly views re-render from state on every change.
 */

import type { TriageStatus } from './triage'

export const STATUS_COLOR: Record<TriageStatus, string> = {
  candidate: '#e8a33d',
  confirmed: '#57b87b',
  rejected: '#c76e5e',
}

export const LABEL_COLOR = { confirmed: '#57b87b', rejected: '#c76e5e', candidate: '#8fa396' }

/** Markup that is already safe to insert. */
export class Raw {
  constructor(readonly value: string) {}
  toString(): string {
    return this.value
  }
}

export function raw(value: string): Raw {
  return new Raw(value)
}

export function esc(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** Tagged template: interpolations are escaped unless wrapped in `raw()`. */
export function html(strings: TemplateStringsArray, ...values: unknown[]): Raw {
  let out = ''
  strings.forEach((chunk, i) => {
    out += chunk
    if (i < values.length) out += render(values[i])
  })
  return new Raw(out)
}

function render(value: unknown): string {
  if (value === null || value === undefined || value === false) return ''
  if (value instanceof Raw) return value.value
  if (Array.isArray(value)) return value.map(render).join('')
  return esc(String(value))
}

export function setHtml(target: Element, markup: Raw): void {
  target.innerHTML = markup.value
}

export function fixed(value: number, digits: number): string {
  return value.toFixed(digits)
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

/** "+26" / "−4" — the design's sign convention for day counts. */
export function signedDays(days: number): string {
  return days < 0 ? `−${Math.abs(days)}` : `+${days}`
}

/**
 * Development server.
 *
 * Bun bundles index.html (and its TypeScript/CSS) on the fly; data files are
 * served read-only from the repository so the app can fetch what a real run
 * wrote — benchmarks/<name>/reports/*.json, the alert GeoJSON beside it, and
 * packages/understory-labels/data/events/*.geojson.
 *
 *   bun run dev            # http://localhost:5173
 *   PORT=8080 bun run dev
 *   HOST=0.0.0.0 bun run dev   # expose on the LAN, deliberately
 */

import index from './index.html'

const REPO_ROOT = new URL('../../', import.meta.url)

/**
 * Loopback by default. Bun.serve binds every interface when hostname is
 * omitted, which on a shared network would publish the repository to anyone who
 * can reach the port. Exposing it is a deliberate choice via HOST, not an
 * accident of the default.
 */
const HOST = process.env.HOST ?? '127.0.0.1'

/**
 * The viewer only ever fetches pipeline output, so the server only ever serves
 * pipeline output. An allowlist rather than a denylist: this directory sits in a
 * repository whose .gitignore lists .env and .netrc at the root, and a denylist
 * is one forgotten entry away from serving them.
 */
const SERVABLE_EXTENSIONS = ['.json', '.geojson']

function resolveInRepo(pathname: string): URL | null {
  let target: URL
  try {
    target = new URL(`.${decodeURIComponent(pathname)}`, REPO_ROOT)
  } catch {
    return null
  }
  if (!target.pathname.startsWith(REPO_ROOT.pathname)) return null

  const relative = target.pathname.slice(REPO_ROOT.pathname.length)
  // No dot-segments anywhere in the path: blocks .git/, .env, .netrc and the
  // rest of the dotfiles, including as intermediate directories.
  if (relative.split('/').some((segment) => segment.startsWith('.'))) return null
  if (!SERVABLE_EXTENSIONS.some((extension) => relative.endsWith(extension))) return null
  return target
}

// Only listen when run directly. Importing this module to test resolveInRepo
// must not open a port, or `bun test` would race a running dev server.
if (import.meta.main) {
  const server = Bun.serve({
    port: Number(process.env.PORT ?? 5173),
    hostname: HOST,
    development: true,
    routes: { '/': index },
    async fetch(request) {
      const { pathname } = new URL(request.url)
      const target = resolveInRepo(pathname)
      if (target) {
        const file = Bun.file(target)
        if (await file.exists()) {
          // Last-Modified is the only run timestamp available: the report
          // itself records none (see README).
          return new Response(file, {
            headers: { 'last-modified': new Date(file.lastModified).toUTCString() },
          })
        }
      }
      return new Response(`not served: ${pathname}\n`, { status: 404 })
    },
  })

  console.log(`understory viewer → ${server.url}`)
  console.log(`serving ${SERVABLE_EXTENSIONS.join(' / ')} from ${REPO_ROOT.pathname}`)
}

export { resolveInRepo }

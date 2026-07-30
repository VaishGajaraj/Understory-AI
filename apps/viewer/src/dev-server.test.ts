import { describe, expect, test } from 'bun:test'
import { resolveInRepo } from '../dev-server'

/**
 * The dev server sits in a repository whose .gitignore lists .env and .netrc at
 * the root, and it once bound every interface while serving any path that did
 * not escape the repo. These pin the allowlist so it cannot regress into a
 * denylist with a hole in it.
 */
describe('resolveInRepo', () => {
  test('serves the pipeline output the viewer actually fetches', () => {
    expect(resolveInRepo('/benchmarks/toy/reports/toy.json')).not.toBeNull()
    expect(resolveInRepo('/benchmarks/toy/reports/toy-alerts.geojson')).not.toBeNull()
    expect(
      resolveInRepo('/packages/understory-labels/data/events/toy-fixtures.geojson'),
    ).not.toBeNull()
  })

  test('refuses dotfiles and dot-directories anywhere in the path', () => {
    expect(resolveInRepo('/.env')).toBeNull()
    expect(resolveInRepo('/.netrc')).toBeNull()
    expect(resolveInRepo('/.git/config')).toBeNull()
    expect(resolveInRepo('/.git/../.env')).toBeNull()
    expect(resolveInRepo('/packages/.hidden/secrets.json')).toBeNull()
  })

  test('refuses anything that is not a data file, whatever its location', () => {
    expect(resolveInRepo('/Makefile')).toBeNull()
    expect(resolveInRepo('/pyproject.toml')).toBeNull()
    expect(resolveInRepo('/uv.lock')).toBeNull()
    expect(resolveInRepo('/packages/understory-core/src/understory_core/stack.py')).toBeNull()
  })

  test('refuses paths that escape the repository', () => {
    expect(resolveInRepo('/../../../etc/passwd')).toBeNull()
    expect(resolveInRepo('/../secrets.json')).toBeNull()
  })

  test('refuses percent-encoded traversal and dotfiles', () => {
    expect(resolveInRepo('/%2e%2e/%2e%2e/etc/passwd.json')).toBeNull()
    expect(resolveInRepo('/%2eenv')).toBeNull()
  })
})

# Modern TypeScript Monorepo: Tools & Techniques Guide

A general-purpose playbook distilled from the Hanover codebase (a Bun + Turborepo + Next.js + Supabase + tRPC + SST FinTech platform). Each section explains a tool or technique, why it's used, and how to apply it to your own projects.

---

## 1. Guiding Philosophy

- **As simple as possible, but no simpler.** Lightweight, modular, easy-to-understand code beats clever abstractions.
- **Iterate fast; performance is secondary.** Optimize for change velocity in early-stage projects.
- **No fallbacks left behind.** When you upgrade or replace an implementation, delete the old one. Dead code paths destroy clarity.
- **Uniformity over novelty.** Every package in the repo uses the same script names (`lint`, `typecheck`, `test`), same config bases, same export style — so tooling works identically everywhere.

---

## 2. Monorepo Foundation

### Structure

```
repo/
├── apps/          # deployable things
│   ├── app/       # Next.js frontend
│   ├── api/       # serverless backend (SST)
│   ├── cli/       # operational scripts (bash + bun)
│   └── supabase/  # database migrations & config
├── packages/      # shared libraries
│   ├── lib/       # core domain logic (framework-agnostic)
│   ├── db/        # generated database types + schema
│   ├── trpc/      # API layer (routers, procedures, middleware)
│   ├── ui/        # design system
│   ├── formatters/# pure formatting utilities
│   └── typescript-config/  # shared tsconfig + test harness
├── turbo.json     # task orchestration
├── biome.json     # lint + format
├── knip.json      # dead code detection
└── lefthook.yml   # git hooks
```

**Rule of thumb:** apps depend on packages, never the reverse. Packages have an explicit dependency direction (see §4).

### Bun as package manager + runtime

- `"packageManager": "bun@x.y.z"` in root `package.json`, `engines.node >= 22`.
- Workspaces: `"workspaces": ["apps/*", "packages/*", "!packages/template"]` — note the `!` exclusion for scaffold templates so they're never installed as real deps.
- `bunfig.toml` with `[install] linker = "hoisted"` and `[test] preload = [...]` for global test setup.
- Bun doubles as a script runner: one-off TS scripts run directly with `bun run script.ts`, no build step.

### Turborepo for task orchestration

Key `turbo.json` techniques:

- **`globalEnv` allowlist**: declare every env var tasks depend on so caching is correct. Undeclared env vars silently break cache invalidation.
- **`globalDependencies`**: `["package.json", "packages/typescript-config/base.json"]` — changing shared config busts all caches.
- **Task graph**: `build` and `typecheck` use `"dependsOn": ["^build"]` / `["^typecheck"]` (upstream-first); `dev` is `"cache": false, "persistent": true`.
- Packages extend the root config with `"extends": ["//"]` in their own `turbo.json`.
- Root scripts just delegate: `"build": "turbo run build"`, `"typecheck": "turbo run typecheck"` (plus a short alias `"tc"`).

---

## 3. Code Quality Toolchain

One tool per job, all fast, all enforced:

| Tool | Job | Notes |
|---|---|---|
| **Biome** | Lint + format (replaces ESLint + Prettier) | Single config, very fast |
| **tsgo / tsc** | Typecheck (`--noEmit`) | The real correctness gate |
| **knip** | Find unused files, exports, dependencies | Run periodically |
| **syncpack** | Keep dependency versions aligned across workspaces | `list-mismatches` / `fix-mismatches` |
| **lefthook** | Git pre-commit hooks | Runs Biome on staged files only |
| **bun test** | Unit tests | Native runner, no Jest |

### Biome techniques worth copying

- Style baseline: 2-space indent, 100-char lines, single quotes, `semicolons: "asNeeded"`, LF endings.
- `domains: { next: "recommended", react: "recommended" }` for framework-aware rules.
- **Enforce filename convention with the linter**: `useFilenamingConvention` with `kebab-case` — no debates, no drift.
- **Enforce architecture with `noRestrictedImports` overrides.** This is the standout technique: per-directory overrides make circular dependencies and layering violations a lint error, e.g.:
  - `packages/lib` may not import `@yourorg/trpc` or `@yourorg/ui` (circular dep).
  - Packages may not import themselves via their own export alias ("breaks type checking — use relative import").
  - The app may not import server-only packages (`@yourorg/ai`).
- Import organization via `assist.actions.source.organizeImports` with groups: built-ins/external → `@yourorg/**` → blank line → local.
- `vcs.useIgnoreFile: true` so Biome respects `.gitignore`.

### lefthook pre-commit

```yaml
pre-commit:
  parallel: true
  commands:
    biome:
      glob: "*.{js,ts,cjs,mjs,jsx,tsx,json,jsonc}"
      run: bun biome check --write --no-errors-on-unmatched --files-ignore-unknown=true {staged_files}
      stage_fixed: true   # auto-stages the fixes — commits are always formatted
```

Keep the hook to formatting only (fast); leave typecheck/tests to CI.

### knip

- Treat script directories as entry points (`"apps/cli": { "entry": ["bun/**/*.ts"] }`) so operational scripts aren't flagged as dead code.
- Maintain an explicit `ignoreDependencies` list for things loaded implicitly (postcss, tailwind, test DOM libs).

---

## 4. Shared Package Design

### Subpath exports serving source directly

Internal packages skip the build step entirely — `exports` maps point at `.ts` source:

```jsonc
// packages/ui/package.json
"exports": {
  "./globals.css":  "./src/globals.css",
  "./lib/*":        { "default": "./src/lib/*.ts" },
  "./primitives/*": { "default": ["./src/primitives/*.tsx", "./src/primitives/*.ts"] }
}
```

Consumers import granularly (`@yourorg/ui/primitives/button`), which keeps bundles lean and makes usage greppable. Arrays in the export target let both `foo.ts` and `foo/index.ts` resolve.

### Explicit dependency direction

```
formatters (pure, depends on nothing internal)
   ↑
lib (core domain logic; consumes db types)
   ↑
trpc, ui, email, ai
   ↑
apps
```

Encode this in Biome `noRestrictedImports` (see §3) so it can't erode.

### A `typescript-config` package as the shared toolchain

More than tsconfig — it's the "typecheck + test harness" package:

- `base.json`: strict everything (`strict`, `noUnusedLocals/Parameters`, `noFallthroughCasesInSwitch`, `noImplicitOverride`), `module/target: ESNext`, `moduleResolution: Bundler`, `isolatedModules`, `skipLibCheck`.
- Variants: `react-library.json` (adds `jsx: react-jsx`), `nextjs.json` (Next plugin, `noEmit`, `jsx: preserve`).
- Ships shared test setup files (`test/setup.ts`, `test/ui-setup.ts`) and owns test devDeps (happy-dom, jest-dom matchers), so every package's `bunfig.toml` can just `preload` them.

### Workspace scaffolding

`turbo generate workspace --copy @yourorg/template --name` clones a template package to scaffold new ones with the standard scripts/exports/config already in place. Exclude the template from workspaces (`!packages/template`).

---

## 5. Database Layer (Supabase + Drizzle)

### DB-as-source-of-truth codegen

The schema lives in raw SQL migrations; all TypeScript types are *generated* from the database:

1. **Migrations**: timestamped raw SQL files (`YYYYMMDDHHMMSS_name.sql`) created via `supabase migration new` or `supabase db diff --local -f` (diff your local DB against migrations to auto-generate the migration).
2. **Type generation** (one script, run via root `sync-types`):
   - `supabase gen types --local` → `packages/db/src/supabase/database.ts` (typed client, `Tables<'x'>`, `TablesInsert<'x'>`, `Enums<'x'>`).
   - `drizzle-kit pull` (introspection) → regenerate Drizzle `schema.ts`/`relations.ts`.
   - `sed` post-processing fixes known introspection bugs, then Biome formats the output.
3. **Data migrations** (backfills) live in a separate `data-migrations/` folder — never mix schema changes and data transformations.

### Two data-access patterns, deliberately

- **Supabase client (raw-ish SQL)** for simple queries — typed via the generated `Database` type: `type TypedSupabaseClient = SupabaseClient<Database>`.
- **Drizzle ORM** for transactions and complex queries.

Shared library code never *creates* clients — it accepts an injected typed client, keeping it environment-agnostic.

### Serverless connection management: cached Drizzle singleton

For Lambda/serverless, cache the DB client at module scope, keyed by a hash of the connection string, with a tiny pool:

```ts
postgres(url, { max: 1, idle_timeout: 10, max_lifetime: 60 * 15 })
```

This prevents connection-pool exhaustion across warm starts. This one pattern saves real production pain.

### Authorization in the database

Row-Level Security (RLS) policies enforce access at the database layer, in addition to application-layer permission middleware. Defense in depth.

---

## 6. Type-Safe API Layer (tRPC)

### Structure

```
packages/trpc/src/
├── routers/          # one file per domain (health.ts, firms.ts, ...)
└── server/
    ├── init.ts       # initTRPC + base procedures
    ├── context.ts    # context types
    └── middleware.ts # procedure builders (auth tiers)
```

### Layered procedure builders

Build an escalating chain of procedures; routers pick the right tier and get a fully-typed, enriched context:

```ts
publicProcedure        // tracing + audit middleware only
  → protectedProcedure // requires ctx.user, injects services
    → orgMemberProcedure / orgAdminProcedure  // .input(orgSchema).use(resolveMembership)
```

Techniques inside:

- `initTRPC.context<BaseContext>().create({ transformer: superjson, errorFormatter })` — the error formatter flattens Zod errors so clients get typed validation errors.
- The auth middleware **narrows the context type** (`user` becomes non-null) via `next<ProtectedContext>({ ctx: ... })`.
- One shared `resolveMembership()` helper backs all org-scoped procedure variants — auth logic lives in exactly one place.
- **Compile-time perf**: export explicit type aliases for procedure builders (`export type ProtectedProcedure = ...`) so tsc doesn't re-infer deep generic chains on every use.
- Role-based rules per procedure via `.meta({ requiredRoles: [...] })` checked in middleware.
- Keep a documented rubric for what goes in `ctx.services` (e.g., "external API + feature-agnostic + widely used") so context doesn't become a junk drawer.

### Router pattern

```ts
export const thingsRouter = router({
  list: orgMemberProcedure
    .input(z.object({ ... }))
    .query(async ({ ctx, input }) => { ... }),
  create: orgAdminProcedure
    .input(createThingSchema)
    .mutation(async ({ ctx, input }) => {
      // bind Zod output to generated DB types at compile time:
      const row = input satisfies TablesInsert<'things'>
    }),
})
```

### One router, multiple deployment targets

Compose the same routers three ways: a Lambda-served router, a server-side caller for React Server Components, and an `AppRouter` type export for the browser client. Same code, three consumption modes.

---

## 7. Frontend (Next.js App Router + TanStack Query)

### Server-first component model

- Server Components by default; `'use client'` only for interactivity.
- Route groups organize the app: `(auth)`, `(protected)`, `(misc)`; dynamic segments for tenancy (`(protected)/[orgSlug]/...`).
- Path alias (`#/` or `@/`) for app-root imports.

### The tRPC + React Query integration (three-file convention)

- **`lib/trpc/server.tsx`** — starts with `import 'server-only'` (build error if it leaks to the client). Exposes a direct server-side caller (`createCaller`), `getQueryClient = cache(makeQueryClient)` (one QueryClient per request via React `cache()`), and `prefetch()` + `<HydrateClient>` helpers. RSC pages prefetch queries on the server; client components hydrate them with zero refetch.
- **`lib/trpc/client.tsx`** — `'use client'`; `createTRPCContext<AppRouter>()` → a `useTRPC` hook. Client links: `splitLink` for opt-out-able request batching (`httpBatchLink` with `maxItems`, bypass via `op.context.skipBatch`), auth header injected from the session, `loggerLink` in dev, and an error link piping failures to Sentry.
- **`lib/trpc/query-client.ts`** — `makeQueryClient()` with a default `staleTime` (e.g. 60s), superjson serialization for SSR dehydration, and `shouldDehydrateQuery` extended to include pending queries (streaming prefetch).

Usage in components:

```ts
const { data, isPending, error } = useQuery(trpc.things.list.queryOptions({ ... }))
```

### Client state: Zustand

Small stores in `lib/stores/*.ts` using `create<T>()(persist(..., { name, partialize }))` — persist only a whitelisted subset of state. React Query owns server state; Zustand owns pure UI/client state. Don't mix.

### Environment handling

A shared `ENVIRONMENTS` constant (`['production','staging','demo','sandbox'] as const`) lives in the core package and is reused by frontend env detection, SST stage validation, and CLI scripts. One source of truth for "what environments exist." Show a visible environment badge in non-production UIs.

### Provider stack

Compose providers once in the root layout: Analytics → Theme → Tooltip → tRPC/Query → Auth. Import the design system's `globals.css` from the UI package.

---

## 8. Design System Package

- **shadcn/ui-style primitives** in `src/primitives/` (owned, copied-in components over black-box libraries — Radix UI underneath), composed app-level components in `src/design-system/`, plus `src/hooks/` and `src/lib/`.
- `components.json` points the shadcn CLI at your primitives dir so `npx shadcn add` keeps working.
- The `cn` utility everywhere: `const cn = (...i: ClassValue[]) => twMerge(clsx(i))`.
- `class-variance-authority` (cva) for component variant APIs.
- **Tailwind v4, CSS-first**: no `tailwind.config.js`; `@import "tailwindcss"`, `@plugin`, `@custom-variant dark`, theme tokens as CSS variables (oklch). Use `@source "../../apps/app/**/*.{ts,tsx}"` in the package's globals.css so consumer files get scanned for classes.
- Always check the design system for an existing component before building a new one.

---

## 9. Serverless Backend (SST v3 on AWS)

### Infrastructure as typed code

Everything in one `sst.config.ts`:

- **Environments as code**: the `ENVIRONMENTS` const drives typed records (`API_URLS satisfies Record<Environment, string>`), branch→stage autodeploy mapping (`main` → production, `staging` → staging...), `protected: ENVIRONMENTS.includes(stage)` and `removal: 'retain'` to guard real stages from accidental teardown.
- **Secrets** as grouped `sst.Secret` objects, linked to functions by spreading: `link: [...Object.values(secrets.db)]`.
- **Transform helpers**: a single `addSourcemapConfig(args)` function applied to every Lambda (Sentry release from `git rev-parse HEAD`, esbuild `sourcemap: 'linked'`) — including gateway routes via `transform.route.handler`. Configure once, apply uniformly.
- **Queues** for async work: `new sst.aws.Queue(...)` + `.subscribe(handler)` with explicit `visibilityTimeout`, `timeout`, `memory`.
- **Crons**: `new sst.aws.Cron('Name', { schedule: 'cron(...)', function: {...} })`.

### Lambda handler wrappers

A `wrapHandler(handler, { schema })` factory per trigger type (api-gateway / cron / webhook) that centralizes:

- `context.callbackWaitsForEmptyEventLoop = false`
- Zod validation of the incoming event
- Sentry trace restoration from `sentry-trace`/`baggage` headers, and `Sentry.withMonitor()` check-ins for crons
- Uniform error capture

Handlers then contain only business logic.

### tRPC-on-Lambda niceties

- **Per-path resource injection**: only attach the queue URLs/secrets a given procedure path actually needs — least-privilege per invocation.
- Gzip responses over 1KB; alert when payloads approach the 6MB Lambda response limit.
- `onError`: wrap unknown errors preserving `cause`; downgrade expected codes (`BAD_REQUEST`, `FORBIDDEN`) to info-level in Sentry.

---

## 10. Testing

- **Bun's native test runner** — no Jest. Test files: `*.test.ts` / `*.spec.ts`, colocated next to source.
- Global setup via `bunfig.toml` `[test] preload`, shipped from the shared config package: force `TZ=UTC`, register happy-dom + testing-library matchers for UI packages.
- Focus tests on **utility functions and critical business logic** (financial calculations, parsers). The primary quality gates are `typecheck` + `lint`; don't chase coverage on glue code.

```ts
import { describe, expect, test } from 'bun:test'

describe('computeIrr', () => {
  test.each([
    [input1, expected1],
    [input2, expected2],
  ])('handles %p', (input, expected) => {
    expect(computeIrr(input)).toBe(expected)
  })
})
```

---

## 11. Error Handling & Observability

- **Always chain `cause`**: `throw new Error(\`loading things: ${e.message}\`, { cause: e })` — preserves the original stack/details for Sentry.
- At the API boundary, throw `TRPCError({ code, message, cause })`; a global `onError` wraps anything else as `INTERNAL_SERVER_ERROR` keeping the original as `cause`.
- Non-critical side effects (audit logging, telemetry) go in try/catch that logs but never fails the request.
- **Distributed tracing end-to-end**: propagate Sentry trace headers from browser → RSC → Lambda so one trace covers the whole request.

---

## 12. Operational Scripts (the `apps/cli` pattern)

Commit operational logic as reviewable scripts instead of running ad-hoc commands:

- **`bash/`** for environment plumbing. Every script starts with `ROOT_DIR=$(git rev-parse --show-toplevel)` so it works from anywhere. Examples worth replicating:
  - `clean_deps.sh` — nuke `node_modules/.turbo/.next/dist` across all workspaces.
  - `update_deps.sh` — `bun update` each workspace, then root install.
  - `refresh_aws_creds.sh` — `aws sso login`, extract keys from the CLI cache with `jq`, write `~/.aws/credentials` (backing up the old file first).
  - DB dump/reset scripts parameterized by environment.
- **`bun/`** for one-off TypeScript scripts (migrations, bulk emails, integration backfills), organized by domain, run directly with `bun run`. They reuse the same shared packages (`@yourorg/db`, `@yourorg/lib`) as the apps, use `commander` for CLI args and `chalk` for output, and get colocated `.spec.ts` tests for shared helpers.
- Wire the common ones into root `package.json` scripts so they're discoverable (`bun run clean-deps`).

---

## 13. Documentation for AI Tooling

Keep a `CLAUDE.md` (and/or `AGENTS.md`) at the repo root covering: philosophy, commands, architecture map, code style, common patterns with short code examples, environment setup, and constraints. This makes AI coding assistants dramatically more effective and doubles as onboarding docs for humans. Keep it current as conventions evolve.

---

## 14. Applying These Standards Beyond TypeScript

Most of this guide is not actually about TypeScript — it's about **enforcement mechanisms**. The transferable core, in priority order:

1. **Version control from day one.** Nothing else can be enforced without it (hooks, CI, reviews all hang off git).
2. **One manifest + one lockfile.** Declare dependencies and tool config in a single canonical file (`package.json` → `pyproject.toml` / `go.mod` / `Cargo.toml`).
3. **One fast tool per job — format, lint, typecheck, test, dead-code** — each runnable as a single command with config committed to the repo.
4. **Uniform task names across every project** (`fmt`, `lint`, `typecheck`, `test`, `dev`), fronted by a language-neutral task runner (`Makefile`, `justfile`, or `mise` tasks) so muscle memory and CI are identical whether the repo is TS, Python, or Rust.
5. **Enforce mechanically, not socially**: pre-commit hooks (lefthook is language-agnostic) for formatting, CI for typecheck + lint + test. A convention that isn't a failing check will drift.
6. **Architecture as lint rules**: whatever the language, encode layering ("core imports nothing from apps") in an import-linter rather than a wiki page.
7. **Generated types from the source of truth** (DB schema, API spec) rather than hand-maintained duplicates.
8. **Committed operational scripts** instead of ad-hoc shell history.
9. **A `CLAUDE.md`/`AGENTS.md`** documenting philosophy, commands, and patterns.

### Tool mapping by language

| Job | TypeScript (this guide) | Python | Go | Rust |
|---|---|---|---|---|
| Package/env manager | Bun | **uv** | go mod | cargo |
| Format + lint | Biome | **ruff** (`ruff format` + `ruff check`) | gofmt + golangci-lint | rustfmt + clippy |
| Type checking | tsc / tsgo | **pyright** or mypy (strict) | compiler | compiler |
| Tests | bun test | **pytest** | go test | cargo test |
| Dead code / unused deps | knip | ruff (F401/F841) + vulture, `uv` for deps | golangci-lint (unused) | clippy + cargo-udeps |
| Import/layer rules | Biome `noRestrictedImports` | **import-linter** or ruff `TID` (banned-api/relative rules) | depguard (golangci-lint) | cargo workspaces + visibility |
| Git hooks | lefthook | lefthook or pre-commit | lefthook | lefthook |
| Task runner | turbo + package scripts | **just / Makefile** (or uv scripts) | Makefile | cargo aliases / just |
| Version pinning | packageManager field + bun.lock | `uv.lock` + `requires-python` | go.mod | Cargo.lock |

### Minimal Python enforcement kit (~4 files)

```toml
# pyproject.toml
[project]
name = "myproject"
requires-python = ">=3.12"

[tool.ruff]
line-length = 100
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "TID"]  # errors, imports, modernize, bugbear

[tool.pyright]
typeCheckingMode = "strict"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```yaml
# lefthook.yml — same tool as the TS repos
pre-commit:
  parallel: true
  commands:
    ruff:
      glob: "*.py"
      run: uv run ruff format {staged_files} && uv run ruff check --fix {staged_files}
      stage_fixed: true
```

```make
# Makefile — uniform verbs across all repos
fmt:        ; uv run ruff format .
lint:       ; uv run ruff check .
typecheck:  ; uv run pyright
test:       ; uv run pytest
check: fmt lint typecheck test
```

Plus one CI workflow that runs `make check`. Direct analogues: ruff's import rules ≈ Biome `noRestrictedImports`; `uv.lock` ≈ `bun.lock`; pyright strict ≈ `strict: true` tsconfig; import-linter contracts ≈ the package dependency graph in §4.

### Sharing standards across many repos

- Keep a **standards repo** (or this doc + a template repo per language) holding the canonical `ruff`/`biome`/`lefthook`/CI configs; new projects copy or template from it (the `turbo gen workspace --copy` idea, generalized — `copier`/`cookiecutter` for Python).
- Tool configs can be *inherited* rather than copied where supported: `extends` in Biome/tsconfig, `[tool.ruff] extend = "../ruff-base.toml"`, shared reusable CI workflows (`uses: org/standards/.github/workflows/check.yml`).
- The uniform `make check` contract means one org-wide CI workflow can enforce every repo regardless of language.

---

## Quick-Start Checklist for a New Project

1. `bun init` a workspace monorepo: `apps/*`, `packages/*`; pin `packageManager`.
2. Add Turborepo with `build`/`dev`/`lint`/`typecheck`/`test` tasks and a `globalEnv` allowlist.
3. Add Biome (format + lint + import organization + filename convention), lefthook pre-commit, knip, syncpack.
4. Create `packages/typescript-config` with strict `base.json` + variants + shared test setup.
5. Create `packages/lib` (domain logic) and `packages/ui` (cn + cva + Tailwind v4 + shadcn primitives), with source-serving subpath exports.
6. Enforce the package dependency graph with Biome `noRestrictedImports` overrides.
7. Set up the database with SQL migrations + generated types (`supabase gen types` / `drizzle-kit pull`) and a `sync-types` script.
8. Build the API as tRPC with layered procedure builders (public → authed → scoped) and superjson.
9. Wire Next.js App Router with the server/client/query-client tRPC trio; server-prefetch + hydrate.
10. Define infrastructure in SST with environments-as-code, secrets, and handler wrappers.
11. Add an `apps/cli` for committed operational scripts.
12. Write the `CLAUDE.md`.

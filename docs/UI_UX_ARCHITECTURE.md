# OG Foreman UI/UX Architecture

## Status

Phase 0 audit and freeze completed on 2026-08-13. This document records the
frontend baseline and the migration boundary for `docs/UI_UX_OVERHAUL.md`.
No product behavior or API contract changed during this phase.

## Existing structure

The frontend is a Next.js 16 App Router application with React 19. Public routes
cover the marketing page, deterministic demo, sign-in, sign-up, and project
selection. Authenticated project routes share `ProjectProvider` and `AppShell`.

Current project routes are:

| Route | Current responsibility | Target module |
| --- | --- | --- |
| `/projects/[id]` | Dashboard/command center | Overview |
| `/projects/[id]/site` | Voice, text, photo, and file intake | Global Ask OG drawer/sheet |
| `/projects/[id]/tasks` | Filtered task table and task creation | Tasks register |
| `/projects/[id]/materials` | Inventory table, quantity adjustment, creation | Materials inventory/requests |
| `/projects/[id]/reports` | Single daily report projection | Reports, then Daily Logs |
| `/projects/[id]/activity` | Paginated activity table | Chronological Activity stream |
| `/projects/[id]/approvals` | Approval and follow-up cards | Needs Attention/approval detail |

There are no routes yet for Schedule, Issues, Daily Logs, Photos, or Documents.
Those routes must initially render honest empty/unsupported states against the
existing snapshot rather than inventing client-side records.

## Runtime boundaries

### Authentication and project state

- `src/lib/auth.tsx` owns Firebase session state and installs the API token
  provider.
- `components/project-context.tsx` loads one authenticated project snapshot and
  exposes `{ projectId, snapshot, refresh }`.
- `app/projects/[id]/layout.tsx` is the single composition boundary for project
  context and the application shell.
- Project identity comes from `snapshot.project`; it is not inferred from route
  labels or display names.

This boundary is retained. Phase 1 may extend shell-facing context with a project
list only if the existing authenticated API supplies it; it must not duplicate
project state in a second provider.

### API layer

`lib/api.ts` is the only browser API boundary. It provides authenticated fetch,
one forced token refresh on `401`, versioned error handling, project bootstrap,
project/snapshot reads, task and material creation, material ledger adjustment,
signed media upload, site-update submission, run polling, and approval decisions.

The current `ProjectSnapshot` supplies project, tasks, materials, approvals,
activities, and one daily report. It does not supply issue, schedule, document,
photo-register, or daily-log collections. UI phases must preserve these contracts
and expose missing projection work explicitly instead of fabricating production
data or redesigning backend models for presentation.

### Golden Scenario

`SiteComposer` is the working Golden Scenario entry point. It uploads media,
submits the authenticated update, polls the persisted agent run, refreshes the
project snapshot, and renders a safe workflow receipt. `ApprovalList` preserves
human approval and stale-version conflict handling. These behaviors are retained
while their presentation moves into the Ask OG and approval experiences.

## Existing presentation baseline

- `app/globals.css` is one global stylesheet containing marketing, auth, project,
  component, responsive, and animation rules. It already defines semantic color,
  spacing, status, table, modal, loading, and reduced-motion patterns, but mixes
  obsolete card/glass styles with reusable primitives.
- Desktop uses a fixed 246 px sidebar. Below 820 px it becomes a two-column menu
  overlay; below 560 px tables and dialogs receive only partial mobile treatment.
- Tasks, Materials, and Activity already use tables, but row details are modal or
  absent. Overview and approvals remain card-heavy.
- `AppShell` contains project selection UI, project navigation, approval count,
  mobile menu, and sign-out. Search, a persistent Ask OG action, field-first bottom
  navigation, and the complete construction module navigation do not exist.
- Loading and error boundaries exist at project level. Module-specific empty
  states exist for tasks, materials, approvals, and activity, but are inconsistent.

## Component disposition

### KEEP

| Component/file | Reason |
| --- | --- |
| `src/lib/auth.tsx`, `src/lib/firebase.ts` | Production authentication boundary |
| `lib/api.ts` and tests | Typed, authenticated API boundary and error contract |
| `components/project-context.tsx` | Single project snapshot and refresh source |
| `components/pagination.tsx` | Small reusable register primitive |
| `components/task-create-dialog.tsx` | Working task mutation UI; restyle later |
| `components/material-create-dialog.tsx` | Working typed material creation; restyle later |
| `app/projects/[id]/error.tsx`, `loading.tsx` | Route-level recovery/loading boundary |
| Auth screens and public product routes | Outside authenticated overhaul scope unless branding text conflicts |

### REWORK

| Component/file | Migration |
| --- | --- |
| `components/app-shell.tsx` | Phase 1: complete module nav, search interface, project selector, persistent Ask OG, mobile navigation, page-header slot |
| `components/command-center.tsx` | Phase 2: operational overview with four compact KPIs, attention list, Today, and lookahead table |
| `components/task-board.tsx` | Phase 3: full work register, search/filter state, and task detail drawer |
| `app/projects/[id]/materials/page.tsx` | Phase 3: Inventory/Requests tabs and material detail drawer |
| `components/site-composer.tsx` | Phase 7: preserve intake state machine inside global drawer/full-screen sheet |
| `components/workflow-receipt.tsx` | Phase 7: operational outcome language and linked records |
| `components/approval-list.tsx` | Phase 9: deliberate approval detail and clearer stale conflict receipt |
| `app/projects/[id]/reports/page.tsx` | Phase 5/Reports: separate Daily Logs from report/export presentation |
| `app/projects/[id]/activity/page.tsx` | Phase 8: continuous chronological audit stream with filters and object links |
| `app/projects/page.tsx` | Align authenticated project selection and visible brand with the new shell |
| `app/globals.css` | Incrementally split/reduce obsolete styles after each owning component migrates |
| Existing component and E2E tests | Preserve behavior while updating accessible names and route expectations |

### DELETE AFTER REPLACEMENT

| Component/style | Replacement condition |
| --- | --- |
| Standalone `/site` navigation entry | Delete from navigation after global Ask OG opens the retained composer |
| Dashboard naming and dashboard-only activity pagination | Delete when Overview and Activity own those responsibilities |
| Card-grid overview and static `OG's brief` copy | Delete in Phase 2 when facts come from snapshot projections |
| Card-based approval/follow-up layout | Delete in Phase 9 after approval detail experience passes |
| Material centered modal and inline presentation styles | Delete after the shared detail drawer is live |
| `glass-panel`, decorative pulse/rise styles used by authenticated shell | Delete when Phase 1 shell no longer references them |
| Obsolete CSS selectors | Remove only in the same verified phase that removes their final consumer |

`components/oga-demo.tsx` remains isolated to the public deterministic demo. It
must never become an authenticated data fallback.

## Target structure

The migration should converge on these boundaries without requiring an immediate
directory rewrite:

```text
app/projects/[id]/
  page.tsx                 Overview
  schedule/page.tsx
  tasks/page.tsx
  issues/page.tsx
  materials/page.tsx
  daily-logs/page.tsx
  photos/page.tsx
  documents/page.tsx
  reports/page.tsx
  activity/page.tsx

components/project-shell/
  project-shell.tsx
  project-navigation.tsx
  project-selector.tsx
  global-search.tsx
  mobile-navigation.tsx

components/shared/
  page-header.tsx
  record-table.tsx
  filter-bar.tsx
  detail-drawer.tsx
  status-indicator.tsx
  empty-state.tsx

components/modules/
  overview/
  schedule/
  tasks/
  issues/
  materials/
  daily-logs/
  photos/
  documents/
  reports/
  activity/
  approvals/
  og/
```

Directories should be introduced only when a phase produces multiple cohesive
files. Existing files may move with their tests in the same increment.

## Shared primitives

Phase work should converge on a small set of semantic primitives:

- `PageHeader`: one page title, optional description, metadata, and actions.
- `RecordTable`: accessible desktop register with explicit responsive fallback.
- `FilterBar`: URL-backed search, filters, and result count where sharing matters.
- `DetailDrawer`: right-side desktop drawer and full-screen mobile sheet with
  focus return, Escape handling, labelled title, and scroll containment.
- `StatusIndicator`: text plus icon/shape; status must never rely on color alone.
- `EmptyState`: module-specific explanation and one useful next action.
- `ProjectNavigation`: the locked ten-module construction navigation.
- `AskOgTrigger`: persistent shell action opening the existing composer workflow.

Avoid a generic card primitive as the default module container. Tables, registers,
timelines, definition lists, and drawers should express operational information.

## Module boundaries and data gaps

| Module | Existing data | Gap to resolve without UI fabrication |
| --- | --- | --- |
| Overview | Project, tasks, materials, approvals, activities, report | Target completion and dependency-derived risk projections |
| Schedule | Task title/status/due label | Start/finish, trade, duration, dependency and milestone projection |
| Tasks | Task identity/status/assignee/due/source | Location, trade, dates, progress, linked object projection |
| Issues | Blocker-like task/activity facts | First-class issue projection and stable issue IDs |
| Materials | Inventory and approvals | Request register projection and lifecycle fields |
| Daily Logs | One daily report | Historical daily-log list, crew/weather/inspection fields |
| Photos | Report photo URLs and upload attachment IDs | Searchable photo metadata and linked-record projection |
| Documents | Upload supports PDF | Document register metadata and revision projection |
| Reports | One daily report | Historical/report list and export/share actions |
| Activity | Activity events | Stable related-object links and richer actor/category metadata |

These are projection/API follow-ups, not permission to add new V1 workflows.

## Migration order

1. Phase 1 replaces only the project shell and establishes honest placeholder
   routes for the locked navigation. Preserve all current routes and mutations.
2. Phase 2 migrates Overview using existing projections and labels unavailable
   schedule fields honestly.
3. Phase 3 establishes shared register/drawer primitives through Tasks,
   Issues, and Materials.
4. Phases 4–6 add schedule, daily-log, photo, and document projections only as
   supported by backend contracts.
5. Phase 7 moves the existing composer state machine into the global Ask OG layer.
6. Phases 8–9 migrate Activity and approvals without exposing agent internals.
7. Phases 10–12 refine field-first mobile behavior, states, and visual polish.
8. Phase 13 runs the persisted Golden Scenario across refresh and authentication.

Each phase must retain a deployable frontend, update tests before behavior, and
remove obsolete UI only after its replacement passes the phase gate.

## Phase 0 acceptance evidence

- Existing routes, shell, project provider, API client, modules, state handling,
  tests, and responsive breakpoints are documented.
- Every authenticated component has a KEEP, REWORK, or DELETE disposition.
- Backend and frontend API contracts are unchanged.
- No `.tsx`, `.ts`, or `.css` production file changed.
- Phase 1 has a bounded migration path and explicit data-gap constraints.

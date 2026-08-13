# OG Foreman UI/UX Overhaul — Codex Execution Plan

## Current phase status

- Active phase: Phase 3 — Operational Registers
- Phase 0 — Audit and Freeze: complete (2026-08-13)
- Phase 1 — New Application Shell: complete (2026-08-13)
- Phase 2 — Overview / Project Command Center: complete (2026-08-13)
- Phase 0 evidence: `docs/UI_UX_ARCHITECTURE.md`
- Phase 1 evidence: 17 frontend unit tests and 18 Playwright journeys pass;
  desktop axe checks report no WCAG A/AA violations, and mobile overflow passes.
- Phase 2 evidence: 18 frontend unit tests and 18 Playwright journeys pass;
  desktop axe checks report no WCAG A/AA violations, and mobile overflow passes.
- Product/API contracts changed through Phase 2: no
- Do not begin Phase 4 until the Phase 3 acceptance gate passes.

## Objective

Rebuild the OG Foreman frontend so it feels like a credible construction project-management product with an autonomous AI coordinator built into it.

The product must feel familiar to construction professionals:

**Schedule · Tasks · Issues · Materials · Daily Logs · Photos · Documents · Reports · Activity**

OG is not the application itself.

OG is the intelligence operating across the construction-management system.

### Core product principle

**OG maintains the construction PM. Humans manage the construction project.**

### Brand lock

Product name:

**OG Foreman**

Assistant name:

**OG**

Optional brand meaning:

**Original Guide**

Do not use `Oga Foreman`, `Oga`, or `OGA` in customer-facing UI.

---

# Non-Negotiable UX Direction

Do not build:

* a generic AI chatbot
* a hackathon dashboard
* a card-heavy SaaS template
* an analytics dashboard
* a shadcn demo with construction terminology
* static activity cards
* AI-specific navigation
* giant empty hero cards
* excessive gradients/glassmorphism

Build a familiar construction PM interface enhanced by OG.

Use:

* tables
* registers
* timelines
* filters
* status indicators
* tabs
* detail drawers
* linked records
* schedule views
* field-friendly mobile interaction

Cards should be reserved for:

* approvals
* urgent attention
* compact project KPIs
* OG responses
* important exceptions

---

# Information Architecture

Desktop project navigation:

1. Overview
2. Schedule
3. Tasks
4. Issues
5. Materials
6. Daily Logs
7. Photos
8. Documents
9. Reports
10. Activity

Persistent secondary action:

**✦ Ask OG**

Optional later:

Milestones

Do not expose:

* Agent Runs
* Workflow Nodes
* AI Insights
* Tool Calls
* Pipelines
* RAG
* Agent State

Those are implementation details.

---

# Global Application Shell

Desktop:

```text
┌──────────────────────────────────────────────────────────────┐
│ OG FOREMAN   Ridge House ▾     Search...      🔔      User │
├──────────────┬───────────────────────────────────────────────┤
│ Overview     │                                               │
│ Schedule     │                                               │
│ Tasks        │                CURRENT VIEW                   │
│ Issues       │                                               │
│ Materials    │                                               │
│ Daily Logs   │                                               │
│ Photos       │                                               │
│ Documents    │                                               │
│ Reports      │                                               │
│ Activity     │                                               │
│              │                                               │
│ ──────────── │                                               │
│ ✦ Ask OG     │                                               │
└──────────────┴───────────────────────────────────────────────┘
```

Use a consistent project shell across every module.

Records should generally open in right-side detail drawers instead of navigating users away unnecessarily.

---

# Execution Rules for Codex

Before changing code:

1. Read this entire document.
2. Inspect the existing frontend architecture.
3. Preserve working backend/API contracts.
4. Preserve the Golden Scenario workflow.
5. Do not redesign backend domain models simply to satisfy UI aesthetics.
6. Implement only the active phase.
7. Do not jump ahead.
8. Do not introduce new product scope.
9. Do not rename API/domain entities unless necessary.
10. Reuse working components only when they fit the new UX.
11. Delete obsolete UI rather than leaving parallel versions.
12. Maintain responsive behavior continuously.
13. Every phase must pass its acceptance gate before starting the next.

After every phase report:

* files changed
* components added
* components removed
* API contracts touched
* known regressions
* tests run
* screenshots/pages ready for manual review

---

# PHASE 0 — Audit and Freeze

## Goal

Understand the current frontend before replacing it.

Do not visually redesign anything yet.

### Audit

Identify:

* application shell
* routing
* navigation
* reusable primitives
* project context/provider
* API client layer
* existing card components
* activity components
* OG/site composer
* task UI
* issue UI
* material UI
* report UI
* mobile behavior

Classify each existing component:

* KEEP
* REWORK
* DELETE

### Create

`docs/UI_UX_ARCHITECTURE.md`

Document:

* existing structure
* target structure
* shared primitives
* module boundaries
* migration order

### Acceptance Gate

No product functionality changed.

We understand exactly what will be replaced.

---

# PHASE 1 — New Application Shell

## Goal

Make the application immediately feel like construction PM software.

Implement:

* OG Foreman branding
* project selector
* global search placeholder/interface
* desktop sidebar
* mobile navigation
* page header system
* project context
* persistent `Ask OG`
* responsive layout

Navigation:

```text
Overview
Schedule
Tasks
Issues
Materials
Daily Logs
Photos
Documents
Reports
Activity
```

### Remove

Any navigation centered on:

* AI
* Agents
* Insights
* Runs
* Workflows

### Acceptance Gate

Every module route opens inside one consistent project shell.

Desktop and mobile navigation work.

No old `Oga` branding remains in the visible product.

---

# PHASE 2 — Overview / Project Command Center

## Goal

Replace the current card-dashboard mentality.

Overview should answer:

1. Where is the project?
2. What happened today?
3. What needs attention?
4. What happens next?

### Top project status

Show compact metrics:

* overall progress
* target completion
* open issues
* work at risk

Maximum four KPI blocks.

### Needs Attention

Use a prioritized operational list:

```text
⚠ Electrical rough-in
  Blocking ceiling work
  Review →

⚠ Cement stock
  10 / 100 bags required
  Review →

◷ Material request
  Awaiting approval
  Review →
```

### Today

Show:

* completed work
* work in progress
* planned inspections
* deliveries
* blockers

### Two-Week Lookahead

Use a table:

```text
Activity          Start     Finish    Progress    Status
Blockwork F1      Aug 10    Aug 13    100%        Done
Electrical        Aug 13    Aug 15    20%         Blocked
Plastering F1     Aug 14    Aug 18    0%          At risk
```

### OG contextual insight

Small inline element:

**OG noticed:** Electrical rough-in is blocking two upcoming activities.

`Review impact →`

Do not create a giant AI card.

### Acceptance Gate

Overview can be understood in under 10 seconds.

A PM can identify the most important project problem without opening OG.

---

# PHASE 3 — Operational Registers

Implement these as familiar construction registers.

## 3A — Tasks

Use table/list as primary desktop presentation.

Columns:

```text
ID
Task
Location
Trade
Assignee
Start
Due
Progress
Status
```

Filters:

```text
All
My work
Due soon
Blocked
Completed
```

Click row → task detail drawer.

Drawer contains:

* title
* status
* location
* trade
* assignee
* dates
* dependencies
* blocker
* linked issue
* linked photos
* source update
* activity

---

## 3B — Issues

Build a proper Issue Log.

Columns:

```text
ID
Issue
Type
Location
Owner
Due
Status
```

Types may include:

* blocker
* schedule
* material
* quality
* safety
* general

Issue drawer:

* description
* status
* severity
* location
* responsible person
* linked task
* linked material
* linked photos
* source
* activity history

---

## 3C — Materials

Use two tabs:

**Inventory**

```text
Material
On site
Required
Unit
Needed by
Status
```

**Requests**

```text
Request
Material
Quantity
Reason
Needed by
Status
```

Statuses:

* OK
* Running low
* Requested
* Approved
* Ordered
* Delayed
* Received

### Acceptance Gate

Tasks, Issues, and Materials no longer rely on large card grids.

All three use searchable/filterable operational records.

OG-generated records appear naturally beside manually created records.

---

# PHASE 4 — Schedule

## Goal

Create a construction-native planning view.

Support:

**List | Gantt**

List columns:

```text
Activity
Trade
Start
Finish
Duration
Progress
Status
```

Support:

* milestones
* dependencies
* blockers
* at-risk state
* filtering
* search

Click activity → detail drawer.

Show downstream impact where available.

Example:

```text
Electrical rough-in

BLOCKED

Blocking:
• Ceiling installation
• Final electrical inspection

Source:
Morning site update
```

### Acceptance Gate

Schedule feels useful without OG.

OG enhances it rather than replacing it.

---

# PHASE 5 — Daily Logs

## Goal

Make Daily Logs a major first-class module.

Daily Log structure:

```text
13 August 2026

Crew
Weather

WORK COMPLETED

WORK IN PROGRESS

DELAYS / BLOCKERS

MATERIALS

DELIVERIES

INSPECTIONS

PHOTOS

TOMORROW

RISKS
```

Footer:

**Compiled by OG from 3 site updates**

Actions:

* Edit
* Share
* Export

Daily logs should look client-ready.

### Acceptance Gate

Golden Scenario mutations visibly produce a believable Daily Log.

---

# PHASE 6 — Photos and Documents

## Photos

Build a visual photo register.

Filters:

* date
* location
* task
* uploaded by

Photo metadata:

* date/time
* uploader
* location
* source site update

Linked records:

* task
* issue
* daily log

Photo detail should show its relationships.

## Documents

Simple familiar document register.

Columns:

```text
Name
Type
Revision
Uploaded by
Updated
Linked records
```

Do not build full document-management complexity.

### Acceptance Gate

A photo uploaded through OG can later be found independently and traced back to its related project records.

---

# PHASE 7 — OG Interaction Layer

## Goal

OG becomes available everywhere without taking over the application.

Desktop:

right-side drawer

Mobile:

full-screen sheet

Persistent action:

**✦ Ask OG**

### Composer

Support:

* voice
* photo
* text
* attachment

Prompt:

**What's happening on site?**

or:

**Tell OG what happened...**

### Processing language

Use:

```text
Listening to your update...
Checking the project...
Found 3 changes...
Updating the site...
Done.
```

Do not use:

```text
Running agent
Invoking tool
Processing node
Calling model
Executing workflow
```

### Response structure

Example:

```text
DONE

Blockwork
Marked ground-floor blockwork complete.

BLOCKER

Electrical
The electrician didn't attend today.

MATERIAL

Cement
10 bags reported. Tomorrow's plastering may be affected.

OG HANDLED

✓ Updated progress
✓ Created electrician follow-up
✓ Prepared material request
✓ Updated today's log

NEEDS YOU

Cement request
90 bags

[Review]
```

### Acceptance Gate

OG feels like an operational assistant acting across the PM—not a standalone chatbot.

---

# PHASE 8 — Activity Overhaul

## Goal

Replace all static activity cards.

Build one continuous chronological audit stream.

Example:

```text
ACTIVITY
13 August 2026

10:18  ● Material request approved
          90 bags of cement
          Approved by Ace
          MR-014

10:17  ◷ Approval requested
          OG prepared a material request.

10:16  ⚠ Material risk detected
          Cement: 10 bags / 100 required

10:16  ⚠ Task blocked
          Electrical rough-in
          Electrician absent

10:15  ✓ Task completed
          Ground-floor blockwork

10:15  🎙 Site update received
          Voice · 00:34 · 2 photos
```

Filters:

```text
All
OG
Tasks
Issues
Materials
Approvals
Reports
People
```

Every activity event must link to its related object where possible.

### Important

Activity displays observable actions and state transitions.

Do not expose private model reasoning or chain-of-thought.

### Acceptance Gate

A judge can watch Activity and understand the entire Golden Scenario without reading backend logs.

---

# PHASE 9 — Approval Experience

## Goal

Consequential actions must feel deliberate and trustworthy.

Approval example:

```text
MATERIAL REQUEST

Cement
90 bags

Needed for
Ground-floor plastering

Needed by
Tomorrow

Why OG prepared this
10 bags were reported on site against a requirement of 100.

[Reject]                     [Approve]
```

After resolution:

```text
APPROVED
by Ace · 10:18
```

Stale conflict:

```text
This request has already been resolved.

Refresh to see the latest status.
```

Never silently overwrite state.

### Acceptance Gate

Approve, reject, and stale-conflict scenarios from the Golden Scenario are understandable without technical knowledge.

---

# PHASE 10 — Mobile Field Experience

## Goal

Do not shrink desktop.

Design specifically for site use.

Primary mobile screen:

```text
Ridge House

Thursday, 13 August

2 things need attention

⚠ Electrical blocked
⚠ Cement running low

┌───────────────────────┐
│          🎙           │
│      Talk to OG       │
└───────────────────────┘

+ Add site photos

TODAY

✓ Blockwork complete
→ Plumbing in progress
```

Bottom navigation:

```text
Home
Tasks
OG
Photos
More
```

OG is the central mobile action.

Optimize:

* one-handed use
* large targets
* outdoor readability
* minimum typing
* rapid photo capture
* rapid voice updates

### Acceptance Gate

A foreman can submit the Golden Scenario from mobile without opening a desktop-style management screen.

---

# PHASE 11 — Loading, Empty, Error, and Success States

Every module needs deliberate states.

Examples:

### No Issues

**Nothing blocking the site.**

OG is watching for changes.

### No Daily Log

**Nothing from site yet.**

Send OG an update when work starts moving.

### No Approvals

**You're clear.**

Nothing needs your approval right now.

### Processing failure

**OG couldn't finish this update.**

Your original site update is saved.

`Try again`

Never lose user input because AI processing failed.

### Acceptance Gate

No production screen contains accidental blank states, skeleton-only states, raw exceptions, or generic “Something went wrong” messaging where more useful recovery is possible.

---

# PHASE 12 — Visual Polish

Only begin after functional UX is complete.

Review:

* typography hierarchy
* density
* spacing
* row heights
* table usability
* drawers
* statuses
* icon consistency
* responsive behavior
* empty states
* focus states
* accessibility
* dark/light behavior if supported

Motion only for:

* OG processing
* drawer transitions
* status transitions
* newly added activity
* approval completion

No decorative motion.

### Acceptance Gate

The application should look like a real construction software company could launch it publicly.

---

# PHASE 13 — Golden Scenario UI Acceptance Test

Use the existing Golden Scenario.

Submit:

**voice + site photo**

Voice:

“OG, ground-floor blockwork is finished. The electrician didn't come today. We only have about ten bags of cement left and plastering starts tomorrow.”

The UI must demonstrate:

### Site

Voice + photo update recorded.

### Tasks

Ground-floor blockwork → Completed.

Electrical follow-up → Created/updated.

### Issues

Electrical blocker → Open.

Plastering schedule risk → Visible.

### Materials

Cement → 10 bags.

Shortage → Visible.

Material request → 90 bags.

### Daily Log

Progress, blocker, material risk, and tomorrow's work appear.

### Schedule

Affected downstream activity shown as at risk where supported by backend project dependencies.

### Approval

90-bag request appears in Needs Attention.

### Activity

Entire sequence appears chronologically.

### OG

OG explains what it handled and what requires human input.

Then:

Approve request.

Verify:

* approval state updates
* workflow resumes
* Activity reflects resume/action
* no duplicate records

Refresh.

Sign out.

Sign back in.

Everything remains.

---

# Final UI Acceptance Criteria

Do not declare the overhaul complete unless all are true:

* [ ] Product says OG Foreman everywhere.
* [ ] OG is the assistant.
* [ ] Navigation uses construction PM terminology.
* [ ] Cards are no longer the default data primitive.
* [ ] Tasks use a work register.
* [ ] Issues use an issue log.
* [ ] Materials use inventory/request registers.
* [ ] Schedule has a professional planning view.
* [ ] Daily Logs are first-class.
* [ ] Photos are linked to project records.
* [ ] Activity is a chronological timeline.
* [ ] OG is available globally via drawer/sheet.
* [ ] Mobile is field-first.
* [ ] Approval UX supports stale conflicts.
* [ ] Golden Scenario is understandable entirely through the product UI.
* [ ] No customer-facing agent-engineering terminology exists.
* [ ] No old Oga/OGA branding remains.
* [ ] Existing Golden Scenario backend behavior has not regressed.

---

# Context Preservation Rule

This document is the source of truth for the overhaul.

At the beginning of every new implementation session:

1. Read this document.
2. Read the current phase status.
3. Inspect only the files relevant to the active phase.
4. Complete that phase.
5. Test it.
6. Update status.
7. Stop.

Do not reconstruct product direction from conversation history.

Do not independently redesign the product.

Do not proceed to the next phase until the active phase passes its acceptance gate.

---

# Final Product Thesis

OG Foreman should feel immediately familiar to someone who has used construction-management software.

The innovation is not a new navigation paradigm.

The innovation is that the user no longer has to manually maintain all of it.

**Site teams report reality.
OG keeps the project system current.
Managers stay in control.**

# UI and UX Specification

## Product Experience

The primary question is: **What's happening on site?** The first screen is an action-oriented command center, not a chart gallery.

## Information Architecture

```text
Project switcher
  Overview / What's happening
  Site updates
  Tasks
  Materials
  Reports
  Approvals
  Activity
  Project settings (admin)
```

## Core Screens

### Mobile Site Intake

- project name and current status;
- large voice capture control with recording, permission, retry, and cancel states;
- text fallback;
- photo/file attachment control with upload progress and validation errors;
- submitted update status;
- OG result summary with completed actions, risks, and items needing the manager;
- link to detailed activity.

### Desktop Command Center

- left project navigation;
- center OG composer and current-day activity;
- right `Needs you` panel for approvals, high-severity blockers, and clarification questions;
- compact progress/task/material context below the composer;
- no hard-coded metrics or demo-only values.

### Approval Detail

- proposed action, amount/quantity, needed-by date, reason, evidence, and source update;
- clear approve/reject actions with required confirmation for high-impact changes;
- pending, submitting, success, conflict, and already-resolved states;
- audit history and workflow run link.

### Activity Detail

- business-readable ordered steps;
- timestamps, actor, entity links, status, retry/approval waits, and safe error summaries;
- trace link visible only to authorized internal users;
- no chain-of-thought or secret-bearing payloads.

## Interaction Rules

- Voice, photo, file, and text are equal intake modes; text remains available when permissions fail.
- Buttons use familiar icons where appropriate, with accessible labels/tooltips for unfamiliar icons.
- Use tabs for major views, toggles for binary settings, menus for option sets, and explicit confirmation for destructive/high-impact actions.
- Every async action shows queued/processing/succeeded/failed/waiting states.
- Stale data is labeled and refreshable; silent optimistic mutation is not used for project truth.
- Empty states explain the next useful action through UI affordances, not a marketing paragraph.

## Responsive Requirements

- Minimum supported width: 360 px.
- The composer remains reachable without horizontal scrolling.
- Approval actions remain visible and do not wrap into ambiguous controls.
- Activity rows use stable dimensions so status labels cannot shift neighboring content.
- Desktop side panels collapse into ordered sections on mobile.
- Touch targets are at least 44 by 44 CSS pixels.

## Accessibility Requirements

- WCAG 2.2 AA for core flows.
- All controls have accessible names and keyboard focus styles.
- Recording and upload states are announced to assistive technology.
- Color is never the only status signal.
- Motion is reduced when the user requests reduced motion.
- Form validation is associated with fields and announced.
- Contrast and focus checks run in browser tests or an accessibility scanner.

## Visual Direction

Use a restrained, work-focused construction UI: high-signal status colors, dense but readable lists, and clear hierarchy. The interface should feel like a tool used repeatedly on site, not a marketing landing page or decorative analytics dashboard.

## UI Data Contract

The frontend consumes only versioned API projections. It must not import backend domain modules or duplicate business calculations. Query keys include `project_id` and invalidate after mutations.

## Required Browser States

For each core workflow test:

- initial loading;
- empty state;
- successful result;
- processing/queued;
- approval pending;
- clarification required;
- retryable error;
- terminal error;
- unauthorized/project removed;
- stale data after another actor changes state.

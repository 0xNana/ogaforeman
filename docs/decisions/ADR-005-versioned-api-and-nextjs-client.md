# ADR-005: Replace the Static Dashboard with a Versioned API and Next.js Client

## Status

Accepted

## Context

The current static HTML contains hard-coded metrics and inline scripts. A production product needs authenticated project-scoped reads, mutations, async status, responsive mobile intake, and testable UI state.

## Decision

Expose a versioned FastAPI `/api/v1` contract and build a Next.js TypeScript frontend that consumes typed projections. The frontend does not duplicate domain calculations or import backend modules.

## Consequences

- API contract tests and browser E2E tests become release requirements.
- Loading, error, stale, approval, and clarification states are part of each screen's design.
- The static page can remain as a temporary prototype adapter only until the command center slice is complete.

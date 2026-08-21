# Deterministic Demo and Rehearsal

## Product story

The marketing site links to `/demo` for the public deterministic showcase. That
route renders local product fixtures and the OG processing preview only; it
does not attach Firebase tokens or call the project API. Authenticated project
routes never fall back to those fixtures.

The public demo remains:

> First-floor blockwork is done. Electrician did not come. We have ten bags of
> cement left. Plastering is tomorrow.

The complete product path must persist the source update, complete only the
matched task, record the blocker and downstream risk, prepare a material request
and approval, update the daily report/activity, resume after a human decision,
and process a later delivery delay without duplicate mutations.

## Checked-in rehearsal

Run three isolated passes:

```bash
.venv/bin/python scripts/run_demo.py \
  --mode dry-run \
  --runs 3 \
  --output artifacts/reliability/demo-dry-run.json
```

`main.py --demo` runs the same default rehearsal. It covers:

- two reset/seed cycles per pass;
- typed task completion and material-shortage request;
- source-linked report projection rebuild;
- one approval, one rejection, then one approval;
- duplicate continuation delivery suppression;
- a new resume-service instance after the decision event;
- rejection closure through the current continuation helper;
- simulated delivery delay and duplicate delay suppression.

The artifact intentionally contains `release_blocked: true`. Approval continuation
and the canonical mixed API/ADK/Firestore workflow are covered by automated local
evidence, but live Gemini, browser, and staging outcomes remain unproven. It is
release evidence for the controls it names, not a production claim.

## Firestore emulator rehearsal

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
.venv/bin/python scripts/run_demo.py \
  --mode emulator \
  --runs 3 \
  --output artifacts/reliability/demo-emulator.json
```

Emulator mode calls the guarded project-only reset twice and uses the Firestore
repository adapter. It must never point at production.

## Staging demo gate

Before public demonstration or release, perform three staging runs through the
real UI/API/worker path, including:

- microphone denial and text fallback;
- verified attachment upload;
- approval and rejection;
- worker restart while waiting;
- duplicate site update and decision delivery;
- delayed supplier event;
- second-project access denial;
- activity and trace correlation.

Record Cloud Run revisions, event/run IDs, trace links, and reset output. No such
staging evidence exists in this workspace yet.

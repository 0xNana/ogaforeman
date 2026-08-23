# All Things Agentic Submission Checklist

Status date: **August 23, 2026**
Submission deadline: **August 31, 2026 at 5:00 PM Pacific Time**

This is a release gate, not a list of aspirations. Check an item only when the
current submitted commit and deployed revision have direct evidence.

> Prize clarification: the official Taskmaster category prize is **$20,000**,
> not $30,000. The Individual/Hobbyist prize is $10,000, but a project can win
> at most one prize; the two cannot be stacked. The Grand Prize is $50,000.

## Stage One: mandatory pass/fail

- [ ] Devpost project is registered and every eligible team member is listed.
- [ ] Entrant eligibility, ownership, employer consent, and conflict rules have
  been reviewed by the entrant.
- [ ] Entrant confirms the submitted work was created during August 3-31, 2026
  and discloses every pre-existing template, asset, library, or code component.
- [ ] Exactly one category is selected: **Taskmaster**.
- [x] Application code uses Gemini 3.6 Flash, satisfying Gemini 3.5 or newer.
- [x] Application code uses Google ADK agents and `Runner` execution.
- [x] Architecture uses Google Cloud infrastructure, including Cloud Run,
  Firestore, Cloud Storage, and Pub/Sub.
- [ ] Current submitted commit is deployed with `USE_FAKE_MODEL=false`,
  `DEMO_MODE=false`, Vertex AI model access, and durable Vertex AI ADK sessions.
- [ ] Public hosted URL works in a signed-out browser and the judge account can
  complete the authenticated workflow for free.
- [ ] Private judge credentials and the synthetic project ID are present in the
  Devpost testing instructions, not in the repository.
- [x] English is supported by the application and submission documents.
- [x] Repository URL is documented as
  https://github.com/0xNana/ogaforeman.
- [ ] Repository is publicly accessible, or Devpost and Google testing accounts
  have access if it remains private.
- [x] README contains clone, pinned install, configuration, run, test, and cloud
  deployment instructions.
- [x] Text description covers features, functionality, technologies, data
  sources, challenges, findings, and learnings.
- [x] Architecture diagram clearly connects the frontend, Gemini, Google ADK,
  backend, event transport, persistence, approvals, and observability.
- [ ] Demo video is uploaded publicly, not unlisted, to YouTube or Vimeo.
- [ ] Demo video URL is in Devpost and `DEVPOST.md`.
- [ ] Demo video is no longer than four minutes and is in English or has English
  subtitles.
- [ ] First four minutes show the problem, value, application in action, and
  visible Google Cloud backend proof.
- [ ] Video contains an unedited live proof-of-action segment using the actual
  submitted cloud deployment.
- [ ] Hosted app, repository, credentials, media, and dependencies will remain
  available without charge or restriction through October 1, 2026.
- [ ] Devpost preview is reviewed after saving; every URL opens in a signed-out
  browser and no placeholder or `SUBMISSION BLOCKER` remains.

## Taskmaster fit: Innovation and Operational Utility, 40%

- [ ] The Devpost story explains the entrant's truthful, personal "Bring Your
  Own Friction" connection rather than only a broad industry problem.
- [ ] Video starts with the messy multi-step chore, not a technology list.
- [ ] One live input visibly causes multiple coordinated operational actions.
- [ ] The agent does more than draft text: it changes tasks, blockers, material
  state, follow-up, reports, approvals, notifications, or audit state.
- [ ] Safe steps execute autonomously without repeated confirmation.
- [ ] The only human interruption shown is a clear consequential authority
  boundary, followed by continuation of the original run.
- [ ] The video makes the time or coordination saved concrete.
- [ ] A messy input includes a useful twist, such as multimodal evidence,
  ambiguous entity reference, negation, duplicate delivery, or delayed event.
- [ ] The output is correct for the seeded ledger and task graph; no narrated
  result relies on hand-edited UI state.

## Architectural Discipline, 30%

- [ ] Video or submission explains the authority split in one sentence:
  Gemini reasons/extracts, ADK coordinates, typed tools mutate, Firestore is
  truth.
- [ ] Current deployment proves separate web, API, and private worker Cloud Run
  revisions with least-privilege service identities.
- [ ] Pub/Sub delivery proves a stable event ID, persisted claim, retry policy,
  and duplicate-safe result.
- [ ] Every demonstrated mutation has a matching atomic `ActivityEvent`.
- [ ] API, repository, and tool authorization checks are covered by current
  passing tests and an authenticated staging smoke.
- [ ] Approval pause and continuation survive process replacement without
  repeating earlier mutations.
- [x] The experimental ADK resumability dependency is pinned to the locally
  tested version; an upgrade is blocked on rerunning both restart gates.
- [ ] Model output cannot directly write Firestore or bypass a typed tool.
- [x] Taskmaster-critical source paths use explicit ADK graphs: Daily Site
  Update has context, interpretation, canonical resolution, parallel
  progress/blocker/material analysis, merge, policy, tools, and interruption;
  delivery delay has impact, risk, follow-up, and notification nodes; project
  conversation has conditional reason/tool branches.
- [x] Staging and production explicitly select the single Google Chat external
  provider and reject the development/test logging provider. `DELIVERY_DELAYED`
  enters through authenticated operator intake and cannot use the logging path
  in competition evidence.
- [ ] Live Google Chat gate records one real external message plus its persisted
  outbox/provider outcome without exposing the webhook URL.
- [ ] Final owner-run artifacts prove those nodes executed, delivery outcomes
  occurred once, and a live project answer came from Gemini over authorized
  context rather than a deterministic response template.
- [ ] Private media is verified from Cloud Storage; the browser preview or
  transcript is not processing truth.
- [ ] Logs and traces correlate request, event, run, workflow, agent, tool, and
  prompt version without secrets or chain-of-thought.
- [ ] Architecture diagram matches the deployed runtime; target-only components
  are not presented as already proven.

## Demo and Production Readiness, 30%

- [ ] The current commit passes backend lint, formatting, type checking, full
  tests, production-readiness tests, deterministic evals, and docs checks.
- [ ] The current commit passes frontend lint, type checking, unit tests, build,
  and browser E2E on desktop and mobile.
- [ ] Live core Gemini evaluation meets its release threshold on the submitted
  prompt/model/version. The billed Vertex Golden artifact must pass all eight
  operational checks with 100% canonical resolution; the checked-in 3/8 result
  and the separate seven-case project-import result are not accepted as a pass.
- [ ] The Golden artifact identifies the billed Vertex project/location, matches
  the submitted commit, and reports `source_tree_dirty: false`.
- [ ] Live voice and photo processing are proven on the deployed worker.
- [ ] Authenticated staging smoke recognizes `waiting_for_approval`, resolves
  the approval, and verifies the resumed terminal state.
- [ ] `.venv/bin/python scripts/run_adk_resume_gate.py` passes without skips
  against configured Firestore and Storage emulators.
- [ ] The Golden run survives a real worker revision/process restart while
  paused; the original ADK app/session/invocation/workflow IDs remain unchanged,
  the approved-request continuation occurs once, and the original run/site update
  terminate.
- [ ] Cloud Run readiness confirms configuration, external notification,
  Firestore, and Storage access.
- [ ] `/api/v1/version` reports `git_sha`, `build_timestamp`, `app_version`, and
  `environment` for the exact submitted clean commit and latest ready API Cloud
  Run revision.
- [ ] Current deployment artifact records `repo_git_sha`, `build_timestamp`,
  `deployment_timestamp`, the safe version response, image digests, API/worker/
  web revisions, region, per-revision timestamps, and public URLs.
- [ ] `staging-deployment-current.json` reports `passed: true`; all three
  revisions contain the same stamped SHA/build time/version and resolved
  `sha256` digests.
- [ ] Cloud Logging and Cloud Trace show the same demonstrated run end to end.
- [ ] Alert delivery, dead-letter handling, Scheduler delivery, backup
  visibility, isolated restore, and rollback have current evidence.
- [ ] Rehearsal succeeds twice from a clean synthetic reset, including refresh
  and duplicate delivery, before recording.
- [ ] Video text is readable on a laptop, narration is clear, notifications are
  disabled, and no secrets, PII, private media, or unrelated customer data show.
- [ ] Final video lands between 3:30 and 3:55 and keeps the complete proof inside
  the first four minutes.

## Required URLs and private fields

| Field | Required value | Status |
| --- | --- | --- |
| Hosted app | https://ogaforeman-cloud-2026.web.app/ | Verify current revision |
| Repository | https://github.com/0xNana/ogaforeman | Verify judge access |
| Architecture | `docs/submission/architecture-diagram.svg` | Ready |
| Agent inventory | `docs/submission/AGENT_INVENTORY.md` | Ready |
| Testing instructions | `docs/submission/TESTING.md` | Credentials pending |
| Public video | YouTube or Vimeo URL | **Blocked** |
| Judge account | Dedicated synthetic-data user | **Blocked** |
| Judge project | Seeded project name and ID | **Blocked** |
| Support contact | Monitored email in Devpost | **Blocked** |
| Personal BYOF story | Truthful entrant-written paragraph | **Blocked** |
| Pre-existing work disclosure | Entrant-reviewed statement | **Blocked** |

## Evidence record for the final commit

Fill this only after the final deployment:

```text
Git commit SHA:
Repository visibility checked at:
Deployment timestamp (UTC):
Google Cloud project:
Google Cloud region:
Web Cloud Run revision / image digest:
API Cloud Run revision / image digest:
Worker Cloud Run revision / image digest:
Gemini model and prompt version:
ADK session backend / Agent Engine ID (redacted as needed):
Live workflow event ID:
Live workflow run ID:
Approval ID:
Cloud Logging query or saved view:
Cloud Trace ID:
Firestore evidence locations:
Backend test artifact:
Frontend test artifact:
Live eval artifact:
Backup / restore / rollback evidence:
Public video URL:
Final Devpost URL:
```

## Optional bonus, only after core gates pass

- [ ] Public build article, podcast, or video states that it was created for
  entry into the All Things Agentic Hackathon; add its URL to Devpost. Maximum
  bonus: 0.2.
- [ ] Public X, LinkedIn, Instagram, or Facebook post includes
  `#AllThingsAgenticHackathon`; add its URL to Devpost. Maximum bonus: 0.2.
- [ ] Any additional Google AI model is genuinely integrated, documented, and
  demonstrated. Bonus: 0.2 per model, maximum 0.6. Do not add a model merely to
  decorate the stack.

Official source of truth:
https://allthingsagentichackathon.devpost.com/rules

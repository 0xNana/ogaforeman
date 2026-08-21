# OG Foreman — Conversational UX Correction Command

## Objective

Fix the current conversational experience so OG behaves like a useful project coordinator, not an exposed intent classifier.

Current bad behavior includes responses such as:

```text
YOU
do we have our project set?

PROJECT
I don't see any urgent project changes right now.
```

and:

```text
YOU
how do i get started

ADVICE
I don't have enough recorded project context to recommend a change yet.
```

These responses are incorrect at the product level.

The router may be functioning technically, but user-facing conversation is not.

Your task is to correct the conversational architecture and UX without changing or regressing the locked Golden Scenario.

---

# NON-NEGOTIABLE PRODUCT RULE

The user talks to **OG**.

The user must never see internal routing concepts such as:

* PROJECT
* ADVICE
* CASUAL
* MUTATION
* SITE_UPDATE
* PROJECT_QUERY
* HELP
* intent names
* confidence scores
* router reason codes

Those may remain in structured logs, traces, and developer diagnostics only.

The conversation UI must display only:

```text
YOU
...

OG
...
```

Structured labels are allowed only when they represent actual project objects/actions, for example:

```text
TASK UPDATED
MATERIAL RISK
PROPOSED CHANGE
NEEDS APPROVAL
ISSUE RESOLVED
```

Do not expose classifier names as response authors or headings.

---

# P0 — ADD PRODUCT HELP / ONBOARDING INTENT

Extend the conversational intent taxonomy.

Current taxonomy should become approximately:

```text
CASUAL
HELP
PROJECT_QUERY
PROJECT_ADVICE
PROJECT_MUTATION
SITE_UPDATE
CLARIFICATION_RESPONSE
CONFIRMATION_RESPONSE
UNKNOWN
```

`HELP` covers questions about using OG Foreman itself.

Examples:

```text
"how do i get started?"
"what can you do?"
"how do I add a site update?"
"can I send voice notes?"
"can you read photos?"
"how do materials work?"
"how do I create a task?"
```

These questions must NOT require meaningful project state.

They should be answered from product knowledge.

---

# P1 — ADD PRODUCT KNOWLEDGE

OG needs access to three distinct context sources:

```text
1. PRODUCT KNOWLEDGE
2. PROJECT STATE
3. CONVERSATION CONTEXT
```

These sources must not be conflated.

## PRODUCT KNOWLEDGE

Use for:

```text
"how do I get started?"
"what can you do?"
"how do I upload photos?"
```

This knowledge should describe the actual implemented product only.

Do not promise unsupported functionality.

A minimal structured ProductKnowledgeService or equivalent is preferred over embedding large amounts of product documentation directly into every prompt.

It should know at minimum:

* OG supports text input
* OG supports voice site updates if currently implemented
* OG supports photo/site media if currently implemented
* OG can understand site updates
* OG can update tasks/materials/issues through supported flows
* OG can detect blockers/material risks
* OG can prepare actions
* important actions can require approval
* project data persists
* user can review Tasks, Issues, Materials, Daily Logs, Activity, etc. if those screens exist

Product knowledge must reflect current implementation, not roadmap ideas.

---

# P2 — PROJECT SETUP AWARENESS

Implement a deterministic project setup/status check.

Do not answer:

```text
"do we have our project set?"
```

with generic issue/risk status.

That question is about project readiness/setup.

Add a project setup projection/service such as:

```text
ProjectSetupStatus
├── project_exists
├── has_members
├── has_tasks
├── has_schedule
├── has_materials
├── has_site_updates
├── has_daily_logs
├── has_recent_activity
└── readiness_state
```

Possible readiness states:

```text
EMPTY
STARTED
ACTIVE
```

Do not over-engineer readiness.

Use deterministic persisted state.

## Example behavior

If the project exists but has little data:

```text
YOU
do we have our project set?

OG
Ridge House is created, but it's still mostly empty. The fastest way to get it going is to tell me what's happening on site today — work underway, materials on hand, blockers, or what's planned next.
```

If sufficiently populated:

```text
OG
Yes. Ridge House is set up and active. You have 8 tasks, 2 open issues, materials being tracked, and today's site activity is already coming in.
```

If no active project exists:

```text
OG
Not yet. Create or open a project first, then tell me what's happening on site and I'll start organizing it.
```

Do not invent counts.

Use actual state.

---

# P3 — ZERO-CONTEXT ONBOARDING RESPONSES

OG must remain useful when project context is empty.

Current response:

```text
I don't have enough recorded project context to recommend a change yet.
```

is unacceptable for:

```text
"how do i get started?"
```

Expected behavior:

```text
OG
Start by telling me what's happening on site. You can type an update, record a voice note, or add photos.

For example:
"Ground-floor blockwork started today. We have 60 bags of cement and the electrician comes tomorrow."

I'll turn that into project updates, tasks, materials, issues, and your daily log where appropriate.
```

Do not require project-state retrieval for product-help questions.

---

# P4 — SEPARATE PROJECT QUERY FROM PROJECT ADVICE

Ensure the router and handlers understand:

```text
"what's up?"
→ PROJECT_QUERY when project context exists

"what happened today?"
→ PROJECT_QUERY

"do we have our project set?"
→ PROJECT_QUERY / CHECK_PROJECT_SETUP

"wdyt about plastering tomorrow?"
→ PROJECT_ADVICE

"should we move plastering?"
→ PROJECT_ADVICE unless user explicitly commands a mutation
```

A PROJECT_QUERY retrieves facts.

A PROJECT_ADVICE request reasons over facts.

Neither should mutate state unless the user subsequently requests an action.

---

# P5 — RESPONSE AUTHOR NORMALIZATION

Inspect the conversation response schema/API/frontend.

If responses currently include fields such as:

```text
role = PROJECT
role = ADVICE
role = CASUAL
```

or equivalent, refactor them.

The user-facing role must resolve to:

```text
USER
OG
SYSTEM
```

`SYSTEM` should be used sparingly for technical/error states only.

Intent/category remains metadata, for example:

```json
{
  "role": "assistant",
  "assistant_name": "OG",
  "intent": "PROJECT_QUERY"
}
```

Frontend renders:

```text
OG
```

not:

```text
PROJECT
```

---

# P6 — HIDE INTERNAL INTENT METADATA IN THE UI

Search the frontend for any direct rendering of:

```text
intent
category
response_type
handler
route
decision
```

Remove it from user-facing author labels/badges unless it represents a meaningful project action.

Allowed:

```text
NEEDS APPROVAL
TASK UPDATED
ISSUE CREATED
```

Not allowed:

```text
PROJECT
ADVICE
HELP
MUTATION
```

---

# P7 — CONVERSATIONAL FALLBACKS

Improve `UNKNOWN` and low-context responses.

Bad:

```text
I don't have enough project context.
```

Prefer context-sensitive recovery.

Examples:

## Unknown but likely product question

```text
I'm not sure what you mean yet. If you're getting started, tell me what's happening on site or ask me about tasks, materials, issues, or today's work.
```

## Project question but project empty

```text
There isn't much project history yet. Send me the first site update and I'll start building the picture.
```

## Ambiguous mutation

```text
Which plastering task do you mean — ground floor or first floor?
```

Do not use one generic fallback for all cases.

---

# P8 — NATURAL OG PERSONA

OG should sound like a practical coordinator.

Preferred style:

* concise
* direct
* useful
* project-aware
* conversational
* no unnecessary AI language

Examples:

```text
"Yep. The project is active."
"Not yet — we're still missing the initial schedule."
"Electrical is still the main blocker."
"You're clear right now. Nothing needs approval."
"Start by telling me what happened on site today."
```

Avoid:

```text
"Based on the available context..."
"My analysis indicates..."
"I have insufficient contextual information..."
"As an AI..."
```

---

# P9 — REQUIRED TEST CASES

Add runtime/API tests for at least these:

## Product help

```text
"how do i get started?"
```

Expected:

* HELP
* product knowledge response
* no project mutation
* no requirement for populated project context
* visible author = OG

---

## Capability question

```text
"what can you do?"
```

Expected:

* HELP
* accurately lists implemented core capabilities
* no unsupported roadmap promises

---

## Empty project setup

```text
"do we have our project set?"
```

with empty/minimal project.

Expected:

* actual readiness response
* useful next step
* no fake urgent-project summary

---

## Active project setup

Same question with seeded active project.

Expected:

* real counts/state where useful
* concise readiness answer

---

## Project query

```text
"what's up?"
```

Expected:

* summary from live state
* no mutation

---

## Advice

```text
"wdyt about plastering tomorrow?"
```

Expected:

* grounded advice
* no mutation

---

## Mutation regression

```text
"we have 35 bags of cement now"
```

Expected:

* still routes to the existing typed mutation path
* persists
* ActivityEvent created

---

## Site update regression

```text
"blockwork is done, electrician didn't show and cement is low"
```

Expected:

* still routes into the existing Golden site-update workflow

---

# P10 — GOLDEN SCENARIO PROTECTION

After implementing these UX changes:

Run the full locked Golden Scenario regression suite.

Required result:

```text
GOLDEN SCENARIO: PASS
```

Do not change:

* multimodal site interpretation semantics
* task mutation semantics
* material-risk semantics
* approval pause/resume
* ActivityEvent behavior
* persistence
* concurrency protections

This task is a conversational UX correction, not a Golden Core rewrite.

---

# P11 — MANUAL ACCEPTANCE FLOW

Run this manually in the actual OG drawer/composer:

```text
YOU
how do i get started?

OG
Start by telling me what's happening on site...
```

Then:

```text
YOU
do we have our project set?

OG
<real setup/readiness response>
```

Then:

```text
YOU
what's up?

OG
<real project summary>
```

Then:

```text
YOU
wdyt about tomorrow?

OG
<grounded project advice>
```

Then:

```text
YOU
we have 35 bags of cement now

OG
Done. Cement is now recorded at 35 bags.
```

Verify Materials reflects 35.

Verify Activity records the mutation.

No second input field.

No visible intent labels.

No generic "not enough project context" response where product knowledge is sufficient.

---

# FINAL ACCEPTANCE CRITERIA

Do not declare complete unless:

* [ ] `HELP` exists and is routed correctly.
* [ ] Product-help questions work without project context.
* [ ] Project setup/readiness is derived from actual persisted state.
* [ ] `do we have our project set?` returns a readiness answer.
* [ ] `how do i get started?` returns useful onboarding.
* [ ] Internal intent names are invisible to users.
* [ ] Assistant messages are visibly authored by `OG`.
* [ ] Project queries remain grounded in real state.
* [ ] Advice remains non-mutating.
* [ ] Existing project mutations still work.
* [ ] Site updates still route into the Golden workflow.
* [ ] One universal composer remains.
* [ ] Golden Scenario regression suite passes.
* [ ] No unsupported product capabilities are claimed.

---

# IMPLEMENTATION DISCIPLINE

Execute this correction as one focused integration task.

Do not add:

* new dashboard modules
* new construction workflows
* new specialist agents
* unrelated visual redesign
* new input/composer surfaces

The objective is simple:

> **OG should feel like someone who knows both the product and the project.**

The user should never need to understand the router behind it.

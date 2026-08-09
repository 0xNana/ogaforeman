# Oga Foreman — High-Level Hackathon Implementation Plan

The product should be built around one promise:

> **Tell Oga what happened on site. Oga handles the follow-through.**

We are **not** building another construction project-management dashboard. We are building an **event-driven AI foreman** that converts messy field updates—voice, text, photos, schedules, deliveries—into structured project state and completed operational workflows.

Google ADK 2.0 is a strong foundation because its Workflow Runtime already provides graph execution, routing, fan-out/fan-in, retries, state, loops, nested workflows and human-in-the-loop pauses. We should use those capabilities instead of recreating a workflow engine ourselves. ([GitHub][1])

---

# 1. Product North Star

### Input

A person on site should be able to do this:

> 🎙 “First-floor blockwork is done. Electrician didn't show. We have maybe ten bags of cement left. Plastering is tomorrow.”

Maybe attach two photos.

### Oga Foreman transforms that into

```text
SITE UPDATE
     ↓
Understand what happened
     ↓
Retrieve current project state
     ↓
Detect:
├── completed work
├── blockers
├── material risks
├── schedule impact
└── things requiring attention
     ↓
Take permitted actions
├── update progress
├── create tasks
├── create material request
├── flag delay
├── update report
└── request approval
     ↓
Monitor what happens next
     ↓
Resume workflow automatically
```

The killer feature is **follow-through**.

Not transcription.

Not summarization.

Not chat.

---

# 2. Hackathon Scope Lock

Codex should treat these as the **only four core workflows for V1**.

| Workflow              | Trigger                    | Autonomous outcome                                     |
| --------------------- | -------------------------- | ------------------------------------------------------ |
| **Daily Site Update** | Voice/text/photos          | Update progress, extract issues, generate daily report |
| **Material Shortage** | Site update / stock event  | Create requirement → request approval → track status   |
| **Blocker & Delay**   | Site update / overdue task | Detect dependency → determine impact → assign/escalate |
| **Daily Brief**       | Scheduled event            | Summarize progress, blockers, risks and approvals      |

Everything else is secondary.

Do **not** build payroll, accounting, tendering, full BIM, procurement marketplaces, contractor CRM, invoicing, estimating, drawing interpretation, structural engineering, or a giant Procore replacement.

---

# 3. Product Architecture

```text
                         OGA FOREMAN
                              │
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
    Voice/Text              Photos              Events
       │                      │              deadlines/deliveries
       └──────────────────────┼──────────────────────┘
                              ▼
                       Intake Gateway
                              │
                              ▼
                    Oga ADK Coordinator
                              │
                     retrieve project state
                              │
                              ▼
                       ADK Workflow
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
        Progress          Materials          Blockers
        workflow          workflow           workflow
           │                  │                  │
           └──────────────────┼──────────────────┘
                              ▼
                        Decision Layer
                         /           \
                 autonomous       approval
                    action          needed
                       \             /
                        └─────┬─────┘
                              ▼
                         Tool Layer
              project/task/material/report tools
                              │
                              ▼
                     Persistent Project State
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
             Activity Log              Oga UI
```

The important architectural rule:

> **Gemini reasons. Workflows coordinate. Tools perform actions. The database remains the source of truth.**

Never let the LLM itself become the project database.

---

# 4. Recommended Stack

### Agent layer

```text
Python
Google ADK 2.x
Gemini
Pydantic structured schemas
```

ADK's `Agent` handles reasoning while `Workflow` should control important multi-stage business processes. ADK 2.0 explicitly separates those concepts and provides structured task delegation for agent-to-agent work. ([GitHub][2])

### Cloud

```text
Cloud Run
Pub/Sub
Eventarc
Firestore
Cloud Storage
Cloud Logging
Cloud Trace
```

Agents CLI already supports Cloud Run deployment and infrastructure/observability workflows, so Codex should prefer Google's provided lifecycle tooling where it saves time. ([Google GitHub][3])

### Web application

```text
Next.js
TypeScript
Tailwind CSS
shadcn/ui or equivalent primitives
React Query / server actions
PWA-friendly responsive design
```

### Do not add

```text
Stripe
Subscriptions
Credits
Billing
Paid tiers
Feature gating
```

**Oga Foreman is free.**

---

# 5. Core Domain Model

Keep the schema small enough to finish.

```text
User
Project
ProjectMember

Project
├── Tasks
├── SiteUpdates
├── Issues
├── Materials
├── MaterialRequests
├── DailyReports
├── Approvals
├── Attachments
└── ActivityEvents
```

### Essential entities

**Project**

```text
id
name
location
description
start_date
target_end_date
status
created_by
```

**Task**

```text
id
project_id
title
description
status
priority
assigned_to
planned_start
planned_end
actual_completion
dependencies[]
source
```

**SiteUpdate**

```text
id
project_id
submitted_by
input_type
raw_text
transcript
attachments[]
created_at
processing_status
```

**Issue**

```text
id
project_id
type
severity
description
task_ids[]
status
detected_by
```

**Material**

```text
id
project_id
name
unit
estimated_available_quantity
minimum_required_quantity
```

**MaterialRequest**

```text
id
material_id
quantity
needed_by
reason
status
approval_id
```

**Approval**

```text
id
project_id
action_type
proposed_action
reason
status
requested_at
resolved_at
resolved_by
```

**AgentRun**

```text
id
project_id
trigger
workflow
status
started_at
completed_at
trace_id
```

**ActivityEvent**

This becomes extremely important for the demo.

```text
id
project_id
actor
action
entity_type
entity_id
summary
metadata
created_at
```

---

# 6. The Oga Event Contract

Do this early.

Every input should eventually become a normalized `ProjectEvent`.

```python
ProjectEvent:
    event_id
    project_id
    source
    event_type
    timestamp
    text
    attachments
    actor
    extracted_facts
    confidence
```

Possible types:

```text
SITE_UPDATE_RECEIVED
TASK_COMPLETED
TASK_BLOCKED
MATERIAL_LOW
MATERIAL_REQUESTED
DELIVERY_DELAYED
APPROVAL_GRANTED
APPROVAL_REJECTED
TASK_OVERDUE
DAILY_BRIEF_REQUESTED
```

This abstraction is what eventually allows Oga to react to WhatsApp, IoT, supplier APIs, schedules, emails, and other systems without rewriting the intelligence layer.

---

# 7. Oga Agent Architecture

Do **not** start with ten agents.

Start with:

```text
OgaCoordinator
     │
     ├── SiteInterpreter
     ├── ProjectPlanner
     ├── MaterialsSpecialist
     └── Reporter
```

### OgaCoordinator

Owns orchestration.

It determines:

```text
What happened?
What project state is relevant?
What workflows should start?
What can happen automatically?
What needs approval?
What should the user know?
```

### SiteInterpreter

Turns messy field communication into structured facts.

Input:

```text
voice + text + images
```

Output:

```json
{
  "completed_work": [],
  "progress_updates": [],
  "blockers": [],
  "material_updates": [],
  "risks": [],
  "observations": []
}
```

### ProjectPlanner

Reasons about:

```text
task dependencies
schedule impact
blocked work
next tasks
```

### MaterialsSpecialist

Handles:

```text
material levels
requirements
shortages
requests
delivery dates
```

### Reporter

Produces:

```text
daily report
manager brief
site summary
status explanations
```

Specialists should return structured outputs. They should **not directly mutate project state** unless explicitly granted a tool designed for that action.

---

# 8. Tool Layer

This is where the agent becomes operational.

Codex should build boring, deterministic functions like:

```text
get_project()
get_project_state()

create_task()
update_task()
complete_task()

create_issue()
resolve_issue()

update_material_quantity()
create_material_request()

create_approval()
resolve_approval()

create_daily_report()

record_activity()
notify_user()
```

Tools return typed results.

Every mutation must produce an `ActivityEvent`.

That gives us this:

```text
09:41 Oga analyzed site update

09:41 Blockwork task marked completed

09:41 Electrical work flagged as blocked

09:42 Cement shortage detected

09:42 Material request MR-104 created

09:42 Manager approval requested

09:43 Daily report updated
```

That timeline will sell the autonomy better than almost anything else in the UI.

---

# 9. Workflow #1 — Daily Site Update

Build this **before anything else**.

```text
Receive update
      ↓
store original media
      ↓
transcribe / interpret
      ↓
load project state
      ↓
extract structured facts
      ↓
validate facts
      ↓
fan out
 ┌────┼──────────┐
 ↓    ↓          ↓
progress blocker materials
 ↓    ↓          ↓
 └────┼──────────┘
      ↓
evaluate schedule impact
      ↓
determine approvals
      ↓
perform safe actions
      ↓
update daily report
      ↓
record activity
      ↓
respond to user
```

ADK 2.0's workflow fan-out/fan-in and routing capabilities are perfect for this pattern. ([GitHub][1])

### Definition of done

User submits:

> “Blockwork is done. Electrician didn't come. Only ten bags of cement left.”

Without manually directing Oga further:

* Blockwork becomes completed.
* Electrical issue becomes a blocker.
* Cement risk becomes a material request.
* Tomorrow's affected task is identified.
* Daily report changes.
* Approval appears.
* Activity timeline records everything.

If that works beautifully, **we already have a hackathon-worthy product.**

---

# 10. Workflow #2 — Materials

```text
MATERIAL_LOW
     ↓
retrieve upcoming tasks
     ↓
determine requirement
     ↓
calculate shortage
     ↓
create proposed request
     ↓
approval needed?
     ├── yes → PAUSE
     │          ↓
     │       manager approves
     │          ↓
     └──────── resume
                ↓
            submit request
                ↓
             monitor
```

Use ADK's human-in-the-loop/resumption capability rather than inventing your own fake approval mechanism. ([GitHub][1])

For the hackathon, actual supplier procurement can be simulated with a deterministic supplier tool.

---

# 11. Workflow #3 — Blockers

This is where Oga starts feeling intelligent.

```text
Blocker detected
      ↓
Identify affected task
      ↓
Find dependent tasks
      ↓
Calculate schedule impact
      ↓
Can Oga resolve automatically?
      │
 ┌────┴────┐
 yes       no
 ↓          ↓
task      escalate
action    manager
 ↓          ↓
 └────┬─────┘
      ↓
monitor resolution
```

Example:

```text
Electrician absent
        ↓
Electrical rough-in blocked
        ↓
Ceiling work depends on electrical rough-in
        ↓
Ceiling work now at risk
        ↓
Notify responsible person
        ↓
Manager sees projected impact
```

---

# 12. Workflow #4 — Daily Brief

This proves **event-driven autonomy**.

Every morning or evening:

```text
scheduler
   ↓
DAILY_BRIEF_REQUESTED
   ↓
Oga retrieves:
├── today's progress
├── overdue tasks
├── active blockers
├── material risks
├── pending approvals
└── upcoming work
   ↓
manager brief
```

Example:

> **Morning, boss.** Blockwork finished yesterday. Electrical rough-in remains blocked and could delay ceiling installation by one day. Cement stock is below the requirement for tomorrow's plastering. One purchase request needs your approval.

No prompt required.

That directly reinforces the Taskmaster story.

---

# 13. UI/UX Direction — Reclip Inspired, Not Copied

Reclip's current experience works because it keeps the proposition extremely simple, leads with a bold outcome, groups capabilities into obvious tool cards and repeatedly emphasizes removing repetitive work. ([Reclip][4])

We steal **that philosophy**, not its brand.

## Landing page

```text
------------------------------------------------------

                 OGA FOREMAN

          Your site doesn't need
             another dashboard.

      Tell Oga what happened.
       Keep the site moving.

 [ Start a project — Free ] [ Watch demo ]

 No card. No credits. No subscriptions.

------------------------------------------------------

Everything Oga handles

 [ Daily Reports ] [ Materials ]
 [ Site Blockers ] [ Progress ]
 [ Photos ]        [ Daily Briefs ]

------------------------------------------------------

BEFORE OGA                   WITH OGA

Voice notes                  Structured updates
WhatsApp chaos       →       Actionable tasks
Missed materials             Early warnings
Manual reports               Reports automatically
Chasing workers              Follow-ups tracked

------------------------------------------------------
```

Replace Reclip's pricing section entirely with:

> **Free means free.**
> Oga Foreman is available at no cost during its public beta. No credits, no card, no locked workflows.

Reclip currently uses a broad feature grid and a strong “before vs after” section; those are the two patterns most worth borrowing. ([Reclip][4])

---

# 14. The Actual App UX

The app should **not** open on charts.

Open on:

# **What's happening on site?**

```text
┌───────────────────────────────────────────────────────┐
│ OGA FOREMAN                           🔔    Ace       │
├────────────┬───────────────────────────┬──────────────┤
│ PROJECT    │                           │ NEEDS YOU    │
│            │ Good morning, boss.       │              │
│ Overview   │                           │ ⚠ Cement     │
│ Site       │ 2 things need attention.  │   Approve →  │
│ Tasks      │                           │              │
│ Materials  │ ┌───────────────────────┐ │ Electrical  │
│ Reports    │ │ 🎙 Tell Oga what      │ │ delay       │
│ Activity   │ │    happened on site   │ │ Review →    │
│            │ │ 📷   🎙   Type...     │ │              │
│            │ └───────────────────────┘ │              │
│            │                           │              │
│            │ TODAY                     │              │
│            │ ✓ Blockwork completed     │              │
│            │ ⚠ Electrical blocked      │              │
│            │ ⚠ Cement running low      │              │
│            │                           │              │
└────────────┴───────────────────────────┴──────────────┘
```

The **Oga composer** is the primary interface.

Support:

```text
🎙 voice
📷 photo
⌨ text
📎 file
```

Agents CLI itself supports multimodal file input during agent runs, so the ADK ecosystem already accommodates the kind of multimodal development/testing we need. ([Google GitHub][5])

---

# 15. Mobile Matters More Than Desktop

The site worker experience should be brutally simple.

```text
┌─────────────────────────┐
│ Oga Foreman             │
│                         │
│ Ridge Project           │
│                         │
│ What happened today?    │
│                         │
│        ┌───────┐        │
│        │  🎙   │        │
│        │ Hold  │        │
│        └───────┘        │
│                         │
│   📷 Add site photos    │
│                         │
│ ──────────────────────  │
│                         │
│ Oga                     │
│ ✓ Update received       │
│                         │
│ I found:                │
│ • 1 completed task      │
│ • 1 blocker             │
│ • 1 material risk       │
│                         │
│      View actions →     │
└─────────────────────────┘
```

No training required.

---

# 16. Free Product Strategy

For the hackathon, remove monetization completely.

No:

```text
$19 Starter
$49 Pro
usage credits
AI tokens
trial expiration
```

Instead:

```text
FREE

Unlimited projects during beta*
Voice site updates
Photo updates
Daily reports
Material tracking
Blocker detection
AI daily briefs
```

Infrastructure protection can happen behind the scenes through sane rate limits. It doesn't need to become part of the product story.

---

# 17. Safety and Autonomy Boundary

This should actually help us with judges.

Oga may autonomously:

```text
update records
create tasks
mark reported progress
create reports
flag risks
prepare requests
send routine notifications
```

Oga requires approval for:

```text
purchases
major schedule changes
external commitments
financial actions
task cancellation
high-impact project changes
```

Oga must **never** represent itself as replacing engineers or certify structural/safety-critical decisions.

If an update suggests a potentially serious site-safety or structural issue:

```text
FLAG
      ↓
STOP AUTOMATION
      ↓
ESCALATE TO QUALIFIED HUMAN
```

This gives us useful human-in-the-loop behavior rather than adding HITL merely because the technology supports it.

---

# 18. Observability = Part of the Product

Don't hide the agents.

Show their work.

### Activity screen

```text
Oga Run #821
─────────────────────────────

Trigger
Site update received

✓ Interpreted site update
✓ Retrieved 14 active tasks
✓ Detected completed blockwork
✓ Detected electrical blocker
✓ Detected cement shortage
✓ Checked downstream tasks
✓ Created material request
◷ Waiting for approval

Duration: 4.2s
```

Behind the UI, use Cloud Logging/Trace. Google's current agent tooling provides workflows for adding observability infrastructure and inspecting spans for LLM calls and tool executions. ([Google GitHub][6])

That gives the judges both:

**consumer experience**

and

**technical proof**.

---

# 19. Evals Are Mandatory

Don't wait until the end.

Create cases such as:

### Normal

```text
"Ground floor plumbing is finished."
```

Expected:

```text
progress update only
```

### Mixed

```text
"Plumbing is finished but the tiles haven't arrived."
```

Expected:

```text
complete plumbing
flag material blocker
```

### Ambiguous

```text
"I think we're almost done with plastering."
```

Expected:

```text
do NOT mark task completed
request clarification
```

### Approval

```text
"We need another 100 bags of cement."
```

Expected:

```text
prepare request
do not purchase automatically
```

### Duplicate event

Same voice note delivered twice.

Expected:

```text
one set of mutations
```

Agents CLI includes dataset generation, grading and before/after evaluation comparison, so Codex should incorporate those tools rather than building a custom eval framework. ([Google GitHub][7])

---

# 20. Implementation Order for Codex

## Phase 0 — Freeze the contract

**Output**

```text
docs/
├── PRODUCT.md
├── ARCHITECTURE.md
├── DOMAIN_MODEL.md
├── WORKFLOWS.md
└── UI_UX.md
```

No feature coding until those agree.

---

## Phase 1 — Foundation

Implement:

```text
configuration
database
domain schemas
repositories
tool interfaces
seed project
sample project state
activity logging
```

**Definition of done:** tests can manipulate a fake construction project entirely without Gemini.

---

## Phase 2 — Agent kernel

Implement:

```text
OgaCoordinator
SiteInterpreter
structured outputs
project-context retrieval
tool registry
```

**Definition of done:** messy site text becomes validated structured facts.

---

## Phase 3 — Killer vertical slice

Implement the entire Daily Site Update workflow.

Input:

```text
text/voice/photo
```

Output:

```text
project mutated
tasks updated
issues created
materials detected
report updated
timeline recorded
```

**Do not move forward until this demos flawlessly.**

---

## Phase 4 — Material workflow

Add:

```text
shortage detection
material request
approval pause
approval UI
workflow resume
```

---

## Phase 5 — Blocker workflow

Add:

```text
dependency reasoning
schedule risk
task escalation
resolution tracking
```

---

## Phase 6 — Event-driven Oga

Add:

```text
Pub/Sub
Eventarc
scheduled daily brief
workflow continuation
event idempotency
retry handling
```

Now Oga operates without waiting for chat prompts.

---

## Phase 7 — Product UI

Build:

```text
landing page
project onboarding
command center
Oga composer
activity timeline
approvals
tasks
materials
daily report
mobile site-update experience
```

No decorative dashboards unless they communicate actionable state.

---

## Phase 8 — Reliability

Build:

```text
eval suite
integration tests
tool tests
workflow tests
duplicate-event protection
retry tests
approval tests
structured logging
tracing
error handling
```

---

## Phase 9 — Hackathon polish

Finish:

```text
seeded demo project
demo reset command
architecture diagram
README
deployment instructions
public Cloud Run deployment
demo video
screenshots
submission write-up
```

---

# 21. Codex Rules

Put something equivalent to this in the repository instructions:

```text
OGA FOREMAN ENGINEERING RULES

1. Read docs/PRODUCT.md and docs/IMPLEMENTATION_PLAN.md before coding.

2. Implement only the active phase.

3. Do not introduce new product scope without explicit approval.

4. Prefer Google ADK primitives over custom agent infrastructure.

5. LLMs reason; deterministic tools mutate state.

6. All agent writes must go through typed tools.

7. All mutations must create ActivityEvents.

8. All workflow steps must be idempotent.

9. High-impact actions require approval.

10. Never store project truth only inside prompts or agent memory.

11. Every workflow requires tests and eval cases.

12. Mobile usability is a first-class requirement.

13. No billing, pricing, credits, subscriptions or feature gating.

14. Preserve the simple "Tell Oga" product experience.

15. Do not replace working code merely to satisfy aesthetic refactors.

16. At the end of every phase:
    - run tests
    - run lint/type checks
    - report files changed
    - report architecture changes
    - report remaining known issues
    - update implementation status
```

---

# 22. Repository Documentation Codex Should Have

Your existing structure can remain. I would add:

```text
docs/
├── PRODUCT.md
├── IMPLEMENTATION_PLAN.md
├── ARCHITECTURE.md
├── DOMAIN_MODEL.md
├── WORKFLOWS.md
├── AGENT_DESIGN.md
├── TOOL_CONTRACTS.md
├── EVENT_SCHEMA.md
├── UI_UX.md
├── EVALS.md
├── DEMO.md
└── DEPLOYMENT.md
```

Google's current agent tooling follows a similar philosophy: define what the agent does, its integrations, constraints and success criteria before letting a coding agent implement it. ([Google GitHub][8])

---

# 23. The Demo We Build Toward From Day One

This is crucial.

Don't build the product and later ask:

> “What should we demo?”

Build **for this exact scenario**.

### 0:00 — The problem

Construction information lives in calls, voice notes, pictures and people's heads.

### 0:30 — Talk to Oga

Foreman records:

> “First-floor blockwork is done. Electrician didn't come. We're down to ten bags of cement and plastering starts tomorrow.”

Uploads two photos.

### 1:00 — Oga takes over

Live activity:

```text
✓ Blockwork completed
⚠ Electrical blocker detected
⚠ Plastering may be affected
⚠ Cement shortage detected
✓ Purchase request prepared
✓ Daily report updated
```

### 1:45 — Human control

Oga:

> Cement is likely insufficient for tomorrow's plastering. I prepared a request. Approve?

Manager presses:

**Approve.**

ADK workflow resumes.

### 2:15 — Disruption

Simulate:

```text
DELIVERY_DELAYED
```

Oga automatically wakes up.

No prompt.

It:

```text
identifies affected plastering task
updates risk
creates follow-up
alerts manager
```

### 3:00 — Show the audit trail

Open Oga Activity.

Show every decision, tool call and workflow transition.

### 3:30 — Architecture

Show:

```text
Gemini
  +
Google ADK 2
  +
Cloud Run
  +
Pub/Sub/Eventarc
  +
Firestore
```

### 3:45 — End

> **Oga Foreman doesn't wait for you to manage the software. It watches the project, figures out what needs to happen next, and keeps the site moving.**

That is the product I would build.

---

## The one metric for every development decision

Ask:

> **Does this feature make Oga better at turning an unstructured site event into completed follow-through?**

If yes, build it.

If no, **after the hackathon**.

And visually, borrow Reclip's strongest lesson: make the complicated technology almost invisible. Its current site presents many AI operations through simple, outcome-focused tools rather than exposing the machinery underneath. ([Reclip][4])

For Oga Foreman, the equivalent is even simpler:

# **Talk to Oga. Keep the site moving.**

That should guide Codex, the architecture, the UX and the demo.

[1]: https://github.com/google/adk-python/blob/main/README.md?utm_source=chatgpt.com "adk-python/README.md at main · google/adk-python · GitHub"
[2]: https://github.com/google/adk-python "GitHub - google/adk-python: An open-source, code-first Python toolkit for building, evaluating, and deploying sophisticated AI agents with flexibility and control. · GitHub"
[3]: https://google.github.io/agents-cli/guide/deployment/?utm_source=chatgpt.com "Deployment - agents-cli"
[4]: https://www.reclip.io/ "Reclip – AI Video Clipper, Voiceover & Creator Tools"
[5]: https://google.github.io/agents-cli/cli/?utm_source=chatgpt.com "CLI - agents-cli"
[6]: https://google.github.io/agents-cli/guide/quickstart-tutorial/?utm_source=chatgpt.com "Tutorial: Build Your First Agent - agents-cli"
[7]: https://google.github.io/agents-cli/guide/evaluation/?utm_source=chatgpt.com "Evaluation Guide - agents-cli"
[8]: https://google.github.io/agents-cli/guide/development/?utm_source=chatgpt.com "Development Guide - agents-cli"

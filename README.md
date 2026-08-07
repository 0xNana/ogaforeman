# 🏗️ Oga Foreman — Autonomous Construction Coordinator

**Oga Foreman** is an event-driven, autonomous construction site management platform built natively on **Google ADK 2.0 (`google-adk`)**.

Rather than operating as a passive chatbot ("*Ask Oga about your project*"), Oga Foreman continuously monitors site inputs (voice updates, photos, delivery webhooks, task events) and keeps the project moving forward.

---

## 🏛️ Architecture

```
                                 OGA FOREMAN
                                      │
                     ┌────────────────┴────────────────┐
                     │                                 │
                Site Updates                       System Events
             voice / text / photos              schedule / delivery
                     │                                 │
                     └───────────────┬─────────────────┘
                                     ▼
                             Google ADK 2.x
                           Oga Coordinator (app/agent.py)
                                     │
               ┌─────────────────────┼─────────────────────┐
               ▼                     ▼                     ▼
          Site Report            Planning              Materials
            Agent                 Agent                  Agent
               │                     │                     │
               └──────────┬──────────┴──────────┬──────────┘
                          ▼                     ▼
                      Task Agent          Communication
                                             Agent
                          │                     │
                          └──────────┬──────────┘
                                     ▼
                                ADK Workflow
                                     │
                        ┌────────────┼─────────────┐
                        ▼            ▼             ▼
                    automatic      approval      retry /
                     actions        gates        recovery
                        │            │             │
                        └────────────┴─────────────┘
                                     ▼
                             Project State
```

---

## 📂 Codebase Layout

```
ogaforeman/
├── app/
│   ├── agent.py              # Oga root coordinator agent
│   ├── workflows/            # Core ADK 2.0 Graph Workflows
│   │   ├── site_update.py    # Voice & photo progress extraction
│   │   ├── materials.py      # Inventory check + HITL approval gate
│   │   ├── blockers.py       # Blocker analysis & schedule replanning
│   │   └── daily_brief.py    # Executive daily brief digest
│   │
│   ├── agents/               # Specialist ADK LLMAgents
│   │   ├── site_report.py
│   │   ├── planner.py
│   │   ├── materials.py
│   │   └── communicator.py
│   │
│   ├── tools/                # ADK FunctionTools
│   │   ├── projects.py       # Site state lookup
│   │   ├── tasks.py          # Progress & blocker updates
│   │   ├── materials.py      # Inventory & procurement
│   │   ├── reports.py        # Summary report generator
│   │   └── notifications.py  # PM alerts & notifications
│   │
│   ├── schemas/              # Pydantic data schemas
│   │   ├── site_update.py
│   │   └── project_event.py
│   │
│   └── prompts/              # System prompt templates
│       ├── oga_coordinator.txt
│       ├── site_report.txt
│       ├── planner.txt
│       ├── materials.txt
│       └── communicator.txt
│
├── web/                      # Oga Foreman Dashboard UI
│   └── index.html
├── tests/                    # pytest suite
│   └── test_workflows.py
├── evals/                    # ADK evaluation dataset
│   └── eval_site_updates.json
├── pyproject.toml
├── Dockerfile
└── README.md
```

---

## ⚡ Quick Start

### 1. Run End-to-End Workflow Demo (CLI)
```bash
python3 main.py --demo
```

### 2. Run Test Suite
```bash
pytest tests/
```

### 3. Launch Web Dashboard & API Server
```bash
uvicorn main:app --reload --port 8000
```
Open `http://localhost:8000` in your browser.
# ogaforeman

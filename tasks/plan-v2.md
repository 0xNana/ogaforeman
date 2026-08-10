# Oga Foreman V2 Execution Plan (Commercial & Go-To-Market)

## How to Use This Plan

Work top to bottom. This plan builds upon the production-ready foundation established in V1 and focuses on transitioning Oga Foreman into a revenue-generating, enterprise-ready product. Mark the matching items in a new `tasks/todo-v2.md` as they are completed.

## Phase 1: Commercial Engine & Billing

### C-01: Integrate SaaS Billing Provider
- **Acceptance**: Stripe (or similar) is integrated for subscription management. Projects/Organizations require an active subscription or trial to process events.
- **Tasks**:
  - Define pricing tiers (e.g., Free Trial, Pro, Enterprise).
  - Implement Stripe Checkout and Customer Portal.
  - Add billing status checks to `app/api/dependencies.py` to gate API access.

### C-02: Usage Metering and Limits
- **Acceptance**: Track agent execution runs and media uploads per tenant to enforce billing tier limits.
- **Tasks**:
  - Emit usage metrics during `OgaCoordinator` and media upload processes.
  - Sync usage to billing provider for usage-based billing components.

## Phase 2: Real Integrations & Ecosystem

### I-01: Procore / Autodesk Construction Cloud Sync
- **Acceptance**: Oga can securely authenticate with a third-party system of record and sync Daily Reports, Issues, and Tasks.
- **Tasks**:
  - Implement OAuth2 flows for external construction software.
  - Create integration adapters to push daily briefs to external systems.

### I-02: Real Supplier Webhooks
- **Acceptance**: Replace `supplier_simulator.py` with real webhook dispatches to actual procurement APIs or automated email generation for purchase orders.
- **Tasks**:
  - Build a generic Webhook/Email Outbox worker.
  - Allow administrators to configure external webhook endpoints per project.

## Phase 3: Mobile Native Application

### M-01: React Native / Expo Application Shell
- **Acceptance**: A native iOS/Android application exists with authentication and basic navigation, replacing the need to use the mobile web browser.
- **Tasks**:
  - Initialize Expo project in a new `mobile/` directory.
  - Port existing Next.js logic for auth and API clients to React Native.

### M-02: Offline-First Capability
- **Acceptance**: Site updates can be recorded (voice/photos) offline and queued for upload when connectivity is restored.
- **Tasks**:
  - Implement local SQLite or WatermelonDB for the mobile app.
  - Build a background sync queue for `SiteUpdate` events and attachments.

## Phase 4: Enterprise Security & Compliance

### E-01: Advanced RBAC and SSO
- **Acceptance**: Organizations can manage access via SAML/SSO (Okta, Microsoft Entra). Granular roles are enforced.
- **Tasks**:
  - Integrate enterprise identity provider support into the Firebase/Identity Platform setup.
  - Refine `app/domain/authorization.py` for granular permissions.

### E-02: Data Retention Lifecycle
- **Acceptance**: Audio, photos, and agent transcripts are automatically archived or deleted based on project compliance settings to reduce storage costs and meet privacy laws.
- **Tasks**:
  - Add retention policies to project configuration.
  - Create scheduled worker tasks to prune expired Storage objects and Firestore records.

## Phase 5: Expanded Agentic Capabilities

### A-01: Multilingual Voice Intake
- **Acceptance**: Foremen can speak in languages other than English, and Oga correctly translates and interprets the facts into the English project baseline.
- **Tasks**:
  - Update `app/infrastructure/gemini.py` to handle explicit multilingual transcription instructions.
  - Add user-preference or project-preference language settings.

### A-02: Blueprint / Document Ingestion (Research Phase)
- **Acceptance**: Oga can ingest PDF blueprints or basic CAD exports to provide spatial context to site updates.
- **Tasks**:
  - Design data model for "Site Documents".
  - Build RAG (Retrieval-Augmented Generation) pipeline for agents to query document context during fact routing.

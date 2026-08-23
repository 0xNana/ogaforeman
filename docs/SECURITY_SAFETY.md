# Security and Safety Requirements

## Threat Model

Treat all site text, transcriptions, photos, files, supplier messages, browser input, and model output as untrusted. The primary risks are cross-project data exposure, unauthorized high-impact action, prompt injection, malicious uploads, duplicate external side effects, and misleading safety claims.

## Identity and Authorization

The normative request flow, identity mapping, browser-session contract, role
matrix, errors, and workload boundary are defined in [AUTH.md](AUTH.md).

- Verify identity tokens at the API boundary.
- Resolve the verified external subject to exactly one active canonical `User.id`; never use email
  or display name as identity.
- Resolve active `ProjectMember` role for every project request.
- Enforce authorization again in repositories/tools; route checks alone are insufficient.
- Permission matrix:

| Role | Read | Operate | Approve | Manage |
| --- | --- | --- | --- | --- |
| `admin` | yes | yes | yes | yes |
| `manager` | yes | yes | yes | no |
| `foreman` | yes | yes | no | no |
| `viewer` | yes | no | no | no |

- `manage` covers project configuration and membership; `approve` covers approval and major
  schedule decisions; `operate` covers site updates and low-impact project mutations.
- Carry a typed project access context from the API into services/tools, and re-check both project
  scope and required permission at repository and transaction boundaries.
- Service-to-service events use workload identity and an allowlisted adapter identity.
- Never accept `project_id`, entity IDs, or recipient IDs from model output without checking them against authorized context.

## Media and Uploads

- Use short-lived signed upload URLs scoped to one project and attachment ID.
- Allowlist content types and enforce byte-size limits before signing and after upload.
- Verify object path, checksum, MIME sniffing, and upload status before processing.
- Store media in private buckets; serve through authorized signed reads.
- Do not execute, render, or transform untrusted files in the API process.
- Scan uploads where available and reject quarantined objects.
- Retain original evidence and deletion metadata according to the configured retention policy.

## Prompt and Model Security

- Delimit untrusted content and label it as evidence.
- Never include secrets, unrelated projects, or raw authorization tokens in prompts.
- Validate structured output against Pydantic schemas and domain policies.
- Use allowlisted tool names and typed arguments only.
- Do not let the model choose arbitrary URLs, collection paths, code, or shell commands.
- Log model ID, prompt version, token/latency metadata, and validation outcome, but not hidden reasoning.

Project-import source text is bounded by UTF-8 bytes, delimited as untrusted
data, and processed only after active membership plus `MANAGE` authorization.
The extraction schema rejects canonical IDs, trusted provenance, arbitrary
fields, mutation tokens, and decision authority. Deterministic normalization
binds temporary source references to the persisted project source, and the
transactional importer generates every canonical ID. Per-user/project extraction
limits run before source persistence and Gemini invocation.

## Approval and Autonomy

- Purchases, external commitments, financial actions, task cancellation, major schedule changes, and high-impact changes always require a human decision in V1.
- Approval resolution is role-checked, version-checked, idempotent, and audit logged.
- The UI must show evidence and impact before the decision button.
- A rejection must close the linked request branch and cannot trigger an external commitment.

## Construction Safety Boundary

OG does not certify engineering, structural, quality, or safety decisions. If input suggests injury, imminent hazard, structural failure, unsafe equipment, or a request to conceal a risk:

1. create a high/critical safety issue;
2. stop the normal autonomous mutation branch;
3. notify the configured manager/safety role;
4. ask for qualified human acknowledgement;
5. resume only the explicitly approved safe branch.

## Data Protection

- Minimize personal data in project records and logs.
- Encrypt data in transit and at rest using managed GCP controls.
- Define retention and deletion for media, transcripts, reports, activities, and traces before public beta.
- Redact emails, phone numbers, tokens, and raw media URLs from ordinary logs.
- Keep audit records append-only to ordinary users; corrections create new events.

## Availability and Abuse Controls

- Apply per-user, per-project, and per-IP rate limits to intake, uploads, and expensive model work.
- Bound media size, transcript length, attachment count, context size, model retries, and workflow duration.
- Use Pub/Sub dead-letter handling and alert on poison events.
- Use circuit breakers or graceful degradation when model or notification dependencies fail.

## Verification Ownership

This document defines the security and safety policy. Release-gate test coverage,
commands, and required operational evidence belong to the release process; service
availability and recovery targets are defined in [SLOS.md](SLOS.md).

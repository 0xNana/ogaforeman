# Authentication and Authorization Contract

## Status

Accepted as the V1 identity and authorization contract. The verifier, canonical
identity repository, idempotent bootstrap, membership policy, repository guards,
browser session provider, auth screens, protected project loading, and
token-aware API client are implemented. Firebase credentials and deployed
browser/cloud evidence are still release gates.

## Identity Boundary

OG Foreman uses Firebase Authentication or Google Cloud Identity Platform for
human identity. Firebase proves control of an external account; it does not
grant access to OG Foreman projects by itself.

The verified Firebase `sub` claim is the external identity key. OG resolves
that subject to exactly one active canonical `User.id` stored in Firestore, then
uses the canonical ID for membership, activities, approvals, mutations, and
audit records.

Never use email, phone number, display name, or a model-provided value as an
application identity or authorization key. Email may be retained as mutable
contact metadata only.

## Human Request Flow

Every protected project request follows this sequence:

1. Extract an `Authorization: Bearer <identity-token>` header.
2. Verify the Firebase token signature, audience, issuer, expiry, and subject.
3. Resolve the verified `sub` to one active canonical Firestore `User`.
4. Load the user's active `ProjectMember` record for the requested project.
5. Check the route's required permission and create an immutable
   `ProjectAccessContext` containing the canonical actor, project, and role.
6. Pass that context into application services, repositories, transactions, and
   typed tools.
7. Recheck project scope and permission at repository and tool boundaries before
   reads or mutations.

Route checks are necessary but not sufficient. A project ID in a URL, request
body, event, model result, or tool argument never overrides the authorized
project context.

## Roles and Permissions

| Role | Read | Operate | Approve | Manage |
| --- | --- | --- | --- | --- |
| `admin` | yes | yes | yes | yes |
| `manager` | yes | yes | yes | no |
| `foreman` | yes | yes | no | no |
| `viewer` | yes | no | no | no |

- `read` covers project-owned views and private media access.
- `operate` covers site updates and validated low-impact project mutations.
- `approve` covers approval decisions and consequential schedule decisions.
- `manage` covers project configuration and membership.

Purchases, external commitments, financial actions, task cancellation, major
schedule changes, and safety-critical actions still require the autonomy and
approval controls in [SECURITY_SAFETY.md](SECURITY_SAFETY.md). A role never
bypasses those controls.

## Browser Session Contract

The Next.js application must use the modular Firebase Web SDK to establish the
browser session. Protected application data must not be requested until Firebase
has resolved the session state. For real API requests, the client obtains a
current ID token and sends it as the Bearer token. It may retry once after a
token refresh when the API returns `401`, then must return the user to sign-in
with a controlled expired-session state.

The public marketing and deterministic demo routes do not require or attach a
user token. Demo fixtures must never be used as a fallback for a failed
authenticated request.

The frontend implements this with client-side authenticated data loading:
protected project layouts wait for `onAuthStateChanged` and then load the
project snapshot with a Bearer token. This prevents server components from
fetching protected data before authentication is established.

## Registration and Provisioning

A valid Firebase account is not automatically a project member. The current V1
path is a verified bootstrap endpoint followed by explicit project creation or
membership assignment. Invitations can be added later without changing the
identity boundary.

Provisioning must use a stable operation key, reject duplicate subject mappings,
emit an `ActivityEvent` with the canonical actor/source context when it mutates
project state, and never infer a role from token claims or profile fields.

`POST /api/v1/auth/bootstrap` provisions an unknown verified subject at a
deterministic canonical ID in a Firestore transaction and returns the existing
user on replay. Protected routes reject unknown subjects until bootstrap
succeeds. Project list/create and an empty authenticated project snapshot are
wired for onboarding; complete domain projections remain an API/workflow gap.

## Deployed Configuration

Preview, staging, and production require:

```text
AUTH_ISSUER=https://securetoken.google.com/<firebase-project-id>
AUTH_AUDIENCE=<firebase-project-id>
```

`AUTH_AUDIENCE` is passed to the official Firebase token verifier.
`AUTH_ISSUER` is checked against the token's `iss` claim. Missing values fail
deployed settings validation. Credentials and raw tokens belong in managed
identity/secret boundaries and must never appear in configuration files, logs,
traces, activities, or error details.

Firebase Console configuration must enable only the approved sign-in providers
and authorized domains. Email/password is the initial V1 browser provider; any
additional provider requires an explicit product and security decision.

## Workload Authentication

Cloud Run worker authentication is separate from user authentication. Pub/Sub
push and Cloud Scheduler use an OIDC service account with
`roles/run.invoker` on the private worker service. The API and worker run as
least-privilege service accounts and use Application Default Credentials for
Google Cloud resources.

Cloud Run IAM proves which workload invoked the private endpoint. The
application still validates the immutable `ProjectEvent` envelope, event type,
project scope, claim, and idempotency key before processing. Workload identity
does not authorize arbitrary workflow or tool names from request data.

## Error Contract

| Code | HTTP | Meaning |
| --- | --- | --- |
| `AUTH_REQUIRED` | 401 | Missing, malformed, invalid, expired, disabled, or unregistered identity |
| `AUTH_PROJECT_FORBIDDEN` | 403 | No active membership for the requested project or cross-project access |
| `ROLE_REQUIRED` | 403 | Active membership exists but the role lacks the required permission |

Responses use the versioned error envelope in [API.md](API.md). They do not
reveal whether a different project, user, membership, or private entity exists.

## Local and Demo Behavior

Unit and integration tests may inject deterministic token verifiers and
in-memory identity/membership repositories. Firestore persistence tests use the
Firestore emulator. Local demo mode may use seeded canonical users, but it must
be explicit and must not be enabled in preview, staging, or production.

No local fallback may silently treat an unverified request as an admin, derive a
user from display text, or switch a failed production API request to fixtures.

## Implementation and Evidence

Implemented components:

- `FirebaseTokenVerifier` with audience, issuer, and subject validation;
- Bearer extraction and active canonical-user resolution;
- Firestore and in-memory identity repositories;
- active project membership and role policy;
- immutable `ProjectAccessContext`;
- repository and transaction project/permission guards;
- stable authentication and authorization error codes;
- role, cross-project, disabled-user, provisioning, and emulator persistence tests;
- Firebase session, sign-in/sign-up/reset screens, protected client-side loading,
  Bearer-token injection, and one forced-refresh retry;
- a public `/demo` route isolated from authenticated project API state.

Open implementation gaps:

- `main.py` installs the production provider when auth settings are present;
  local environments without those settings intentionally fail closed;
- several V1 routers are empty or stubs and therefore do not exercise the auth
  boundary end to end;
- project snapshots are empty for new projects until the remaining V1
  projections and routers are completed;
- real Firebase browser E2E has not been executed;
- secure-cookie/token behavior has not been tested in a deployed browser.

Required launch evidence:

- valid, expired, wrong-audience, wrong-issuer, malformed, unknown, and disabled
  token tests;
- every-role and cross-project tests at route, repository, transaction, and tool
  boundaries;
- idempotent first-user provisioning or invitation tests;
- browser sign-in, refresh, sign-out, reset, and protected-route tests;
- production app requests carrying Firebase Bearer tokens without demo fallback;
- staging verification against the configured Firebase project and authorized
  domains;
- workload OIDC invocation and unauthenticated worker rejection evidence.

# ADR-007: Verify Source-to-Deployment Provenance

## Status

Accepted

## Date

2026-08-23

## Context

The repository and deployed Cloud Run services can advance independently. An
image tag from an older commit does not prove that the public API runs the
submitted source. Committing a post-deployment evidence file also creates a new
commit that the evidence cannot describe.

## Decision

For every deployment, `infra/deploy.sh` derives the full Git object ID from
`HEAD`, the dirty-tree state, the application version, and one UTC build time.
It stamps those values into both OCI images and all three Cloud Run revisions.
The public `GET /api/v1/version` endpoint exposes only that safe identity plus
Cloud Run's `K_SERVICE` and `K_REVISION` values.

After traffic migration, `scripts/verify_deployment_provenance.py` compares the
repository `HEAD` with the endpoint and each latest ready revision, its stamped
fields, revision creation timestamp, and resolved `status.imageDigest`. The
verifier does not accept an operator-supplied expected SHA. Any mismatch fails.
Passing evidence includes the safe endpoint response and each service's name,
revision, deployment timestamp, URL, and immutable digest. Current evidence uses the
ignored `artifacts/operations/*-deployment-current.json` path so generating it
does not change the commit being proved. Only allowlisted fields enter the
artifact; arbitrary environment values and secret references are excluded.

## Alternatives Considered

Trusting the image tag was rejected because tags are mutable and do not prove
the running revision's digest. Committing current deployment evidence was
rejected because that creates a different commit. Exposing the complete process
environment was rejected because it could leak configuration or secrets.

## Consequences

- Preview, staging, and production startup requires a full Git SHA and aware
  build timestamp.
- A dirty emergency deployment can identify itself but cannot pass release
  provenance.
- Judges can compare repository commit, public API response, Cloud Run
  revisions, and immutable image digests.
- Current evidence must be preserved externally or in the submission record
  without committing a new source revision.

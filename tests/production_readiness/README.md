# Production-readiness suite

`test_controls.py` groups the production-readiness safeguards as PR-01 through
PR-13. The public reliability and verification contract is maintained in
[`docs/ENGINEERING_SPEC.md`](../../docs/ENGINEERING_SPEC.md).

- Passing tests are locally verified controls.
- Strict `xfail` tests are known release blockers caused by missing prerequisite
  implementation. An unexpected pass fails the suite until the marker and blocker
  documentation are removed.
- Emulator or staging-only evidence is run separately and must not be inferred from
  a local pass.

Run:

```bash
.venv/bin/python -m pytest -q tests/production_readiness
```

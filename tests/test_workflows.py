import unittest
from app.workflows import (
    run_site_update_workflow,
)


class TestOgaWorkflows(unittest.IsolatedAsyncioTestCase):
    async def test_site_update_workflow_requires_explicit_dependencies(self):
        with self.assertRaisesRegex(RuntimeError, "explicit service, runtime, and access"):
            await run_site_update_workflow(
                site_id="prj_site_test",
                raw_text="Column rebar completed for grid A-D.",
            )


if __name__ == "__main__":
    unittest.main()

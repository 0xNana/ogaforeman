from __future__ import annotations

import httpx
import pytest

from scripts.smoke_observability import run_smoke


class StubTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        payloads = {
            "/healthz": (200, '{"status":"ok"}'),
            "/readyz": (200, '{"status":"ready"}'),
            "/metrics": (200, "oga_test_counter 1\n"),
        }
        status_code, body = payloads[request.url.path]
        assert request.headers["x-request-id"].startswith("req_smoke_")
        assert request.headers["x-correlation-id"].startswith("cor_smoke_")
        assert request.headers["x-trace-id"].startswith("trc_smoke_")
        return httpx.Response(status_code, text=body, request=request)


def test_smoke_collects_correlation_headers_without_mutating_state() -> None:
    client = httpx.Client(transport=StubTransport())
    evidence = run_smoke("https://staging.example.test/", client=client)

    assert evidence.passed is True
    assert [check.name for check in evidence.checks] == ["liveness", "readiness", "metrics"]
    assert evidence.base_url == "https://staging.example.test"


def test_smoke_rejects_non_http_urls() -> None:
    with pytest.raises(ValueError, match=r"absolute http\(s\) URL"):
        run_smoke("staging.example.test")

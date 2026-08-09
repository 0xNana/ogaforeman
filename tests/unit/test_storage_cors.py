from __future__ import annotations

import json

import pytest

from infra.render_storage_cors import build_storage_cors


def test_storage_cors_allows_only_configured_origins_for_signed_media() -> None:
    origins_json = json.dumps(
        [
            "https://ogaforeman-cloud-2026.web.app",
            "https://ogaforeman-cloud-2026.firebaseapp.com",
        ]
    )

    rules = build_storage_cors(origins_json)

    assert rules == [
        {
            "origin": [
                "https://ogaforeman-cloud-2026.web.app",
                "https://ogaforeman-cloud-2026.firebaseapp.com",
            ],
            "method": ["GET", "HEAD", "PUT", "OPTIONS"],
            "responseHeader": [
                "Content-Length",
                "Content-Type",
                "ETag",
                "x-goog-generation",
                "x-goog-if-generation-match",
            ],
            "maxAgeSeconds": 600,
        }
    ]


@pytest.mark.parametrize(
    "origins_json",
    [
        "[]",
        '["*"]',
        '["http://ogaforeman.example"]',
        '["https://ogaforeman.example/path"]',
        '{"origin":"https://ogaforeman.example"}',
    ],
)
def test_storage_cors_rejects_empty_wildcard_or_non_exact_origins(origins_json: str) -> None:
    with pytest.raises(ValueError, match="exact HTTPS origins"):
        build_storage_cors(origins_json)

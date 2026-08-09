from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def build_storage_cors(origins_json: str) -> list[dict[str, Any]]:
    try:
        raw_origins = json.loads(origins_json)
    except json.JSONDecodeError as exc:
        raise ValueError("storage CORS requires a JSON list of exact HTTPS origins") from exc
    if not isinstance(raw_origins, list) or not raw_origins:
        raise ValueError("storage CORS requires a JSON list of exact HTTPS origins")

    origins: list[str] = []
    for raw_origin in raw_origins:
        if not isinstance(raw_origin, str):
            raise ValueError("storage CORS requires a JSON list of exact HTTPS origins")
        origin = raw_origin.strip()
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or origin != f"{parsed.scheme}://{parsed.netloc}"
        ):
            raise ValueError("storage CORS requires a JSON list of exact HTTPS origins")
        if origin not in origins:
            origins.append(origin)

    return [
        {
            "origin": origins,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Render exact-origin media bucket CORS JSON")
    parser.add_argument("--origins-json", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rules = build_storage_cors(args.origins_json)
    args.output.write_text(json.dumps(rules, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

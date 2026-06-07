"""Diagnose local or Azure-hosted Ollama-compatible endpoints.

Configuration comes from environment variables:
  OLLAMA_BASE_URL
  OLLAMA_API_KEY
  LLM_MODEL_NAME
  EMBED_MODEL_NAME
"""

from __future__ import annotations

import argparse
import os
import socket
from urllib.parse import urlparse

import requests


def _base_url(raw_url: str) -> str:
    return raw_url.rstrip("/").removesuffix("/api/generate").removesuffix("/api/chat")


def _headers(api_key: str | None) -> dict[str, str]:
    return {"api-key": api_key} if api_key else {}


def _require_key_for_remote(base_url: str, api_key: str | None) -> None:
    host = urlparse(base_url).hostname or ""
    if host not in {"localhost", "127.0.0.1", "::1"} and not api_key:
        raise SystemExit(
            "OLLAMA_API_KEY is required for non-local endpoints. "
            "Set it in the environment; no fallback key is embedded in this tool."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--api-key", default=os.getenv("OLLAMA_API_KEY"))
    parser.add_argument("--llm-model", default=os.getenv("LLM_MODEL_NAME", "llama2:latest"))
    parser.add_argument("--embed-model", default=os.getenv("EMBED_MODEL_NAME", "nomic-embed-text:latest"))
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    base_url = _base_url(args.base_url)
    _require_key_for_remote(base_url, args.api_key)
    headers = _headers(args.api_key)

    print(f"Endpoint: {base_url}")
    host = urlparse(base_url).hostname
    if host:
        try:
            print(f"DNS: {host} -> {socket.gethostbyname(host)}")
        except OSError as exc:
            print(f"DNS: failed ({exc})")

    failures = 0

    try:
        response = requests.get(f"{base_url}/api/tags", headers=headers, timeout=args.timeout)
        print(f"GET /api/tags: HTTP {response.status_code}")
        if response.ok:
            models = response.json().get("models", [])
            print(f"Models: {', '.join(m.get('name', '?') for m in models[:10]) or '(none)'}")
        else:
            failures += 1
    except requests.RequestException as exc:
        print(f"GET /api/tags: ERROR {exc}")
        failures += 1

    try:
        response = requests.post(
            f"{base_url}/api/chat",
            headers=headers,
            json={
                "model": args.llm_model,
                "messages": [{"role": "user", "content": "Say OK"}],
                "stream": False,
            },
            timeout=args.timeout,
        )
        print(f"POST /api/chat ({args.llm_model}): HTTP {response.status_code}")
        if not response.ok:
            print(response.text[:300])
            failures += 1
    except requests.RequestException as exc:
        print(f"POST /api/chat: ERROR {exc}")
        failures += 1

    try:
        response = requests.post(
            f"{base_url}/api/embeddings",
            headers=headers,
            json={"model": args.embed_model, "prompt": "test"},
            timeout=args.timeout,
        )
        print(f"POST /api/embeddings ({args.embed_model}): HTTP {response.status_code}")
        if not response.ok:
            print(response.text[:300])
            failures += 1
    except requests.RequestException as exc:
        print(f"POST /api/embeddings: ERROR {exc}")
        failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())


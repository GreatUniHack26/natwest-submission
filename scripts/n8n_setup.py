#!/usr/bin/env python3
"""Create or update the "FinTime news" workflow in n8n and activate it.

Usage:
    .venv/bin/python scripts/n8n_setup.py [--write-env]

Reads N8N_BASE_URL and N8N_API_KEY from the environment, falling back to the repo's .env
(only those two keys are read from it). Uses the n8n public REST API (/api/v1).
With --write-env, upserts N8N_NEWS_WEBHOOK_URL=<production webhook> into the repo's .env.
Secrets are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
WORKFLOW_PATH = REPO_ROOT / "integrations" / "n8n" / "fintime-news.json"
WORKFLOW_NAME = "FinTime news"
WEBHOOK_PATH = "fintime-news"
ENV_KEY = "N8N_NEWS_WEBHOOK_URL"
# The public API rejects read-only/unknown fields on create/update; send only these.
ALLOWED_FIELDS = ("name", "nodes", "connections", "settings")


def load_settings(env_path: Path = ENV_PATH) -> tuple[str, str]:
    """Return (base_url, api_key) from env vars, else from .env. Other .env keys are ignored."""
    values = {k: os.environ.get(k, "").strip() for k in ("N8N_BASE_URL", "N8N_API_KEY")}
    if not all(values.values()) and env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, sep, val = line.strip().partition("=")
            key = key.removeprefix("export ").strip()
            if sep and key in values and not values[key]:
                values[key] = val.strip().strip('"').strip("'")
    return values["N8N_BASE_URL"].rstrip("/"), values["N8N_API_KEY"]


def workflow_payload(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = {k: data[k] for k in ALLOWED_FIELDS if k in data}
    payload["name"] = WORKFLOW_NAME
    payload.setdefault("settings", {"executionOrder": "v1"})
    return payload


def find_workflow(client: httpx.Client, name: str) -> str | None:
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        resp = client.get("/workflows", params=params)
        resp.raise_for_status()
        body = resp.json()
        for wf in body.get("data", []):
            if wf.get("name") == name:
                return str(wf["id"])
        cursor = body.get("nextCursor")
        if not cursor:
            return None


def deploy(client: httpx.Client, payload: dict[str, Any]) -> tuple[str, str]:
    """Create or update the workflow, then activate it. Returns (workflow_id, action)."""
    existing = find_workflow(client, payload["name"])
    if existing:
        resp = client.put(f"/workflows/{existing}", json=payload)
        action = "updated"
    else:
        resp = client.post("/workflows", json=payload)
        action = "created"
    resp.raise_for_status()
    wf_id = str(resp.json().get("id") or existing)
    client.post(f"/workflows/{wf_id}/activate").raise_for_status()
    return wf_id, action


def upsert_env(webhook_url: str, env_path: Path = ENV_PATH) -> None:
    """Set ENV_KEY in .env, replacing only that line (or appending it)."""
    line = f"{ENV_KEY}={webhook_url}"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
    replaced = False
    for i, existing in enumerate(lines):
        if existing.strip().removeprefix("export ").split("=", 1)[0].strip() == ENV_KEY:
            lines[i] = line
            replaced = True
    if not replaced:
        lines.append(line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-env", action="store_true", help=f"upsert {ENV_KEY} into .env")
    parser.add_argument("--env-file", type=Path, default=ENV_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--workflow", type=Path, default=WORKFLOW_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    base_url, api_key = load_settings(args.env_file)
    if not base_url or not api_key:
        print("N8N_BASE_URL and N8N_API_KEY must be set (env or .env).", file=sys.stderr)
        return 2

    client = httpx.Client(
        base_url=f"{base_url}/api/v1",
        headers={"X-N8N-API-KEY": api_key, "Accept": "application/json"},
        timeout=15.0,
        transport=transport,
    )
    try:
        with client:
            wf_id, action = deploy(client, workflow_payload(args.workflow))
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300].replace(api_key, "***")
        print(f"n8n API error {exc.response.status_code} on {exc.request.url.path}: {detail}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"Could not reach n8n at {base_url}: {type(exc).__name__}", file=sys.stderr)
        return 1

    webhook_url = f"{base_url}/webhook/{WEBHOOK_PATH}"
    print(f"Workflow '{WORKFLOW_NAME}' {action} and activated (id {wf_id}).")
    print(f"Production webhook: {webhook_url}")
    if args.write_env:
        upsert_env(webhook_url, args.env_file)
        print(f"Wrote {ENV_KEY} to {args.env_file}")
    else:
        print(f"Set {ENV_KEY}={webhook_url} in .env (or rerun with --write-env).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

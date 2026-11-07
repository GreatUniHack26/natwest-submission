#!/usr/bin/env python3
"""Create or update FinTime's n8n workflows (news, GOV.UK) and activate them.

Usage:
    .venv/bin/python scripts/n8n_setup.py [--workflow news|govuk|all] [--write-env]

Reads N8N_BASE_URL and N8N_API_KEY from the environment, falling back to the repo's .env
(only those two keys are read from it). Uses the n8n public REST API (/api/v1). Each workflow is
created or updated by name, then activated. With --write-env, upserts each deployed workflow's
production webhook into the repo's .env (N8N_NEWS_WEBHOOK_URL, N8N_GOVUK_WEBHOOK_URL).
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
N8N_DIR = REPO_ROOT / "integrations" / "n8n"
# key -> (workflow file, workflow name in n8n, webhook path, .env key)
WORKFLOWS: dict[str, dict[str, Any]] = {
    "news": {"file": N8N_DIR / "fintime-news.json", "name": "FinTime news",
             "webhook_path": "fintime-news", "env_key": "N8N_NEWS_WEBHOOK_URL"},
    "govuk": {"file": N8N_DIR / "fintime-govuk.json", "name": "FinTime GOV.UK",
              "webhook_path": "fintime-govuk", "env_key": "N8N_GOVUK_WEBHOOK_URL"},
}
WORKFLOW_PATH = WORKFLOWS["news"]["file"]
WORKFLOW_NAME = WORKFLOWS["news"]["name"]
WEBHOOK_PATH = WORKFLOWS["news"]["webhook_path"]
ENV_KEY = WORKFLOWS["news"]["env_key"]
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


def workflow_payload(path: Path = WORKFLOW_PATH, name: str = WORKFLOW_NAME) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = {k: data[k] for k in ALLOWED_FIELDS if k in data}
    payload["name"] = name
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


def upsert_env(webhook_url: str, env_path: Path = ENV_PATH, key: str = ENV_KEY) -> None:
    """Set `key` in .env, replacing only that line (or appending it)."""
    line = f"{key}={webhook_url}"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
    replaced = False
    for i, existing in enumerate(lines):
        if existing.strip().removeprefix("export ").split("=", 1)[0].strip() == key:
            lines[i] = line
            replaced = True
    if not replaced:
        lines.append(line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow", choices=[*WORKFLOWS, "all"], default="all",
                        help="which workflow to deploy (default: all)")
    parser.add_argument("--write-env", action="store_true", help="upsert the webhook URL(s) into .env")
    parser.add_argument("--env-file", type=Path, default=ENV_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    base_url, api_key = load_settings(args.env_file)
    if not base_url or not api_key:
        print("N8N_BASE_URL and N8N_API_KEY must be set (env or .env).", file=sys.stderr)
        return 2

    keys = list(WORKFLOWS) if args.workflow == "all" else [args.workflow]
    client = httpx.Client(
        base_url=f"{base_url}/api/v1",
        headers={"X-N8N-API-KEY": api_key, "Accept": "application/json"},
        timeout=15.0,
        transport=transport,
    )
    status = 0
    with client:
        for key in keys:
            spec = WORKFLOWS[key]
            try:
                wf_id, action = deploy(client, workflow_payload(spec["file"], spec["name"]))
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:300].replace(api_key, "***")
                print(f"n8n API error {exc.response.status_code} on {exc.request.url.path} "
                      f"({spec['name']}): {detail}", file=sys.stderr)
                status = 1
                continue
            except httpx.HTTPError as exc:
                print(f"Could not reach n8n at {base_url}: {type(exc).__name__}", file=sys.stderr)
                return 1

            webhook_url = f"{base_url}/webhook/{spec['webhook_path']}"
            print(f"Workflow '{spec['name']}' {action} and activated (id {wf_id}).")
            print(f"Production webhook: {webhook_url}")
            if args.write_env:
                upsert_env(webhook_url, args.env_file, spec["env_key"])
                print(f"Wrote {spec['env_key']} to {args.env_file}")
            else:
                print(f"Set {spec['env_key']}={webhook_url} in .env (or rerun with --write-env).")
    return status


if __name__ == "__main__":
    sys.exit(main())

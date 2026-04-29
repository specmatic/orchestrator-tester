#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def run_gh_api(path: str, attempts: int = 5, delay_seconds: int = 5) -> bytes:
    last_error = ""
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            ["gh", "api", path],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode == 0:
            return completed.stdout
        last_error = completed.stderr.decode("utf-8", errors="replace").strip()
        print(f"gh api failed for {path} (attempt {attempt}/{attempts}): {last_error}", flush=True)
        if attempt < attempts:
            time.sleep(delay_seconds)
    raise RuntimeError(f"gh api failed for {path}: {last_error}")


def load_json_from_gh(path: str) -> dict[str, Any]:
    return json.loads(run_gh_api(path).decode("utf-8"))


def parse_actions_run_url(url: str) -> tuple[str, str, str] | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[2] != "actions" or parts[3] != "runs":
        return None
    return parts[0], parts[1], parts[4]


def orchestrator_run_url_from_status(status: dict[str, Any], default_repository: str) -> str:
    target_url = str(status.get("target_url") or "")
    if parse_actions_run_url(target_url):
        owner, repo, _ = parse_actions_run_url(target_url) or ("", "", "")
        if f"{owner}/{repo}" == default_repository:
            return target_url

    description = str(status.get("description") or "")
    match = re.search(r"Orchestrator run (\d+)", description)
    if match:
        return f"https://github.com/{default_repository}/actions/runs/{match.group(1)}"
    return target_url


def as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def sum_result_ints(summary: dict[str, Any], key: str) -> int | None:
    results = summary.get("results")
    if not isinstance(results, list):
        return None

    total = 0
    found = False
    for result in results:
        if not isinstance(result, dict):
            continue
        value = as_int(result.get(key))
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


def summary_count(summary: dict[str, Any], key: str) -> int | None:
    value = as_int(summary.get(key))
    if value is not None:
        return value
    return sum_result_ints(summary, key)


def display(value: Any) -> Any:
    return value if value is not None else "n/a"


def render_summary_table(summary: dict[str, Any]) -> str:
    rows = [
        ("Conclusion", summary.get("conclusion", "n/a")),
        ("Total workflows", display(summary_count(summary, "total"))),
        ("Passed workflows", display(summary_count(summary, "passed_count"))),
        ("Failed workflows", display(summary_count(summary, "failed_count"))),
        ("Total tests", display(summary_count(summary, "total_tests"))),
        ("Failed tests", display(summary_count(summary, "failed_tests"))),
        ("Skipped tests", display(summary_count(summary, "skipped_tests"))),
        ("Duration", display(summary_count(summary, "duration_seconds"))),
    ]
    body = ["| Key | Value |", "| --- | --- |"]
    body.extend(f"| {key} | {value} |" for key, value in rows)

    results = summary.get("results")
    if isinstance(results, list) and results:
        body.extend(
            [
                "",
                "Workflow results:",
                "",
                "| Repository | Workflow | Status | Tests | Failed | Skipped | Details |",
                "| --- | --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for result in results:
            if not isinstance(result, dict):
                continue
            repository = f"{result.get('type', '')}/{result.get('repository', '')}".strip("/") or "n/a"
            details = str(result.get("details") or "n/a").replace("|", "\\|")
            if len(details) > 180:
                details = details[:177] + "..."
            body.append(
                "| "
                + " | ".join(
                    [
                        repository,
                        str(result.get("workflow", "n/a")),
                        str(result.get("status", "n/a")),
                        str(result.get("total_tests", "n/a")),
                        str(result.get("failed_tests", "n/a")),
                        str(result.get("skipped_tests", "n/a")),
                        details,
                    ]
                )
                + " |"
            )
    return "\n".join(body)


def find_orchestration_summary(orchestrator_run_url: str) -> dict[str, Any] | None:
    parsed = parse_actions_run_url(orchestrator_run_url)
    if parsed is None:
        return None

    owner, repo, run_id = parsed
    artifacts = load_json_from_gh(f"repos/{owner}/{repo}/actions/runs/{run_id}/artifacts")
    candidates = [
        artifact
        for artifact in artifacts.get("artifacts", [])
        if artifact.get("name") == "specmatic-outputs" and not artifact.get("expired")
    ]
    if not candidates:
        return None

    artifact_id = candidates[0]["id"]
    archive = run_gh_api(f"repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / "artifact.zip"
        zip_path.write_bytes(archive)
        with zipfile.ZipFile(zip_path) as archive_zip:
            archive_zip.extractall(temp_path)
        summary_path = temp_path / "outputs" / "orchestration-summary.json"
        if not summary_path.exists():
            return None
        return json.loads(summary_path.read_text(encoding="utf-8"))


def wait_for_orchestration_summary(orchestrator_run_url: str, timeout_seconds: int = 180, poll_seconds: int = 10) -> dict[str, Any] | None:
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            summary = find_orchestration_summary(orchestrator_run_url)
        except (OSError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            print(f"Could not read orchestrator artifact summary yet: {exc}", flush=True)
            summary = None
        if summary is not None:
            return summary
        print("Waiting for orchestrator artifact summary...")
        time.sleep(poll_seconds)
    return None


def latest_status(repo: str, sha: str, context: str) -> dict[str, Any] | None:
    combined = load_json_from_gh(f"repos/{repo}/commits/{sha}/status")
    matches = [
        status
        for status in combined.get("statuses", [])
        if status.get("context") == context
    ]
    return matches[0] if matches else None


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    context = os.environ["STATUS_CONTEXT"]
    timeout_seconds = int(os.environ.get("GATE_TIMEOUT_SECONDS", "3600"))
    poll_seconds = int(os.environ.get("GATE_POLL_SECONDS", "15"))
    started = time.time()
    latest: dict[str, Any] | None = None

    while time.time() - started < timeout_seconds:
        try:
            latest = latest_status(repo, sha, context)
        except (RuntimeError, json.JSONDecodeError) as exc:
            print(f"Could not read commit status yet: {exc}", flush=True)
            latest = None
        if latest:
            state = str(latest.get("state", "pending"))
            print(f"Current orchestrator gate state: {state}")
            if state != "pending":
                break
        else:
            print(f"Waiting for status context: {context}")
        time.sleep(poll_seconds)
    else:
        latest = {
            "state": "timeout",
            "description": f"Timed out waiting for {context}",
            "target_url": "",
        }

    state = str(latest.get("state", "unknown"))
    description = str(latest.get("description") or "")
    target_url = str(latest.get("target_url") or "")
    orchestrator_repository = os.environ.get("ORCHESTRATOR_REPOSITORY", "specmatic/specmatic-tests-orchestrator")
    orchestrator_run_url = orchestrator_run_url_from_status(latest, orchestrator_repository)
    status_url = os.environ.get("STATUS_URL") or f"{os.environ['GITHUB_SERVER_URL']}/{repo}/commit/{sha}"
    summary = wait_for_orchestration_summary(orchestrator_run_url) if orchestrator_run_url else None

    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
        handle.write("\n")
        handle.write(f"## Orchestrator Gate for enterprise run {os.environ['GITHUB_RUN_ID']} attempt {os.environ['GITHUB_RUN_ATTEMPT']} ({state})\n\n")
        handle.write(f"- Status context: `{context}`\n")
        handle.write(f"- State: `{state}`\n")
        if description:
            handle.write(f"- Description: {description}\n")
        handle.write(f"- Commit status: [{sha[:7]}]({status_url})\n")
        if target_url:
            handle.write(f"- Status details: {target_url}\n")
        if orchestrator_run_url and orchestrator_run_url != target_url:
            handle.write(f"- Orchestrator run: {orchestrator_run_url}\n")
        if summary is not None:
            handle.write("\n")
            handle.write(render_summary_table(summary))
            handle.write("\n")
        elif orchestrator_run_url:
            handle.write("\nCould not find `outputs/orchestration-summary.json` in the orchestrator artifact.\n")

    return 0 if state == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

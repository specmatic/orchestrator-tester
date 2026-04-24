#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "resources" / "test-executor.json"
OUTPUTS_DIR = ROOT / "outputs"
CONSOLIDATED_DIR = ROOT / "consolidated_output"


@dataclass
class CapturedRequest:
    method: str
    path: str
    body: dict[str, Any]


class LocalGitHubState:
    def __init__(self, jar_bytes: bytes) -> None:
        self.jar_bytes = jar_bytes
        self.requests: list[CapturedRequest] = []
        self.lock = threading.Lock()
        self._events: dict[str, threading.Event] = {
            "check-runs": threading.Event(),
            "dispatches": threading.Event(),
        }

    def add_request(self, method: str, path: str, body: dict[str, Any]) -> None:
        with self.lock:
            self.requests.append(CapturedRequest(method=method, path=path, body=body))
            if path.endswith("/check-runs"):
                self._events["check-runs"].set()
            if path.endswith("/dispatches"):
                self._events["dispatches"].set()

    def wait_for(self, key: str, timeout: float = 10.0) -> bool:
        return self._events[key].wait(timeout)


def build_jar() -> Path:
    with tempfile.TemporaryDirectory(prefix="orchestrator-tester-build-") as build_dir:
        env = os.environ.copy()
        env["ORCHESTRATOR_TESTER_BUILD_DIR"] = build_dir
        completed = subprocess.run(
            [sys.executable, "scripts/build_jar.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        jar_path = Path(completed.stdout.strip().splitlines()[-1])
        jar_bytes = jar_path.read_bytes()
        temp_jar = Path(tempfile.mkdtemp(prefix="orchestrator-tester-jar-")) / "orchestrator-tester.jar"
        temp_jar.write_bytes(jar_bytes)
        return temp_jar


def load_manifest() -> list[dict[str, Any]]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, list):
        raise ValueError("test-executor.json must contain a JSON array")
    return manifest


def ensure_clean_outputs() -> None:
    for path in (OUTPUTS_DIR, CONSOLIDATED_DIR):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def result_for_source(source: dict[str, Any], index: int) -> dict[str, Any]:
    result = source.get("result") or {}
    total = int(result.get("total", 1))
    passed_count = int(result.get("passed_count", total if result.get("passed", True) else 0))
    failed_count = int(result.get("failed_count", max(total - passed_count, 0)))
    passed = bool(result.get("passed", failed_count == 0))
    kind = str(result.get("kind", "sample"))
    return {
        "index": index,
        "type": source.get("type", "sample-project"),
        "name": source.get("name", f"source-{index}"),
        "description": source.get("description", ""),
        "branch": source.get("branch", "main"),
        "kind": kind,
        "passed": passed,
        "total": total,
        "passed_count": passed_count,
        "failed_count": failed_count,
    }


def write_source_outputs(manifest: list[dict[str, Any]], jar_url: str) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for index, source in enumerate(manifest, start=1):
        result = result_for_source(source, index)
        source_dir = OUTPUTS_DIR / f"{result['type']}-{result['name']}"
        source_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": {
                "type": result["type"],
                "name": result["name"],
                "description": result["description"],
                "branch": result["branch"],
            },
            "run": {
                "jar_url": jar_url,
                "kind": result["kind"],
                "passed": result["passed"],
                "total": result["total"],
                "passed_count": result["passed_count"],
                "failed_count": result["failed_count"],
            },
        }
        (source_dir / "result.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        outputs.append(payload)
    return outputs


def consolidate(outputs: list[dict[str, Any]], jar_url: str) -> dict[str, Any]:
    total_sources = len(outputs)
    passed_sources = sum(1 for item in outputs if item["run"]["passed"])
    failed_sources = total_sources - passed_sources
    total_tests = sum(int(item["run"]["total"]) for item in outputs)
    passed_tests = sum(int(item["run"]["passed_count"]) for item in outputs)
    failed_tests = sum(int(item["run"]["failed_count"]) for item in outputs)
    conclusion = "success" if failed_sources == 0 else "failure"

    summary = {
        "jar_url": jar_url,
        "conclusion": conclusion,
        "totals": {
            "sources": total_sources,
            "passed_sources": passed_sources,
            "failed_sources": failed_sources,
            "tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
        },
        "sources": outputs,
    }
    return summary


def render_html(summary: dict[str, Any]) -> str:
    rows = []
    for item in summary["sources"]:
        run = item["run"]
        rows.append(
            "<tr>"
            f"<td>{item['source']['type']}</td>"
            f"<td>{item['source']['name']}</td>"
            f"<td>{run['kind']}</td>"
            f"<td>{'PASS' if run['passed'] else 'FAIL'}</td>"
            f"<td>{run['passed_count']}/{run['total']}</td>"
            "</tr>"
        )
    rows_html = "\n".join(rows)
    totals = summary["totals"]
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>orchestrator-tester summary</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 2rem; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
      th {{ background: #f5f5f5; }}
    </style>
  </head>
  <body>
    <h1>orchestrator-tester summary</h1>
    <p><strong>Conclusion:</strong> {summary['conclusion']}</p>
    <ul>
      <li>Sources: {totals['sources']}</li>
      <li>Passed sources: {totals['passed_sources']}</li>
      <li>Failed sources: {totals['failed_sources']}</li>
      <li>Tests: {totals['tests']}</li>
      <li>Passed tests: {totals['passed_tests']}</li>
      <li>Failed tests: {totals['failed_tests']}</li>
    </ul>
    <table>
      <thead>
        <tr>
          <th>Type</th>
          <th>Name</th>
          <th>Profile</th>
          <th>Status</th>
          <th>Counts</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </body>
</html>
"""


def write_summary(summary: dict[str, Any]) -> None:
    CONSOLIDATED_DIR.mkdir(parents=True, exist_ok=True)
    (CONSOLIDATED_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (CONSOLIDATED_DIR / "summary.html").write_text(render_html(summary), encoding="utf-8")


def github_request(base_url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url=f"{base_url}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def send_callback(base_url: str, summary: dict[str, Any]) -> None:
    conclusion = summary["conclusion"]
    check_body = {
        "name": "orchestrator-tester",
        "head_sha": "local-demo-sha",
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": "orchestrator-tester summary",
            "summary": f"Conclusion: {conclusion}",
        },
    }
    dispatch_body = {
        "event_type": "specmatic-orchestrator-result",
        "client_payload": {
            "summary": summary,
        },
    }
    github_request(base_url, "/repos/specmatic/orchestrator-tester/check-runs", check_body)
    github_request(base_url, "/repos/specmatic/orchestrator-tester/dispatches", dispatch_body)


class DemoRequestHandler(BaseHTTPRequestHandler):
    state: LocalGitHubState

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/orchestrator-tester.jar":
            self.send_response(200)
            self.send_header("Content-Type", "application/java-archive")
            self.send_header("Content-Length", str(len(self.state.jar_bytes)))
            self.end_headers()
            self.wfile.write(self.state.jar_bytes)
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            body = {"raw": raw_body.decode("utf-8", errors="replace")}
        self.state.add_request("POST", self.path, body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def start_server(state: LocalGitHubState) -> tuple[ThreadingHTTPServer, str]:
    handler = type("Handler", (DemoRequestHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def main() -> int:
    jar_path = build_jar()
    jar_bytes = jar_path.read_bytes()
    state = LocalGitHubState(jar_bytes=jar_bytes)
    server, base_url = start_server(state)
    jar_url = f"{base_url}/orchestrator-tester.jar"

    try:
        ensure_clean_outputs()
        manifest = load_manifest()
        outputs = write_source_outputs(manifest, jar_url)
        summary = consolidate(outputs, jar_url)
        write_summary(summary)
        send_callback(base_url, summary)

        if not state.wait_for("check-runs") or not state.wait_for("dispatches"):
            raise RuntimeError("Callback requests were not captured in time")

        print(f"Built jar: {jar_path}")
        print(f"Used manifest: {MANIFEST_PATH}")
        print(f"Wrote outputs to: {OUTPUTS_DIR}")
        print(f"Wrote consolidated summary to: {CONSOLIDATED_DIR}")
        print("Captured callback requests:")
        for item in state.requests:
            print(f"- {item.method} {item.path}: {json.dumps(item.body, indent=2, sort_keys=True)}")
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())

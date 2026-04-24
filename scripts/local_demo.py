#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DemoServer(HTTPServer):
    def __init__(self, server_address: tuple[str, int]) -> None:
        super().__init__(server_address, _DemoHandler)
        self.requests: list[dict[str, Any]] = []
        self.event = threading.Event()


class _DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/orchestrator-tester.jar":
            body = b"fake jar bytes"
            self.send_response(200)
            self.send_header("Content-Type", "application/java-archive")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload: Any = json.loads(body)
        except json.JSONDecodeError:
            payload = body

        self.server.requests.append(  # type: ignore[attr-defined]
            {
                "path": self.path,
                "payload": payload,
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")
        if len(self.server.requests) >= 2:  # type: ignore[attr-defined]
            self.server.event.set()  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def build_jar() -> Path:
    subprocess.run([sys.executable, "orchestrator-tester/scripts/build_jar.py"], cwd=ROOT, check=True)
    return ROOT / "orchestrator-tester" / "build" / "orchestrator-tester.jar"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="orchestrator-tester-") as temp_dir:
        temp_path = Path(temp_dir)
        event_path = temp_path / "event.json"
        sample_config = ROOT / "orchestrator-tester" / "resources" / "test-executor.json"

        jar_path = build_jar()

        server = _DemoServer(("127.0.0.1", 0))
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            jar_url = f"http://127.0.0.1:{port}/orchestrator-tester.jar"
            event_path.write_text(
                json.dumps(
                    {
                        "action": "specmatic-enterprise-jar-ready",
                        "client_payload": {
                            "jar_url": jar_url,
                            "enterprise_repository": "specmatic/orchestrator-tester",
                            "enterprise_sha": "deadbeef",
                            "enterprise_run_id": "1",
                            "enterprise_run_attempt": "1",
                        },
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "ENTERPRISE_CALLBACK_TOKEN": "dummy-token",
                    "ENTERPRISE_REPOSITORY": "specmatic/orchestrator-tester",
                    "ENTERPRISE_SHA": "deadbeef",
                    "ENTERPRISE_RUN_ID": "1",
                    "ENTERPRISE_RUN_ATTEMPT": "1",
                    "ORCHESTRATOR_RUN_URL": "http://example.local/orchestrator/run/1",
                    "ORCHESTRATOR_RUN_ID": "99",
                    "ORCHESTRATOR_RUN_ATTEMPT": "1",
                    "GITHUB_API_BASE_URL": f"http://127.0.0.1:{port}",
                    "GITHUB_EVENT_NAME": "repository_dispatch",
                    "GITHUB_EVENT_PATH": str(event_path),
                    "SPECMATIC_JAR_URL": jar_url,
                    "SPEC_OUTPUTS_DIR": str(temp_path / "outputs"),
                    "SPEC_CONSOLIDATED_DIR": str(temp_path / "consolidated_output"),
                    "ORCHESTRATOR_SAMPLE_CONFIG": str(sample_config),
                }
            )
            subprocess.run([sys.executable, "scripts/orchestrate.py"], cwd=ROOT, env=env, check=True)

            if not server.event.wait(5):
                raise SystemExit("Timed out waiting for callback POSTs")

            print(f"Built jar: {jar_path}")
            print("Captured callback requests:")
            for request in server.requests:
                print(json.dumps(request, indent=2, sort_keys=True))
            return 0
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())

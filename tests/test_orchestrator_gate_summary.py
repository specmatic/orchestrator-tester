from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "orchestrator_gate_summary.py"
SPEC = importlib.util.spec_from_file_location("orchestrator_gate_summary", SCRIPT_PATH)
assert SPEC is not None
orchestrator_gate_summary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = orchestrator_gate_summary
SPEC.loader.exec_module(orchestrator_gate_summary)


class OrchestratorGateSummaryTest(unittest.TestCase):
    def test_parse_actions_run_url(self) -> None:
        parsed = orchestrator_gate_summary.parse_actions_run_url(
            "https://github.com/specmatic/specmatic-tests-orchestrator/actions/runs/25054623103"
        )

        self.assertEqual(parsed, ("specmatic", "specmatic-tests-orchestrator", "25054623103"))

    def test_orchestrator_run_url_from_status_prefers_description_when_details_points_to_tester(self) -> None:
        url = orchestrator_gate_summary.orchestrator_run_url_from_status(
            {
                "target_url": "https://github.com/specmatic/orchestrator-tester/actions/runs/25096082367",
                "description": "Orchestrator run 25096088116 failed",
            },
            "specmatic/specmatic-tests-orchestrator",
        )

        self.assertEqual(
            url,
            "https://github.com/specmatic/specmatic-tests-orchestrator/actions/runs/25096088116",
        )

    def test_orchestrator_run_url_from_status_uses_target_when_it_is_orchestrator_run(self) -> None:
        url = orchestrator_gate_summary.orchestrator_run_url_from_status(
            {
                "target_url": "https://github.com/specmatic/specmatic-tests-orchestrator/actions/runs/25096088116",
                "description": "Orchestrator run 25096088116 failed",
            },
            "specmatic/specmatic-tests-orchestrator",
        )

        self.assertEqual(
            url,
            "https://github.com/specmatic/specmatic-tests-orchestrator/actions/runs/25096088116",
        )

    def test_render_summary_table_uses_root_counts_and_workflow_rows(self) -> None:
        summary = {
            "conclusion": "failure",
            "total": 2,
            "passed_count": 0,
            "failed_count": 2,
            "total_tests": 233,
            "failed_tests": 6,
            "skipped_tests": 5,
            "results": [
                {
                    "type": "sample-project",
                    "repository": "contract-tests",
                    "workflow": ".github/workflows/gradle.yml",
                    "status": "failed",
                    "total_tests": 227,
                    "failed_tests": 5,
                    "skipped_tests": 4,
                    "duration_seconds": 118,
                    "details": "test failures detected",
                },
                {
                    "type": "sample-project",
                    "repository": "asyncapi-tests",
                    "workflow": ".github/workflows/gradle.yml",
                    "status": "failed",
                    "total_tests": 6,
                    "failed_tests": 1,
                    "skipped_tests": 1,
                    "duration_seconds": 34,
                    "details": "test failures detected",
                },
            ],
        }

        markdown = orchestrator_gate_summary.render_summary_table(summary)

        self.assertIn("| Total workflows | 2 |", markdown)
        self.assertIn("| Failed workflows | 2 |", markdown)
        self.assertIn("| Total tests | 233 |", markdown)
        self.assertIn("| Failed tests | 6 |", markdown)
        self.assertIn("| Skipped tests | 5 |", markdown)
        self.assertIn("| Duration | 152 |", markdown)
        self.assertIn("| sample-project/contract-tests | .github/workflows/gradle.yml | failed | 227 | 5 | 4 | test failures detected |", markdown)

    def test_wait_for_orchestration_summary_retries_until_artifact_is_available(self) -> None:
        calls = {"count": 0}
        original_find = orchestrator_gate_summary.find_orchestration_summary
        original_sleep = orchestrator_gate_summary.time.sleep
        try:
            def fake_find(url: str):
                calls["count"] += 1
                if calls["count"] < 3:
                    return None
                return {"conclusion": "failure", "total": 2}

            orchestrator_gate_summary.find_orchestration_summary = fake_find
            orchestrator_gate_summary.time.sleep = lambda seconds: None

            summary = orchestrator_gate_summary.wait_for_orchestration_summary(
                "https://github.com/specmatic/specmatic-tests-orchestrator/actions/runs/1",
                timeout_seconds=30,
                poll_seconds=1,
            )
        finally:
            orchestrator_gate_summary.find_orchestration_summary = original_find
            orchestrator_gate_summary.time.sleep = original_sleep

        self.assertEqual(summary, {"conclusion": "failure", "total": 2})
        self.assertEqual(calls["count"], 3)

    def test_wait_for_orchestration_summary_retries_transient_read_errors(self) -> None:
        calls = {"count": 0}
        original_find = orchestrator_gate_summary.find_orchestration_summary
        original_sleep = orchestrator_gate_summary.time.sleep
        try:
            def fake_find(url: str):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("api temporarily unavailable")
                return {"conclusion": "success", "total": 1}

            orchestrator_gate_summary.find_orchestration_summary = fake_find
            orchestrator_gate_summary.time.sleep = lambda seconds: None

            summary = orchestrator_gate_summary.wait_for_orchestration_summary(
                "https://github.com/specmatic/specmatic-tests-orchestrator/actions/runs/1",
                timeout_seconds=30,
                poll_seconds=1,
            )
        finally:
            orchestrator_gate_summary.find_orchestration_summary = original_find
            orchestrator_gate_summary.time.sleep = original_sleep

        self.assertEqual(summary, {"conclusion": "success", "total": 1})
        self.assertEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()

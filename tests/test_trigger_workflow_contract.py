from __future__ import annotations

import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "trigger-orchestrator.yml"


class TriggerWorkflowContractTest(unittest.TestCase):
    def test_enterprise_version_defaults_to_explicit_dummy_selector(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("default: 0.0.0-DUMMY", workflow)
        self.assertIn("DEFAULT_DUMMY_ENTERPRISE_VERSION: 0.0.0-DUMMY", workflow)
        self.assertIn("DEFAULT_DUMMY_JAR_URL: https://repo1.maven.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar", workflow)
        self.assertNotIn("run_parallel", workflow)
        self.assertNotIn("RUN_PARALLEL", workflow)

    def test_blank_enterprise_version_fails_instead_of_defaulting_to_dummy_flow(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("ENTERPRISE_VERSION is required. Use ${DEFAULT_DUMMY_ENTERPRISE_VERSION} for the default tester flow.", workflow)
        self.assertIn('if [ -z "${enterprise_selector}" ]; then', workflow)

    def test_workflow_replicates_enterprise_os_scoped_orchestrator_gates(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("matrix:", workflow)
        self.assertIn("os: [ubuntu-latest, windows-latest]", workflow)
        self.assertIn("Ubuntu - Specmatic Orchestrator Gate", workflow)
        self.assertIn("Windows - Specmatic Orchestrator Gate", workflow)
        self.assertIn("https://api.github.com/repos/${GITHUB_REPOSITORY}/statuses/${GITHUB_SHA}", workflow)
        self.assertIn("Authorization: Bearer ${STATUS_TOKEN}", workflow)
        self.assertIn("--arg configuration \"${configuration}\"", workflow)
        self.assertIn("--arg repository \"${GITHUB_REPOSITORY}\"", workflow)
        self.assertIn("repository_label=\"${repository_name^}\"", workflow)
        self.assertIn("--arg repository_name \"${repository_label}\"", workflow)
        self.assertIn("--arg run_number \"${GITHUB_RUN_NUMBER}\"", workflow)
        self.assertIn("--arg jar_url \"${jar_url}\"", workflow)
        self.assertIn("--arg test_executor_json \"${test_executor_json}\"", workflow)
        self.assertIn("enterprise_options: {", workflow)
        self.assertIn("orchestrator_options: (", workflow)
        self.assertIn("test_executor_json: $test_executor_json", workflow)
        self.assertNotIn("test_executor_path", workflow)
        self.assertNotIn("run_parallel", workflow)
        self.assertIn("callbacks update each gate's Details link", workflow)
        self.assertNotIn("needs.build-and-trigger.outputs.status_context", workflow)
        self.assertNotIn("Wait for orchestrator gate", workflow)


if __name__ == "__main__":
    unittest.main()

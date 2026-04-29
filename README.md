# Orchestrator Tester

`orchestrator-tester` is a small side project that can be used to exercise the
Specmatic orchestrator flow end-to-end.

It is intentionally simple:

1. Trigger the orchestrator with a fake `repository_dispatch` payload.
2. Use a small public dummy jar by default for GitHub workflow tests.
3. Produce three sample test-source outputs from a synthetic orchestrator manifest.
4. Update the pending gate status in this side project.

## Structure

- `src/Main.java`: tiny Java entrypoint for the jar
- `scripts/build_jar.py`: compiles and packages the jar
- `scripts/local_demo.py`: runs the end-to-end dry run locally
- `resources/test-executor.json`: three sample source descriptors and their result profiles
- `.github/workflows/trigger-orchestrator.yml`: production workflow sketch

## Local run

```bash
python3 scripts/local_demo.py
```

That simulates the production flow locally:

- builds the jar
- runs three sample test sources from `resources/test-executor.json`
- writes `outputs/` and `consolidated_output/`
- sends the callback to a local fake GitHub server

## Local testing

To build just the jar:

```bash
python3 scripts/build_jar.py
```

To exercise the full local dry-run:

```bash
python3 scripts/local_demo.py
```

That local run:

- builds `build/orchestrator-tester.jar`
- uses the built jar's absolute file path as the jar reference
- uses `resources/test-executor.json`
- generates `outputs/` and `consolidated_output/`
- prints the callback payloads captured by the local server

## Result profiles

Each entry in [`resources/test-executor.json`](./resources/test-executor.json) can include a `result` block such as:

```json
{
  "kind": "smoke",
  "passed": true,
  "total": 5,
  "passed_count": 5,
  "failed_count": 0
}
```

That block controls what the local demo writes into the corresponding `result.json`.
You can change `passed`, `passed_count`, `failed_count`, or `total` to simulate pass/fail scenarios for each sample project.

## Production workflow shape

The intended tester flow in GitHub Actions is:

1. Create a pending gate commit status.
2. Dispatch `specmatic/specmatic-tests-orchestrator` with:
   - a dummy `jar_url` by default: `https://repo1.maven.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar`
   - `enterprise_version=0.0.0-DUMMY` by default
   - `test_executor_path=resources/orchestrator-tester-test-executor.json` by default
   - `enterprise_repository=specmatic/orchestrator-tester`
   - `enterprise_sha`
   - `enterprise_run_id`
   - `enterprise_run_attempt`
3. Let the orchestrator publish `outputs/orchestration-summary.json` and update the original pending status directly.

To test a real Enterprise artifact, provide `ENTERPRISE_VERSION` when manually running the workflow. Supported values include `1.12.1-SNAPSHOT`, `SNAPSHOT`, `RELEASE`, a Specmatic Enterprise repository URL, or a direct Enterprise jar URL. When `ENTERPRISE_VERSION` is provided, the tester does not send the dummy jar URL; the orchestrator resolves the jar from the selector. Leave `ORCHESTRATOR_TEST_EXECUTOR_PATH` blank in that case to use the orchestrator's default real sample-project manifest, or provide a path to test another manifest.

The workflow file in [`.github/workflows/trigger-orchestrator.yml`](./.github/workflows/trigger-orchestrator.yml) now does this by:

- using the small public dummy jar and synthetic manifest when `ENTERPRISE_VERSION` is blank
- forwarding `ENTERPRISE_VERSION` without the dummy jar when you want the orchestrator to resolve a real Enterprise artifact
- optionally forwarding `ORCHESTRATOR_TEST_EXECUTOR_PATH` when you want to test a specific manifest in the orchestrator repo
- dispatching `specmatic/specmatic-tests-orchestrator`
- showing a separate `orchestrator-gate` job while the stable `Specmatic Orchestrator Gate` commit status is `pending`
- downloading the orchestrator `specmatic-outputs` artifact and appending `outputs/orchestration-summary.json` results to the `orchestrator-gate` job summary

## Test in GitHub Actions

1. Push this repository to GitHub.
2. Run the workflow named `Build and Trigger Orchestrator`.
3. Confirm the orchestrator workflow was dispatched with the default dummy jar and synthetic manifest.
4. Confirm the orchestrator run produced:
   - `outputs/`
   - `outputs/orchestration-summary.json`
   - `outputs/index.html`
   - the direct gate status update back to `specmatic/orchestrator-tester`
5. Confirm the `orchestrator-gate` job is visible in the workflow graph while the orchestrator is running.
6. Confirm the `orchestrator-gate` summary contains the final state, orchestrator run link, and orchestration result counts.

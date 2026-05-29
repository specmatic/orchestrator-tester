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
- `resources/test-executor.json`: caller-owned synthetic test executor manifest embedded into the orchestrator payload
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

1. Create pending OS-scoped gate commit statuses.
2. Dispatch `specmatic/specmatic-tests-orchestrator` with:
   - a dummy `jar_url` by default: `https://repo1.maven.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar`
   - `enterprise_version=0.0.0-DUMMY` by default
   - `orchestrator_options.test_executor_json` read from [`resources/test-executor.json`](./resources/test-executor.json)
   - `enterprise_repository=specmatic/orchestrator-tester`
   - `enterprise_sha`
   - `enterprise_run_id`
   - `enterprise_run_attempt`
3. Let the orchestrator publish `outputs/orchestration-summary.json` and update the original pending statuses directly.

`ENTERPRISE_VERSION` must not be blank. Use the default `0.0.0-DUMMY` value for the lightweight tester flow. To test a real Enterprise artifact, replace it with a supported selector such as `1.12.1-SNAPSHOT`, `SNAPSHOT`, `RELEASE`, a Specmatic Enterprise repository URL, or a direct Enterprise jar URL. When a real selector is provided, the tester does not send the dummy jar URL; the orchestrator resolves the jar from the selector. The tester still owns the manifest and embeds its JSON content in the dispatch payload.

The workflow file in [`.github/workflows/trigger-orchestrator.yml`](./.github/workflows/trigger-orchestrator.yml) now does this by:

- using the small public dummy jar and synthetic manifest when `ENTERPRISE_VERSION` is `0.0.0-DUMMY`
- failing early when `ENTERPRISE_VERSION` is blank
- forwarding `ENTERPRISE_VERSION` without the dummy jar when you want the orchestrator to resolve a real Enterprise artifact
- embedding [`resources/test-executor.json`](./resources/test-executor.json) as `orchestrator_options.test_executor_json` so the orchestrator stays caller-agnostic
- dispatching `specmatic/specmatic-tests-orchestrator` once for Ubuntu and once for Windows
- relying on the orchestrator callback to update the OS-scoped gate statuses, including the Details link to the exact orchestrator run
- writing a short trigger summary with the gate contexts and orchestrator workflow link

## Test in GitHub Actions

1. Push this repository to GitHub.
2. Run the workflow named `Build and Trigger Orchestrator`.
3. Confirm the orchestrator workflow was dispatched with the default dummy jar and synthetic manifest.
4. Confirm the orchestrator run produced:
   - `outputs/`
   - `outputs/orchestration-summary.json`
   - `outputs/index.html`
   - the direct gate status update back to `specmatic/orchestrator-tester`
5. Confirm the commit status popover shows `Ubuntu - Specmatic Orchestrator Gate` and `Windows - Specmatic Orchestrator Gate`.
6. Confirm each gate's Details link points to the exact orchestrator run after the callback completes.

## Manual trigger and results

To test the full callback flow manually:

1. Open **Actions -> Build and Trigger Orchestrator**.
2. Click **Run workflow**.
3. Leave `ENTERPRISE_VERSION` as `0.0.0-DUMMY` for the lightweight tester flow, or enter a real Enterprise selector/jar URL.
4. Leave `TEST_EXECUTOR_JSON_PATH` as `resources/test-executor.json` unless you want to embed a different caller-owned manifest.
During the run, the workflow summary shows the pending Ubuntu and Windows gate contexts plus the orchestrator workflow link. The orchestrator always dispatches the target workflows from the embedded manifest in parallel. After the orchestrator callback completes, see the final result in the commit status popover on the repository main page. Each gate's **Details** link points to the exact `specmatic-tests-orchestrator` run, whose artifacts include `outputs/orchestration-summary.json` and `outputs/index.html`.

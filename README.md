# Orchestrator Tester

`orchestrator-tester` is a small side project that can be used to exercise the
Specmatic orchestrator flow end-to-end.

It is intentionally simple:

1. Build a tiny jar.
2. Trigger the orchestrator with a fake `repository_dispatch` payload.
3. Produce three sample test-source outputs from the side-project manifest.
4. Consolidate them into `consolidated_output/summary.json` and `summary.html`.
5. Update the pending gate status in this side project.

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

The intended production flow in a standalone `orchestrator-tester` repository is:

1. Build the jar.
2. Upload the jar to a reachable URL.
3. Dispatch `specmatic/specmatic-tests-orchestrator` with:
   - `jar_url`
   - `enterprise_repository=specmatic/orchestrator-tester`
   - `enterprise_sha`
   - `enterprise_run_id`
   - `enterprise_run_attempt`
   - `enterprise_version`
   - optional `ORCHESTRATOR_TEST_EXECUTOR_PATH` if you want the orchestrator to use a non-default manifest
4. Let the orchestrator run the sample test sources and update the original pending status directly.

The workflow file in [`.github/workflows/trigger-orchestrator.yml`](./.github/workflows/trigger-orchestrator.yml) now does this by:

- building the jar
- creating a release asset for `orchestrator-tester.jar`
- using the release asset download URL as `jar_url`
- optionally forwarding `ORCHESTRATOR_TEST_EXECUTOR_PATH` when you want to test a specific manifest in the orchestrator repo
- forwarding `ENTERPRISE_VERSION` so the orchestrator can resolve the Enterprise snapshot under test
- dispatching `specmatic/specmatic-tests-orchestrator`
- waiting for the original commit status context to move out of `pending`, then appending the final gate result to this workflow summary

## Test in GitHub Actions

1. Push this repository to GitHub.
2. Run the workflow named `Build and Trigger Orchestrator`.
3. Confirm a release asset was created for `orchestrator-tester.jar`.
4. Confirm the orchestrator workflow was dispatched.
5. Confirm the orchestrator run produced:
   - `outputs/`
   - `outputs/orchestration-summary.json`
   - `outputs/index.html`
   - the direct gate status update back to `specmatic/orchestrator-tester`
6. Confirm the `Build and Trigger Orchestrator` summary contains a second gate section with the final state and orchestrator run link.

If the repository is private, use a signed or authenticated jar URL instead of a public release asset URL.

# Unity CI and licensing

## License constraints

The available license is Unity Student (named-user licensing). There is no
serial key and no `.ulf` file; the activation file is
`UnityEntitlementLicense.xml`. GameCI v4 supports `.ulf` files, serial keys,
floating licenses and Personal accounts
(<https://game.ci/docs/github/activation/>), so the Student license cannot
activate inside GameCI on a GitHub-hosted runner.

Unity Editor Software Terms §2.8 forbid third parties from running the editor
on cloud or remote servers, and Pro assigned seats are not license-request
targets (<https://docs.unity.com/en-us/hub/manage-license>). Running Unity on a
GitHub-hosted runner is therefore unavailable on both licensing and technical
grounds.

## Runner modes

`unity.yml` takes `unity-runner`:

| Value         | Behaviour                                                                 |
| ------------- | ------------------------------------------------------------------------- |
| `none`        | Integrity only. Unity test/build jobs are skipped with a notice.          |
| `self-hosted` | Unity runs on the private repository's self-hosted Windows runner.        |
| `gameci`      | GameCI test and build jobs run; requires a GameCI-supported license.      |
| `uba`         | Unity Build Automation builds the commit on Unity-hosted Windows machines.|

The generated Unity caller uses `unity-runner: self-hosted`. The reusable
workflow's input default is `none`, so a caller without a runner still gets the
editor-free integrity gate. The template renders a platform layer to place at a
Unity project root; it is not a complete Unity project. Integrity always runs on `ubuntu-latest` and never
needs an editor. The `changes` job on Ubuntu compares the event's base and head
commits and reports whether `Assets/`, `Packages/` or `ProjectSettings/`
changed. Push events use `github.event.before` (all-zero or forced pushes run
the tests), pull requests use the base SHA, and schedule or manual runs always
run. When nothing relevant changed, the Unity job stays green and prints
`::notice::no Unity-relevant changes`.

Builds are excluded from default verification. The `build` input (default
false) runs `devctl unity build` on the self-hosted runner, zips
`artifacts/unity-build` to `artifacts/ProjectDelta-<ref>.zip`, and uploads it as
the `unity-build` artifact. Callers enable it on tags and nightly runs.

Job and check names: the Unity caller names its job `platform-verify`, so the
checks are `platform-verify / integrity` and `platform-verify / tests`.
`platform-verify / check` does not exist for Unity repositories. A Unity
repository that also wants the `mise run check` gate adds a `platform-check`
caller that invokes `ci.yml` with `run-tests: false`; `project-delta` does,
producing `platform-check / check`.

## Self-hosted runner

Use a repository-level runner for the private `project-delta` repository only.

1. Install the runner in `C:/ghr/runner` and register it with labels
   `[self-hosted, windows, unity]` and work folder `C:/ghr/work`. GitHub shows the
   custom `windows` label merged into the built-in `Windows` label; matching is
   case-insensitive, so `runs-on: [self-hosted, windows, unity]` still selects it.
2. Run it as the logged-in user, not as a service. Creating a logon task with
   `schtasks /SC ONLOGON` requires administrator rights, so autostart uses a
   Startup-folder script instead:
   `%APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup/github-runner-project-delta.cmd`.
   The named-user license works because the editor runs on the license holder's
   own machine. `C:/ghr/README.txt` documents stop, start, and removal.
3. Do not delete `Library/` between builds. The checkout uses `clean: false` so
   the next run reuses the incremental import.
4. The job concurrency group is `unity-${{ github.repository }}` with
   `cancel-in-progress: false`, so only one Unity run touches the project at a
   time.
5. Never attach this runner to a public repository.

The runner machine needs `uv` on `PATH`; the job checks it with `uv --version`.
Unity itself is discovered by `devctl` from `unity.editorPath`, the
`UNITY_EDITOR_PATH` environment variable, or the Hub editor directory. The
self-hosted job checks out `ghdtmdwns133/dev-platform` at the caller's
`platform-ref` into `.dev-platform` and runs
`uv run --project .dev-platform/cli devctl ...` with the consumer repository as
the working directory.

## GameCI mode

GameCI remains implemented for accounts that hold a supported license. Enable
it with `unity-runner: gameci` and provide `UNITY_LICENSE`, `UNITY_EMAIL` and
`UNITY_PASSWORD`. If the `6000.5.1f1` image is unavailable, the job fails and
the report marks Unity execution as blocked. The platform never sets GameCI as
the default.

## Unity Build Automation (UBA)

Role split:

- The self-hosted PC runner remains the primary Unity CI: EditMode and
  PlayMode tests on every relevant push and nightly runs. It uses the student's
  named-user license on the license holder's machine.
- UBA is the auxiliary path. It produces the release player and can build on
  demand while the PC is off. Unity operates the build machines, so the
  student named-user license is not involved and no local editor is needed.

The REST API is `https://build-api.cloud.unity3d.com/api/v1` (Build Automation
API 2.0.0). Start a build with
`POST /orgs/{orgid}/projects/{projectid}/buildtargets/{buildtargetid}/builds`
and `{"commit": "<sha>"}`, poll `GET .../builds/{number}`, and download
`links.download_primary` (a relative link returns `303` with the signed storage
URL in the JSON body). Authentication is the API key in
`Authorization: Bearer <key>`; older documentation describes the legacy
`Authorization: Basic <key>` form, selectable with `UNITY_BUILD_API_AUTH=basic`.
References:

- <https://build-api.cloud.unity3d.com/docs/>
- <https://docs.unity.com/en-us/build-automation/build-automation-api>
- <https://docs.unity.com/en-us/build-automation/run-builds>

Free tier: 200 Windows build minutes per month (Windows Micro), 100 Mac and
100 Linux minutes, two concurrent machines, and 25 GB of DevOps storage. The
minutes renew monthly. When the free minutes are exhausted, builds stop unless
the organization has a payment method on file; there is no charge without a
payment method. See
<https://support.unity.com/hc/en-us/articles/34748492914964-Understanding-of-New-Unity-DevOps-Pricing-starting-from-Mar-1-2026>
and
<https://support.unity.com/hc/en-us/articles/6093104438932-How-does-the-pricing-for-Unity-Build-Automation-work>.

Dashboard setup (repeat if the project, repository link or API key changes):

1. At <https://cloud.unity.com/home/cloud-build>, open **DevOps > Build
   Automation** and link the Unity Cloud project to the GitHub repository.
2. Create a Windows build target for the release branch (for `project-delta`,
   Unity `6000.5.1f1`, `StandaloneWindows64`).
3. Copy the organization id (the org `coreForeignKey`/`orgFk`, not the display
   name), the project id (the project `guid`) and the build target id.
4. Copy the API key from **Build Automation Settings**.
5. Store the values as Actions secrets `UNITY_BUILD_API_KEY`,
   `UNITY_BUILD_ORG_ID` and `UNITY_BUILD_PROJECT_ID`, either through Doppler
   (`<repo>/ci`) or with `gh secret set <NAME> -R ghdtmdwns133/<repo>`. Never
   commit them.
6. Optionally set `unity.cloudBuild.target` in `.devplatform/config.json`
   (and `unity.cloudBuild.timeoutMinutes`, default 90) or pass
   `cloud-build-target` to the reusable workflow.

The CLI entry point is:

```bash
devctl unity cloud-build --commit <sha> [--target <id>] [--timeout-min 90] [--download DIR]
```

It reads the three `UNITY_BUILD_*` variables, polls every 30 seconds (backing
off to five minutes and honouring `Retry-After` on `429`), writes
`artifacts/reports/unity/cloud-build.json` and downloads the primary artifact
to `artifacts/reports/unity/cloud-build/` by default. Exit codes: 0 success,
1 build failure/cancelled, 2 missing target or credentials, 3 timeout or
transport/download failure. `UNITY_BUILD_API_BASE` overrides the base URL for
local tests; `UNITY_BUILD_POLL_SECONDS` overrides the poll interval.

When the release workflow receives `unity_build_api_key`,
`unity_build_org_id` and `unity_build_project_id`, a `build-cloud` job on
`ubuntu-latest` supplies the release asset. Without all three secrets it prints
`::notice::Unity Build Automation not configured; using self-hosted build` and
runs the self-hosted build command. The generated Unity caller does not ship a
separate cloud-build workflow; project-delta has its own `cloud-build.yml`
caller for an on-demand UBA build without the PC.

## Local verification

```bash
cd C:/dev/project-delta
uv run --project C:/dev/dev-platform/cli devctl verify --profile unity
```

A generated Unity layer can run the same CLI without a local platform checkout:

```bash
uvx --from git+https://github.com/ghdtmdwns133/dev-platform@v1#subdirectory=cli \
  devctl verify --profile unity
```

- `project-delta` currently sets `unity.testPlatforms` to `["EditMode"]`, so CI
  and local `verify` run EditMode only. The template's Unity layer defaults to
  both modes; a generated Unity repository must set `testPlatforms` explicitly
  for the tests it can actually run. PlayMode needs a desktop session and
  injects input, so enabling it is a deliberate configuration change, not part
  of the default gate.
- EditMode runs with `-batchmode -nographics`. PlayMode, when enabled, runs with
  `-batchmode` only; `-nographics` is omitted because PlayMode needs graphics
  initialization. `-quit` is not passed to test runs; the editor exits after the
  tests.
- Test results are NUnit3 XML under `artifacts/reports/unity/`. A run passes
  when the root has `failed="0"` and `result="Passed"`.
- Coverage is read from `coverage-*/Report/Summary.xml`; a missing report is a
  warning, not a failure. The self-hosted test job uploads the OpenCover
  results to Codecov when `CODECOV_TOKEN` is set.
- `--unity-build` produces `artifacts/unity-build/ProjectDelta.exe`; success
  requires exit 0, the executable, and a size above 1 MiB.
- `unity odin` runs the bridge described in the Unity template's
  `docs/UNITY-ADAPTER.md`. Without Odin the report status is `skipped` and the
  command exits 0.

The known flaky test
`ActiveInterceptBot_ReachesRealSuccess_WithinMissionBudget` is recorded in the
project README. If only that test fails, report it as a pre-existing flake; do
not disable or edit it.

## Odin

Odin is not vendored into `project-delta`: the coursework rules forbid paid
assets and the Sirenix EULA forbids redistributing Odin tooling. The bridge
therefore uses reflection only and proves the `skipped` path. Real validation
requires a locally installed Sirenix education license and runs against a copy
of the project under `artifacts/tmp/`.

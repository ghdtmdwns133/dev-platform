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

| Value        | Behaviour                                                                 |
| ------------ | ------------------------------------------------------------------------- |
| `none`       | Integrity only. The Unity jobs are skipped with a notice.                 |
| `self-hosted`| Unity runs on the private repository's self-hosted Windows runner.        |
| `gameci`     | GameCI test and build jobs run; requires a GameCI-supported license.     |

Integrity always runs on `ubuntu-latest` and never needs an editor. The
`changes` job on Ubuntu compares the event's base and head commits and reports
whether `Assets/`, `Packages/` or `ProjectSettings/` changed. Push events use
`github.event.before` (all-zero or forced pushes run the tests), pull requests
use the base SHA, and schedule or manual runs always run. When nothing relevant
changed, the Unity job stays green and prints
`::notice::no Unity-relevant changes`.

Builds are excluded from default verification. The `build` input (default
false) runs `devctl unity build` on the self-hosted runner, zips
`artifacts/unity-build` to `artifacts/ProjectDelta-<ref>.zip`, and uploads it as
the `unity-build` artifact. Callers enable it on tags and nightly runs.

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
`UNITY_EDITOR_PATH` environment variable, or the Hub editor directory.

## GameCI mode

GameCI remains implemented for accounts that hold a supported license. Enable
it with `unity-runner: gameci` and provide `UNITY_LICENSE`, `UNITY_EMAIL` and
`UNITY_PASSWORD`. If the `6000.5.1f1` image is unavailable, the job fails and
the report marks Unity execution as blocked. The platform never sets GameCI as
the default.

## Local verification

```bash
cd C:/dev/project-delta
uv run --project C:/dev/dev-platform/cli devctl verify --profile unity
```

- EditMode runs with `-batchmode -nographics`. PlayMode runs with
  `-batchmode` only; `-nographics` is omitted because PlayMode needs graphics
  initialization. `-quit` is not passed to test runs; the editor exits after the
  tests.
- Test results are NUnit3 XML in `artifacts/reports/unity/`. A run passes when
  the root has `failed="0"` and `result="Passed"`.
- Coverage is read from `coverage-*/Report/Summary.xml`; a missing report is a
  warning, not a failure.
- `--unity-build` produces `artifacts/unity-build/ProjectDelta.exe`; success
  requires exit 0, the executable, and a size above 1 MiB.
- `unity odin` runs the bridge described in
  `templates/unity/docs/UNITY-ADAPTER.md`. Without Odin the report status is
  `skipped` and the command exits 0.

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

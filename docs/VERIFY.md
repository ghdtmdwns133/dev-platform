# Verification reference

There is one verification interface per stack. Local development and GitHub
Actions run the same command with the same configuration; CI does not add a
second, hidden gate.

| Stack        | Day-to-day command                                        | What CI runs                              |
| ------------ | --------------------------------------------------------- | ----------------------------------------- |
| `python`     | `mise run check`, `mise run test`, `mise run build`       | the same mise tasks in `ci.yml`           |
| `typescript` | `mise run check`, `mise run test`, `mise run build`       | the same mise tasks in `ci.yml`           |
| `dotnet`     | `mise run check`, `mise run test`, `mise run build`       | the same mise tasks in `ci.yml`           |
| `unity`      | `mise run check` and `devctl verify --profile unity`      | `unity.yml` (`integrity` and `tests`)     |
| `other`      | `mise run check`                                           | `ci.yml` with tests disabled              |

`check`, `test` and `build` live in the generated `mise.toml`. `check` runs
`pre-commit run --all-files` against the repository's
`.pre-commit-config.yaml`; the same file is used by the pre-commit install and
by CI. `test` writes its native coverage report under `coverage/`, which CI
uploads as an artifact. `build` writes the release artifact under `dist/`.
`test` and `build` are absent for `other`; Unity has no `test` task because its
test execution belongs to `unity.yml` and `devctl`.

First-time setup in a generated repository:

```bash
mise trust
mise install
mise exec -- pre-commit install   # optional: run the same check on staged files
mise run check
mise run test
```

The tool versions mise manages come from `[tools]` in `mise.toml`; Unity's
editor is supplied by the host and checked by `devctl`. Renovate updates the
mise pins when the hosted app is installed; there is no `versions.json` and no
`devctl versions` command.

## devctl (Unity only)

`devctl` keeps the Unity work that cannot be expressed as a generic task. It is
a Python 3.12 standard-library CLI in [`cli/`](../cli), run through `uv`.

```bash
uv run --project <path-to-dev-platform>/cli devctl [global options] <command> [options]
```

In CI, `unity.yml` checks out `ghdtmdwns133/dev-platform` at the caller's
`platform-ref` into `.dev-platform` and runs
`uv run --project .dev-platform/cli devctl ...`. A generated Unity layer's
pre-commit hook uses
`uvx --from git+https://github.com/<owner>/dev-platform@<ref>#subdirectory=cli devctl ...`;
from a local project-delta checkout, use the clone path form above. There is no
wrapper or shim that hides these two forms.

Global options:

| Option          | Default                                  | Meaning                                  |
| --------------- | ---------------------------------------- | ---------------------------------------- |
| `--root DIR`    | current directory                        | Project root.                            |
| `--reports DIR` | config `reports` or `artifacts/reports`  | Report directory, relative to the root.  |
| `--config FILE` | `<root>/.devplatform/config.json`        | Configuration file.                      |

Exit codes are part of the contract:

| Code | Meaning                                                          |
| ---- | ---------------------------------------------------------------- |
| 0    | All requested checks passed.                                     |
| 1    | A gate failed (lint, test, coverage, integrity, security).       |
| 2    | A precondition is missing (editor, token, clean git state).      |
| 3    | Execution failed (tool crash, missing result file).              |
| 4    | A required feature is absent (for example `--require-odin`).     |

### `devctl verify --profile unity|unity-assets`

Runs the fixed Unity step table. `--fail-fast` stops at the first failure;
without it every step runs and failures are aggregated. `--min-coverage N`
overrides `coverage.minimum`; `--unity-build` adds the player build;
`--upload-coverage` uploads coverage after the test step.

| Profile        | Steps, in order                                                                                          |
| -------------- | -------------------------------------------------------------------------------------------------------- |
| `unity`        | integrity, one test step per entry in `unity.testPlatforms`, coverage (when enabled), optional build, optional coverage upload |
| `unity-assets` | integrity only (no editor required)                                                                     |

Step names are fixed: `unity-integrity`, `unity-editmode`, `unity-playmode`,
`unity-coverage`, `unity-build`, `unity-coverage-upload`. `unity-coverage` is
skipped with `prerequisite unity-editmode failed` when the EditMode step did
not pass.

### `devctl unity ...`

- `unity integrity [--write-baseline]` — required paths, editor version,
  protected scene and objects, build settings, script locations, meta files,
  GUIDs and reference integrity. `--write-baseline` refreshes
  `.devplatform/external-guids.json` and requires `Library/PackageCache`.
- `unity tests [--platform EditMode|PlayMode|all]` — batchmode test run;
  NUnit3 XML lands under `artifacts/reports/unity/`.
- `unity build` — Windows player build in `artifacts/unity-build/`.
- `unity odin [--require-odin]` — reflection bridge; `status: skipped` is
  success unless `--require-odin` is passed.
- `unity junit --in FILE_OR_DIR --out FILE` — convert NUnit3 XML to JUnit XML.
- `unity coverage-upload` — upload Unity OpenCover results to Codecov. Requires
  `CODECOV_TOKEN` in the environment and a pushed, clean commit.
- `unity cloud-build [--target ID] [--commit SHA] [--timeout-min N] [--download DIR]`
  — start and poll a Unity Build Automation build. Requires the
  `UNITY_BUILD_*` variables; see [UNITY-CI.md](UNITY-CI.md).

### `devctl summary`

Prints the `summary.md` generated by the last run.

## Reports

Unity runs write:

```
artifacts/reports/<profile>/
  summary.json
  summary.md
  <step>.log
  editmode.xml / playmode.xml
  coverage-*/Report/Summary.xml
```

`summary.json` records `schema`, `profile`, `status`, `exit`, `started`,
`duration_s`, `root`, `steps`, `coverage`, `tests` and `artifacts`. Each step
records `name`, `status`, `exit`, `duration_s`, `log` and an optional `detail`.
`verify` clears `<reports>/<profile>/` before a run so a failed build cannot
reuse stale results; it refuses to clear a symlink or a path outside the
repository.

Coverage comes from `coverage-*/Report/Summary.xml`. A missing report prints a
`::warning::` and records `coverage report not produced`; the coverage step
passes. A measured value below `coverage.minimum` fails `unity-coverage`.

## CI contract

Non-Unity callers use `ci.yml`; the caller job is named `platform-verify`, so
the checks are `platform-verify / check` and, except for `other`,
`platform-verify / test`. `ci.yml` runs `mise run check` and, when `run-tests`
is true, `mise run test`, then uploads `coverage/`. Codecov runs only when `enable-codecov` is true and
the `codecov_token` secret is present; an enabled job without a token prints a
`::warning::`, and a disabled job prints a `::notice::`. `security.yml` runs
independently and produces `platform-security / scan`.

Unity callers use `unity.yml` only. Its `integrity` job runs
`devctl verify --profile unity-assets` on `ubuntu-latest` and uploads
`reports-unity-assets`; the `tests` job runs on the self-hosted Windows runner
with `devctl verify --profile unity` and uploads coverage to Codecov when the
token is present. GameCI test results and build zips have their own artifacts.
The caller never produces `platform-verify / check`, so that name must not
appear in a Unity repository's required checks.

`actions/security-scan` is the only security runner; it is not a `devctl`
subcommand. Its version pins live in the composite action and are updated by
Renovate.

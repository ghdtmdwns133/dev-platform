# devctl reference

`devctl` is the single verification command. Local runs and CI runs use the
same executable, the same profile and the same arguments.

```bash
uv run --project <platform>/cli devctl [global options] <command> [options]
```

## Global options

| Option            | Default                            | Meaning                                   |
| ----------------- | ---------------------------------- | ----------------------------------------- |
| `--root DIR`      | current directory                  | Project root.                             |
| `--reports DIR`   | config `reports` or `artifacts/reports` | Report directory, relative to the root. |
| `--config FILE`   | `<root>/.devplatform/config.json`  | Configuration file.                       |
| `--platform-home` | `DEVPLATFORM_HOME` or the CLI repo | Location of `versions.json` and templates. |

Exit codes:

| Code | Meaning                                                       |
| ---- | ------------------------------------------------------------- |
| 0    | All requested checks passed.                                  |
| 1    | A gate failed (lint, test, coverage, integrity, security).    |
| 2    | A precondition is missing (editor, token, clean git state).   |
| 3    | Execution failed (tool crash, missing result file).           |
| 4    | A required feature is absent (for example `--require-odin`).  |

## Commands

### `devctl verify --profile P`

Runs every step for the profile. By default all steps run and failures are
aggregated; `--fail-fast` stops at the first failure. `--min-coverage N`
overrides the configured floor. `--unity-build` adds the player build to the
`unity` profile. `--upload-coverage` uploads Unity coverage after tests.

| Profile        | Steps, in order                                                                                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python`       | `uv sync --frozen`, `ruff check --output-format=github .`, `ruff format --check .`, `pytest --junitxml --cov --cov-report=xml --cov-fail-under`                     |
| `typescript`   | `npm ci --no-audit --no-fund`, `tsc --noEmit`, `eslint . --max-warnings=0`, `prettier --check .`, `vitest run --coverage` with JUnit output                          |
| `dotnet`       | `dotnet restore`, `dotnet build --no-restore -warnaserror`, `dotnet format --verify-no-changes --severity warn`, `dotnet test` with XPlat coverage and TRX output    |
| `unity`        | integrity, EditMode tests, PlayMode tests, coverage, optional build, optional coverage upload                                                                        |
| `unity-assets` | integrity only                                                                                                                                                      |

Step names in `summary.json` are fixed: `uv-sync`, `ruff-check`, `ruff-format`,
`pytest`, `npm-ci`, `tsc`, `eslint`, `prettier`, `vitest`,
`dotnet-restore`, `dotnet-build`, `dotnet-format`, `dotnet-test`,
`unity-integrity`, `unity-editmode`, `unity-playmode`, `unity-coverage`,
`unity-build`, `unity-coverage-upload`, and an aggregate `coverage` step.

### `devctl unity ...`

- `unity integrity [--write-baseline]` — validate required paths, editor
  version, protected scene and objects, build settings, script locations, meta
  files, GUIDs and reference integrity. `--write-baseline` refreshes
  `.devplatform/external-guids.json` and requires `Library/PackageCache`.
- `unity tests [--platform EditMode|PlayMode|all]` — batchmode test run;
  NUnit3 XML lands in `artifacts/reports/unity/`.
- `unity build` — Windows player build in `artifacts/unity-build/`.
- `unity odin [--require-odin]` — reflection bridge; `status: skipped` is a
  success unless `--require-odin` is passed.
- `unity junit --in FILE_OR_DIR --out FILE` — convert NUnit3 XML to JUnit XML.
- `unity coverage-upload` — upload Unity OpenCover results to Codecov. Requires
  `CODECOV_TOKEN` in the environment and a pushed, clean commit.

### `devctl versions --check [--profile P]`

Compares the running toolchain with `versions.json`. Python must match the
pinned minor; .NET must provide an SDK in the pinned feature band; the Unity
editor must match exactly when one is installed; Node must be at least the
pinned major. A lower Node major fails. uv, npm and the security tools report
warnings only. The command exits 1 on any `fail`.

### `devctl init --template T --name NAME --dest PATH`

Renders `_shared` then the template, substitutes the documented tokens, refuses
to leave unresolved `__TOKEN__` text, and prints the next three steps. Empty
directories are required unless `--force` is used.

### `devctl summary`

Prints the generated `summary.md` for the last run.

## Reports

```
artifacts/reports/<profile>/
  summary.json
  summary.md
  <step>.log
  junit.xml
  coverage.xml
```

`summary.json` has `schema`, `profile`, `status`, `exit`, `started`,
`duration_s`, `root`, `steps`, `coverage`, `tests` and `artifacts`.
Each step records `name`, `status`, `exit`, `duration_s`, `log` and an optional
`detail`.

Coverage is read from the profile's native report: Cobertura `line-rate` for
Python and .NET, and `coverage-summary.json` (`total.lines.pct`) for
TypeScript. A missing report is an execution failure unless the producing step
already failed.

## CI contract

Composite actions run from the caller's working directory:

```bash
uv run --project .dev-platform/cli devctl versions --check --profile <p>
uv run --project .dev-platform/cli devctl verify --profile <p> --min-coverage <n>
```

Reports always land in `artifacts/reports/<profile>/` and are uploaded as the
`reports-<profile>` artifact for 14 days. CI steps add `::error title=<step>`
annotations on failure and append the markdown summary to the job summary.

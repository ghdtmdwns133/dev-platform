# Repository Guidelines

This repository is the source of truth for a reusable verification platform used by Python, TypeScript, .NET, Unity and stack-agnostic (`other`) repositories. A consumer gets the template, mise tasks, pre-commit hooks, caller workflows and a GitHub ruleset; local development and CI run the same commands.

## Project Overview

- Keep one public contract: generated repositories run `mise run check`, plus `test` and `build` where they really exist. Unity adds the `devctl` CLI; there is no `devctl init`, no `devctl versions` and no Python/TypeScript/.NET profile.
- `scripts/bootstrap_repo.py` provisions new or existing repositories. It renders the pure-safe Copier template, installs the toolchain and hook, then applies GitHub settings, labels, the ruleset and, only when available, optional secrets.
- `template/` is one Copier tree with conditional files, not one directory per stack. Keep `.copier-answers.yml` answer names stable; renaming them breaks `copier update` for existing consumers.
- `other` is the adoption layer for native applications. It provides `check` only and must never grow a fake `test` or `build` task.
- The Python, TypeScript and .NET samples deliberately keep the fixed internal names `devflow` / `DevFlow` (`src/devflow`, `DevFlow.slnx`, `DevFlow.Core`). `--name` changes distribution/repository naming, not sample identifiers. Never substitute a sample for a framework the user asked for.
- Credentials and SaaS setup are out of scope by default. Codecov and Doppler are separate deferred items in [TODO.md](TODO.md); do not configure them, ask the user to configure them, or claim they are connected. Sentry is created only when the user explicitly requests it. Codecov is off by default; do not turn it on as part of unrelated work.
- Do not add a generic language adapter, an NLP/model service, a new paid service, Azure resources, or an integration the request did not ask for. Do not fake success, suppress failures, or create no-op tasks.
- **How to use this file:** open this dev-platform repository itself as the AI workspace so its root `AGENTS.md` is loaded, then describe the desired project in natural language, for example “`C:/dev/my-app`에 Vite + React 앱을 만들어 줘. 비공개 저장소로.” The user does not need to know bootstrap flags. This file is scoped to this repository; it is not a global AI configuration and is not discovered from an unrelated workspace.
- **Generated apps:** do not copy this platform file wholesale into a new app; its Unity CLI and platform internals are irrelevant there. Preserve an existing app's `AGENTS.md`. If app-specific guidance is needed, write it from the app's actual files, commands, tests and structure after the smoke run.

**Bounded AI project-intent workflow.** When asked to create a project:

1. Infer the repository slug, private-by-default visibility, stack, framework, package manager and existing project path from the request. Ask only for material product choices that cannot be inferred; never ask for credentials or service setup.
2. If the user named a framework or wants its native app structure, create it with that framework's official generator first; for example `uv init --lib` preserves a native import namespace and is preferable to forcing the sample layout. Never substitute a platform sample for the requested framework, and do not assume the built-in `devflow`/`DevFlow` identifiers become the requested app's package names. For an existing editor-created Unity project, skip the generator and treat that project's `ProjectSettings/ProjectVersion.txt`, scene `.meta` GUIDs, YAML fileIds, required objects and first enabled build scene as authoritative; render EditMode only, no GUI/PlayMode, and `unity-runner: none` until a runner exists. UBA needs a real `unity.cloudBuild.target` and is a build path, not automatic test verification.
3. Before the overlay, identify the app's real native commands and define project-owned `mise.toml` tasks: `prepare` when dependencies need installing, `check`, `test` only when tests exist, and `build` only when a build exists. Never add placeholder tasks. Decide whether the native `test` task exists now; only then include `--run-tests` in the first `other` render below.
4. Overlay without overwriting: use `--template other` (or `unity` for an existing Unity project) with `--adopt --render-only` and the test choice from step 3. Copier `--skip '*'` preserves every existing file. Inspect skipped collisions and merge missing tools/hooks; a preserved `mise.toml` needs the template's pinned `"pypi:pre-commit" = { version = "4.7.0", python = "3.12" }`. Keep native `.github/workflows/ci.yml`; add the platform caller under a distinct filename with the same `platform-verify`/`platform-security` job IDs, or match the ruleset to native checks. Keep `run_tests`, actual tasks and required checks aligned. Do not recopy to change test settings later: use `uvx copier@9.19.1 update --defaults --data run_tests=true` (or `false`), then review caller/ruleset changes, including app-owned workflow filenames.
5. After `--render-only` (which never initializes Git or installs tools), ensure the app has an initialized Git repository even if the official generator left it absent or unborn; then review and stage only the intended files explicitly—never blanket-add the user's tree. Run `mise trust && mise install`, run `prepare` only if that task exists, and install the pre-commit hook. Merge missing `.gitignore`/`.editorconfig` entries along with the mise/hooks/CI files so report and `.dev-platform` outputs do not make the tree dirty. Smoke-test with `mise run check` and any real `test`/`build` tasks; checks over no tracked files are not evidence, so confirm the intended source and tests are visible. Fix failures, commit the reviewed work, then run `bootstrap_repo.py --root <dir>` for GitHub settings and the ruleset, and after the first green run confirm actual check names before finalizing required checks.

## Architecture & Data Flow

- **Provisioning path:** `bootstrap_repo.py` validates arguments, invokes pinned Copier 9.19.1 against `template/`, and writes `.copier-answers.yml`. A full fresh render then runs git init/commit (only when the destination is not a repository), `mise trust`/`install`/`prepare`, `pre-commit install`, `gh repo create` when needed, then repository settings, labels, the `platform-gates` ruleset and optional secrets. `copier.yml` is pure-safe: no `_tasks`, migrations or extensions, so hosted Renovate never executes template code.
- **Render modes:** `--render-only` stops after Copier and permits no git, tool install, hook, GitHub API or secret work; it may still fetch the template over the network. `--adopt` requires `--render-only` and an `other` or `unity` stack, and rejects an existing `.copier-answers.yml`; use `copier update` for an existing Copier project, not a recopy. `--dry-run` is the only no-network, no-write mode. `--no-create-repo` still queries and reconciles an existing remote; when the remote is absent it still performs local git/tool/hook setup, then stops before repository creation, settings, ruleset and secrets. It is not a local-only mode.
- **Existing-checkout reconciliation:** a run without `--render-only` that targets an existing `--root` requires an actual git checkout at the repository top level with a commit, no uncommitted or untracked changes, and—if the remote already exists—an `origin` that resolves exactly to the requested owner/name. Fail before installing tools or mutating GitHub when that is not true. A fresh `--template --dest` run creates the directory and initializes git itself; it is not a reconciliation.
- **Consumer local path:** `mise run check` runs `pre-commit run --all-files`; pre-commit delegates to the native linters/test tools declared in that repository's `mise.toml`. `mise run test` and `mise run build` are the same commands CI invokes; CI has no hidden second gate.
- **CI path:** caller workflows call reusable workflows at the pinned platform ref. `ci.yml` runs `mise run check` and, when `run-tests` is true, `mise run test`; `unity.yml` runs integrity and the selected Unity runner; `security.yml` runs trivy, gitleaks, zizmor and actionlint. `nightly.yml`, `release.yml` and `self-test.yml` reuse the same building blocks. Required-check contexts are `<caller job> / <job name>` and come from the ruleset, never from guesswork.
- **Unity devctl path:** `.devplatform/config.json` (strict, unknown keys rejected) feeds a fixed step table in `cli/src/devplatform/verify.py`. `plan()` is authoritative; `run_verify()` executes steps through `procs.run`, records one log per step under `artifacts/reports/<profile>/`, aggregates failures unless `--fail-fast`, and writes `summary.json` plus `summary.md`. Exit codes are 0 success, 1 gate failure, 2 missing precondition, 3 execution failure, 4 required feature absent.
- **Implementation style:** synchronous Python 3.12 standard library only. Use `pathlib.Path`, frozen/simple dataclasses, explicit return codes and the `DevctlError` mapping. Subprocess and HTTP clients are injected (`Runner = Callable[..., procs.Result]`, `cloudbuild.Client`) so tests can substitute them. There is no async framework, DI container or hidden global state.

## Key Directories

- `scripts/bootstrap_repo.py` — the only provisioning entry point; owns argument validation, Copier invocation, GitHub reconciliation and optional secret lookup.
- `cli/src/devplatform/` — Unity-only `devctl`: `cli.py` (argparse), `config.py`, `verify.py`, `procs.py`, `integrity.py`, `unity.py`, `report.py`, `errors.py`, `cloudbuild.py`.
- `cli/tests/` — pytest suite, including bootstrap/CLI behavior and gate fixtures. Tests import the standalone bootstrap script with `importlib`; do not add a runtime dependency for testing.
- `template/` — the Copier render root. It contains conditional caller workflows under `template/.github/workflows/`, the Unity overlay under `template/Assets/` and `template/.devplatform/`, and the shared `mise.toml.jinja` / `.pre-commit-config.yaml.jinja`.
- `actions/` — composite actions, notably `security-scan` and `notify`; `unity-cloud-build` holds the UBA bridge.
- `.github/workflows/` — dev-platform's reusable workflows (`ci`, `unity`, `security`, `nightly`, `release`) and `self-test.yml`. `.github/rulesets/platform-gates.json` is dev-platform's own required-check ruleset.
- `docs/` — ADOPTION, VERIFY, UNITY-CI, SECRETS, COSTS, CODESCENE and the Korean operating manuals. `docs/research/` is dated evidence, not operating instructions.
- Root `mise.toml` — dev-platform's own toolchain and `lint`/`test`/`check` tasks. `copier.yml` — template questions and exclusions. `default.json` — shared Renovate preset. `TODO.md` — user-deferred Codecov/Doppler setup.

## Development Commands

Run from `C:/dev/dev-platform` unless stated otherwise. Root commands are exactly those in `mise.toml`; there is no root `run` or `build` task.

```bash
mise trust && mise install
mise run lint    # ruff check/format, zizmor, actionlint
mise run test    # pytest cli/tests -q
mise run check   # lint + test, the platform's own gate
```

Equivalent low-level CLI commands:

```bash
uv run --directory cli ruff check --config pyproject.toml . ../scripts
uv run --directory cli ruff format --check --config pyproject.toml . ../scripts
uv run --project cli pytest cli/tests -q
```

Provisioning commands:

```bash
uv run --script scripts/bootstrap_repo.py --help
uv run --script scripts/bootstrap_repo.py --template python --name my-service --dest C:/dev/my-service
uv run --script scripts/bootstrap_repo.py --template other --adopt --render-only --name my-app --dest C:/dev/my-app
uv run --script scripts/bootstrap_repo.py --root C:/dev/my-service --name my-service --dry-run
```

- `--render-only` requires `--template` and is the local render path; it is not offline. Use `--dry-run` for a pure plan; it makes no network calls, never invokes Copier and writes nothing, though a `--root` plan may read local git state.
- `--adopt` requires `--render-only`, `--template other|unity`, and forbids `--force`. It requires an existing destination directory, rejects one that already contains `.copier-answers.yml`, and writes only missing platform files while preserving every existing file.
- `--run-tests`/`--no-run-tests` are valid only with `--template other`; unset leaves Copier's `run_tests` default (`false` for `other`). Enable it only after the native `mise run test` task is real.
- `--unity-runner none|self-hosted|uba` is valid only with `--template unity`; unset renders `none`. A public repository with `self-hosted` is rejected.
- A normal render refuses a non-empty destination even with `--force`; update an existing Copier project with `uvx copier update --defaults`, review the diff, and do not recopy.
- Full `--root` reconciliation requires a clean git checkout and a matching `origin` for an existing repository. Do not commit or push unrelated user changes to satisfy it.

Generated repositories (when the task exists):

```bash
mise trust && mise install
mise run prepare
mise run check
mise run test
mise exec -- pre-commit install   # fresh clone only
```

Unity CLI examples (from a platform checkout):

```bash
uv run --project C:/dev/dev-platform/cli devctl verify --profile unity-assets --root <project>
uv run --project C:/dev/dev-platform/cli devctl verify --profile unity --root <project>
uv run --project C:/dev/dev-platform/cli devctl summary --root <project>
```

Only `unity` and `unity-assets` profiles exist. Integrity needs no editor; a full Unity run requires the host editor configured in `.devplatform/config.json`.

## Code Conventions & Common Patterns

- Python: 3.12, standard library only, ruff line length 100, double quotes, full type hints, `from __future__ import annotations`. Prefer small pure functions, `Path` over string paths, and dataclasses for records. Return documented exit codes instead of raising arbitrary exceptions; use `DevctlError` for precondition/execution failures.
- Never swallow subprocess failures. `procs.run` captures combined output and returns `Result`; aggregate failures, emit GitHub annotations in Actions, and keep the last 20 lines for the error summary.
- Config is intentionally strict: reject unknown keys and validate ranges at the parser/config boundary. Resolve project-relative paths against `--root`; refuse to clear a reports directory that is a symlink or outside the root.
- Workflows: pin third-party actions to full SHAs with the human tag in a comment, set minimal `permissions`, add `concurrency` and `timeout-minutes`, and never use `pull_request_target`. Workflows call mise tasks or the shared composite actions instead of duplicating commands.
- Template changes: keep `copier.yml` pure-safe; express stack differences with Copier conditions/exclusions, not generated scripts. Preserve native manifests, lockfiles and READMEs on adoption. Do not add `_tasks`, migrations or extensions.
- Secrets: never print or commit values. Pass them through `secrets`/environment; missing optional credentials produce a `::notice::`, never a fake success. Do not turn an integration on merely because a token exists.
- Commits: only include files reviewed for the authorized task. Do not `git add -A` a user's working tree, commit build output or coverage, or push unless the user authorized it. Create a tag or release only when the user explicitly authorizes that release scope and CI is green; never attach one to an unrelated feature change.

## Important Files

- `copier.yml` — question contract (`project_name`, `stack`, `owner`, `visibility`, `platform_ref`, `min_coverage`, `create_github_repo`, `enable_codecov`, `enable_sentry`, `run_tests`, `unity_runner`) and file exclusions. Answer names are a compatibility contract.
- `scripts/bootstrap_repo.py` — argument parsing, render/adopt modes, git/mise/pre-commit setup, GitHub repository/settings/labels/ruleset/secret reconciliation.
- `template/mise.toml.jinja` — consumer tool pins and native `prepare`/`check`/`test`/`build` tasks. `template/.pre-commit-config.yaml.jinja` — hooks shared by local commits and CI.
- `template/.github/workflows/{ci,nightly,release}.yml.jinja` and `template/.github/rulesets/platform-gates.json.jinja` — caller jobs and the required-check contract for generated repositories.
- `.github/workflows/{ci,unity,security,nightly,release,self-test}.yml` — reusable platform workflows and the platform's own gate. `actions/security-scan/action.yml` is the only security runner.
- `cli/src/devplatform/verify.py` — fixed Unity step table and aggregation. `config.py` — strict config defaults. `procs.py` — subprocess/log contract. `integrity.py` — asset, scene, GUID and `.meta` checks. `unity.py` — editor discovery, tests, build, Odin and coverage. `report.py` — summaries. `errors.py` — exit-code contract.
- `default.json` — shared Renovate preset; root `renovate.json` extends it. Root `mise.toml` — platform toolchain. `TODO.md` — deferred Codecov/Doppler items.

## Runtime/Tooling Preferences

- Platform toolchain: Python 3.12, uv 0.12.21, pre-commit 4.7.0, gitleaks 8.30.1, zizmor 1.31.1, actionlint 1.7.12. Generated stacks use Node 22 with `package-lock.json` and .NET SDK 10.0.401 with `global.json`. The rendered Unity sample pins 6000.5.1f1, but on adoption the existing project's `ProjectSettings/ProjectVersion.txt` is authoritative. There is no `versions.json`; each generated `mise.toml` and native manifest is authoritative.
- Respect the existing package manager and lockfile. Do not convert npm to Bun/pnpm, replace `uv.lock`, regenerate `package-lock.json` casually, or add a second toolchain manager. Use `npm ci`/`uv sync --frozen`/`dotnet restore` in automation.
- Copier is pinned to 9.19.1. Keep `--skip '*'` semantics for adoption; use `--force` only for a throwaway render, never an existing repository. Hosted Renovate cannot run template tasks, so keep the template pure-safe.
- GitHub-hosted Ubuntu runs non-Unity and Unity integrity. Unity tests require a configured private self-hosted Windows runner; UBA is a build path that needs a real `unity.cloudBuild.target` and does not automatically verify tests. The default is `unity-runner: none`, and public repositories must never use `self-hosted` (they may use `none` or `uba`). Never register a public repository on self-hosted infrastructure. Do not add Azure, Copilot, or another paid service.
- Unity new-project defaults are EditMode only and `unity-runner: none`. Do not queue a runner that does not exist, do not require `platform-verify / tests` when the runner is none, and do not assume PlayMode or GUI automation. `project-delta` is hand-adopted with an explicit runner; leave its configuration alone unless that task explicitly asks.
- `other` has `check` only. If a native app has real tests or a build, define those tasks explicitly and wire `run_tests`/required checks only then.
- Optional credentials: Codecov and Doppler are deferred separately in `TODO.md`; Codecov defaults off in both bootstrap and Copier. Sentry is opt-in and unconfigured. Never present any of these as active, and never ask for tokens as a prerequisite for basic provisioning.

## Testing & QA

- Platform QA is `mise run check` locally and `self-test.yml` in CI. Self-test lints the CLI, renders every template, runs its check/test tasks, builds the devcontainers, scans security, and lints workflows. Template renders use Copier directly with `create_github_repo=false`; they must not mutate GitHub.
- Tests live in `cli/tests/`. Add focused tests for changed behavior, exit codes and stable error conditions; do not couple tests to incidental diagnostic wording or internal source details. Keep tests independent of a live Unity editor unless the task explicitly requires a local Unity run.
- Coverage: the platform's own pytest suite (pytest-cov is available) has no CLI coverage floor. Generated Python uses pytest-cov, TypeScript uses Vitest v8, and .NET uses xUnit + coverlet to enforce the configured `min_coverage` (default 80). `other` follows its actual native project policy and never gets a synthetic floor. Unity's `coverage.minimum` must match the project's real measured/native policy, not a claimed default-threshold pass.
- Consumer verification uses the same `mise run check`/`test`/`build` commands as CI. A successful `--adopt` copy proves only that files landed: inspect preserved collisions, merge missing hooks/tasks, and confirm the caller jobs actually run before claiming CI or coverage integration. Do not invent a CI-only command or claim a gate passed when it was skipped.
- Unity integrity is editor-free (`devctl verify --profile unity-assets`). A full `devctl verify --profile unity` requires a host editor and writes `artifacts/reports/unity/summary.json`. EditMode is the default for new projects; do not run GUI/PlayMode automation from unrelated work. Test results, coverage and logs are artifacts, not committed files.
- Confirm outcomes before reporting completion: run the root gate for platform changes, render smoke projects for template changes, and run the generated project's real check/test tasks. A missing optional token or unavailable runner is a documented notice and an unverified integration, never a pass.

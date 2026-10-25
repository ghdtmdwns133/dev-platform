# dev-platform

Reusable verification platform for repositories using the stacks that already
exist here — Python, TypeScript, .NET and Unity — plus a stack-agnostic `other`
profile that runs only the repository-level checks. A new repository starts
with one bootstrap command that invokes Copier, and local checks and CI use the
same commands and the same configuration.

## What it provides

- **Copier template** — [`copier.yml`](copier.yml) and [`template/`](template/)
  render the project and write `.copier-answers.yml` so `copier update` can
  propagate later changes. The template is pure-safe: it has no `_tasks` or
  other code-executing features. [`scripts/bootstrap_repo.py`](scripts/bootstrap_repo.py)
  is the single provisioning entry point; it renders with Copier, initializes
  git, creates the GitHub repository when asked, and applies the settings,
  labels and ruleset.
- **mise tasks** — each generated `mise.toml` pins the toolchain mise manages
  (Python, Node or .NET, plus uv, pre-commit and gitleaks) and declares
  `check`, `test` and `build` where they exist. Unity's editor comes from the
  host, not from mise. The reusable CI workflow runs the same tasks through
  `jdx/mise-action`; there is no second CI-only command.
- **pre-commit** — each generated repository has a `.pre-commit-config.yaml`.
  `mise run check` runs it on all files locally, and CI runs the same check.
- **Renovate** — [`default.json`](default.json) is the shared preset
  (`github>ghdtmdwns133/dev-platform`) for dependency updates and action pins;
  the platform's own [`renovate.json`](renovate.json) extends it so this
  repository is onboarded too. The user confirmed the hosted Renovate app is
  installed for all repositories on 2026-10-24; actual bot run/PR evidence is
  still to be verified.
- **Unified workflows** — `ci.yml`, `security.yml`, `unity.yml`, `release.yml`
  and `nightly.yml` are reusable, plus `self-test.yml` for the platform itself.
  Dependency PR auto-merge is handled by Renovate; release-please PRs are
  handled by the release workflow. There is no separate auto-merge workflow.
- **Unity tooling** — `devctl` (Python 3.12, standard library only, run through
  `uv`) keeps the Unity-specific work: integrity checks, Unity tests (the modes
  listed in `unity.testPlatforms`), build, Odin bridge, NUnit-to-JUnit
  conversion, coverage upload and Unity Build Automation. Non-Unity stacks are
  verified by their mise tasks, not by `devctl`.
- **releases** — for non-Unity and private Unity repositories using the
  self-hosted runner, release-please opens the Release PR; merging it creates
  the tag, and the same workflow builds and attaches the assets. Public Unity
  and UBA renders omit the release workflow and produce no release assets; with
  the default `none` runner Unity runs integrity only, while UBA may run
  cloud-build for relevant changes.

## Quick start

For AI-assisted provisioning, open this dev-platform checkout itself as the AI
workspace so the root [AGENTS.md](AGENTS.md) is loaded, then describe the app in
natural language — for example, “`C:/dev/my-app`에 Vite + React 앱을 만들어 줘.
비공개 저장소로.” Flags are not required. That guidance is repository-scoped;
it is not global configuration and is not discovered from an unrelated
workspace.

Prerequisites: `uv` (which provides `uvx`), `git`, `mise`, and an authenticated
`gh`. From a dev-platform checkout:

```bash
uv run --script scripts/bootstrap_repo.py \
  --template python \
  --name my-service \
  --dest C:/dev/my-service
cd C:/dev/my-service
mise run check
```

The bootstrap asks Copier for the stack-specific files, applies the repository
settings, runs `mise trust`/`mise install`, `mise run prepare` when the stack
defines it, and installs the pre-commit hook.
It writes `.copier-answers.yml` (Copier, not the script). Pass `--owner`,
`--visibility`, `--platform-ref`, `--min-coverage`,
`--enable-sentry`/`--no-enable-sentry`, or `--no-create-repo` as needed.
Codecov is off by default in both the bootstrap and the template; enabling it
is optional and deferred in [TODO.md](TODO.md).

`--render-only` requires `--template` and stops after Copier: no git, tools,
hooks, GitHub API or secrets. `--adopt` (with `--render-only`, `--template
other|unity`, and never `--force`) adds the platform layer to an existing
native application or Unity project while preserving every existing file;
inspect the skipped files before assuming CI is wired. `--run-tests` is valid
only for `other` and only when its `mise run test` task really exists.
`--unity-runner none|self-hosted|uba` is valid only for Unity and defaults to
`none`; a public repository cannot use `self-hosted`. `--dry-run` prints every
planned command without network access, rendering or writes. The settings-only
`--root` path is idempotent: re-running it reconciles settings, labels and the
ruleset without creating a second repository. A non-empty template destination
is refused; update a Copier-managed repository with `copier update`. A full
`--root` reconciliation requires a clean git checkout whose `origin` matches the
requested repository. `--no-create-repo` still queries and reconciles an
existing remote; if the remote is absent it still performs the local
Git/tool/hook setup, then stops before repository creation, settings, ruleset
and secrets. It is not a local-only mode. Use `--render-only` for a local
render.

A fresh clone later cannot inherit git hooks, so install them once there:

```bash
mise trust && mise install
mise run prepare
mise exec -- pre-commit install
```

To render only, without any GitHub work, use `--render-only` (or Copier
directly). Both still fetch the template, so they are not offline; only
`--dry-run` performs no network access or writes:

```bash
uv run --script scripts/bootstrap_repo.py --template python --name my-service \
  --dest C:/dev/my-service --render-only
# or
uvx copier copy https://github.com/ghdtmdwns133/dev-platform my-service
```

The default Copier source is `https://github.com/ghdtmdwns133/dev-platform` at the latest PEP
440 tag; `--template-source` overrides it and `--template-ref` pins a ref.
`--local` renders from the current checkout instead and is intended for
development/self-test, not normal project creation.

The Unity template is a platform layer, not a complete Unity project. For an
existing editor-created project, use `--template unity --adopt --render-only`
and align `.devplatform/config.json` with that project's actual
`ProjectSettings/ProjectVersion.txt`, scene and `.meta` GUIDs, scene fileIds,
and enabled build scene. New Unity renders are EditMode-only and default to
`unity-runner: none`; enable a runner or PlayMode only when it is actually
configured. UBA also needs `unity.cloudBuild.target` filled in.

The template does not install Renovate, authorize Codecov/CodeScene/Sentry, or
log in to Doppler. Those remain external account actions; see
[docs/SECRETS.md](docs/SECRETS.md) and [docs/ADOPTION.md](docs/ADOPTION.md).

## Stacks and the single check interface

| Stack        | Local check (same command in CI)              | Test output                          | Build output |
| ------------ | --------------------------------------------- | ------------------------------------ | ------------ |
| `python`     | `mise run check` → `mise run test`            | `coverage/coverage.xml`              | `dist/`      |
| `typescript` | `mise run check` → `mise run test`            | `coverage/coverage-final.json` + `coverage/lcov.info` | `dist/` |
| `dotnet`     | `mise run check` → `mise run test`            | `coverage/coverage.cobertura.xml`    | `dist/`      |
| `unity`      | `mise run check` (pre-commit, incl. integrity) and `devctl verify --profile unity` | Unity NUnit3 XML and coverage report | Unity build via `unity.yml` |
| `other`      | `mise run check`                              | —                                    | —            |

`check`, `test` and `build` are the only task verbs the reusable workflow
calls. `test` and `build` do not exist for `other`; `test` does not exist for
Unity. The Unity template renders the platform layer for a Unity project; it
does not contain a complete Unity project.

## CI behaviour

- Non-Unity callers name the `ci.yml` job `platform-verify`, producing
  `platform-verify / check` and, when `run-tests` is true,
  `platform-verify / test`. `other` defaults to `run-tests: false`, so it has
  `platform-verify / check` and `platform-security / scan`. `security.yml`
  produces `platform-security / scan`.
- Unity callers use `unity.yml` (as `platform-verify`). The default
  `unity-runner: none` produces only `platform-verify / integrity`; a private
  repository with an explicit `self-hosted` runner also produces
  `platform-verify / tests`; `uba` runs `cloud-build` only when Unity-relevant
  files change and requires integrity only (never require cloud-build, which is
  skipped on unrelated PRs). New Unity renders are EditMode-only. A repository
  that also wants the `mise run check` gate adds a `platform-check` caller that
  invokes `ci.yml` with `run-tests: false`; `project-delta` does, producing
  `platform-check / check`. Unity repositories never produce
  `platform-verify / check`; do not require that absent check.
- The check job runs `mise run check`; the test job runs `mise run test` and
  uploads `coverage/` as an artifact. Codecov is off by default; it uploads
  only when the job is enabled and a token is present. An enabled job with no
  token prints a `::warning::`, and a disabled job prints a `::notice::`.
- Security scanning covers trivy, gitleaks, zizmor and actionlint and publishes
  SARIF plus a CycloneDX SBOM.
- Failures open or update an issue labeled `ci-alert` with the workflow, job,
  commit and run URL. The Unity notification also includes
  `devctl verify --profile unity` as the local repro command.
- Renovate opens dependency and action-update PRs once the installed app
  processes the repository; auto-merge uses GitHub's native auto-merge and the
  required checks from the ruleset. Release PRs are handled by `release.yml`.
- Unity runs on a private repository's configured self-hosted Windows runner,
  or through Unity Build Automation; new renders default to `unity-runner:
  none` and integrity only. Public repositories never use self-hosted. GameCI
  is not an active option because the Student named-user license is not a
  supported GameCI activation method.

## Documentation

- [AGENTS.md](AGENTS.md) — repository guidelines and the bounded AI project-intent workflow.
- [docs/MANUAL.ko.md](docs/MANUAL.ko.md) — 매일 쓰는 절차: commit, push, Unity 러너, 릴리스, 장애 대응.
- [docs/MAINTAINING.ko.md](docs/MAINTAINING.ko.md) — 구조, 태그 운영, 도구 업데이트, 저장소 연결.
- [docs/VERIFY.md](docs/VERIFY.md) — the verification contract and `devctl` reference.
- [docs/ADOPTION.md](docs/ADOPTION.md) — new repository, existing repository, rulesets and Renovate.
- [docs/SECRETS.md](docs/SECRETS.md) — Doppler, Codecov, Sentry and GitHub secrets.
- [docs/UNITY-CI.md](docs/UNITY-CI.md) — Unity licensing, runners and UBA.
- [docs/COSTS.md](docs/COSTS.md) — Actions quota and cost controls.
- [docs/CODESCENE.md](docs/CODESCENE.md) — CodeScene setup and its limits.
- [`docs/research/`](docs/research/) — dated evidence notes used for these
  decisions; they are background, not operating instructions.

## License

MIT. See [LICENSE](LICENSE).

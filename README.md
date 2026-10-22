# dev-platform

Reusable verification platform for Unity, .NET, Python and TypeScript
repositories. One command, `devctl`, runs the same steps locally and in GitHub
Actions, with the same arguments and the same report layout.

## Start here

- [docs/MANUAL.ko.md](docs/MANUAL.ko.md) — 매일 쓰는 절차: commit, push, Unity 러너, 릴리스, 장애 대응.
- [docs/MAINTAINING.ko.md](docs/MAINTAINING.ko.md) — 구조, 태그 운영, 도구 업데이트, 새 스택·저장소 추가.

## What it provides

- `devctl` — Python 3.12 CLI (stdlib only, run through `uv`) with profiles for
  `python`, `typescript`, `dotnet`, `unity` and `unity-assets`.
- Reusable workflows — `quality.yml`, `security.yml`, `unity.yml`,
  `release.yml`, `nightly.yml` and `auto-merge.yml`.
- Composite actions — `setup-platform`, `verify`, `security-scan`, `notify`,
  `codecov` and `sentry-sourcemaps`.
- Templates — render a complete starter repository with `devctl init`.
- One version source — [`versions.json`](versions.json) is referenced by the
  CLI, devcontainers, workflows and documentation.

## Quick start

```bash
uv run --project cli devctl init --template python --name my-service --dest ../my-service
cd ../my-service
uv run --project ../dev-platform/cli devctl verify --profile python
```

Adoption into an existing repository takes three steps:

1. Add `.devplatform/config.json` (profile, coverage floor, Unity settings).
2. Copy the caller workflows that call `ghdtmdwns133/dev-platform` at the
   released ref.
3. Run `devctl verify --profile <p>` locally before pushing.

See [docs/ADOPTION.md](docs/ADOPTION.md) for the full procedure, required
status checks and automation settings.

## Profiles

| Profile        | Steps                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------ |
| `python`       | uv sync, ruff check, ruff format, pytest + coverage                                                    |
| `typescript`   | npm ci, tsc, eslint, prettier, vitest + coverage                                                       |
| `dotnet`       | restore, build with warnings as errors, dotnet format, test + coverage                                 |
| `unity`        | integrity, EditMode tests, PlayMode tests, coverage, optional build and coverage upload                |
| `unity-assets` | integrity only (no editor required)                                                                    |

Every step writes a log under `artifacts/reports/<profile>/`; `summary.json`
records status, duration, coverage and test counts. Exit codes are `0` success,
`1` gate failure, `2` precondition missing, `3` execution failure and `4`
required feature absent. The full reference is
[docs/VERIFY.md](docs/VERIFY.md).

## CI behaviour

- `platform-verify` and `platform-security` run independently so a defect turns
  both checks red at once.
- Security scanning covers trivy (vulnerabilities, secrets, misconfiguration),
  gitleaks, zizmor and actionlint, and publishes SARIF plus a CycloneDX SBOM.
- Failures open or update an issue labeled `ci-alert` containing the exact
  local repro command.
- Dependabot patch/minor PRs and PRs labeled `automerge` (from the repository
  owner or `github-actions[bot]`) are auto-merged once required checks pass.
- release-please opens a Release PR from conventional commits; merging it
  creates the tag and the same workflow attaches the built assets.
- Unity runs locally, on a private-repository self-hosted runner, or through
  GameCI when a supported license is available.

## Documentation

- [docs/VERIFY.md](docs/VERIFY.md) — `devctl` reference.
- [docs/ADOPTION.md](docs/ADOPTION.md) — repository adoption and automation.
- [docs/SECRETS.md](docs/SECRETS.md) — Doppler and GitHub secrets.
- [docs/UNITY-CI.md](docs/UNITY-CI.md) — Unity licensing and runners.
- [docs/COSTS.md](docs/COSTS.md) — Actions quota and cost controls.
- [docs/CODESCENE.md](docs/CODESCENE.md) — CodeScene setup.

## License

MIT. See [LICENSE](LICENSE).

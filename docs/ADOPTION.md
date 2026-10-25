# Adopting dev-platform

Repository-wide conventions and the bounded AI project-intent workflow are in
[AGENTS.md](../AGENTS.md). Use this document for the provisioning commands and
ruleset contract.

## New repository: one command

From a dev-platform checkout:

```bash
uv run --script C:/dev/dev-platform/scripts/bootstrap_repo.py \
  --template python \
  --name my-service \
  --dest C:/dev/my-service
```

`--template` is one of `python`, `typescript`, `dotnet`, `unity`, `other`.
Optional flags: `--owner` (default `ghdtmdwns133`), `--visibility private|public`
(default `private`), `--min-coverage` (default 80, validated 0–100), `--platform-ref` (default
`v1`), `--template-source` (default `https://github.com/<owner>/dev-platform`),
`--template-ref` (default latest PEP 440 tag), `--local` (render from this
checkout for development/self-test), `--create-repo`/`--no-create-repo`,
`--render-only`, `--adopt`, `--run-tests`/`--no-run-tests` (`other` only),
`--unity-runner none|self-hosted|uba` (Unity only),
`--enable-codecov`/`--no-enable-codecov` (default off),
`--enable-sentry`/`--no-enable-sentry` (TypeScript only), `--force`, and
`--dry-run`. Run `uv run --script scripts/bootstrap_repo.py --help` for the
exact set in the checkout.

The command is the whole creation path:

1. Renders `template/` with Copier and writes `.copier-answers.yml`.
2. Runs `git init` and the first commit when the destination is not yet a
   repository.
3. Runs `mise trust`, `mise install`, `mise run prepare` when the rendered
   `mise.toml` defines it, and `mise exec -- pre-commit install`.
4. Runs `gh repo create <owner>/<name> --<visibility> --source . --push` when
   the repository does not exist. A repository that already exists is not
   recreated.
5. Applies repository settings: artifact and log retention 14 days, workflow
   permissions read with `can_approve_pull_request_reviews`, auto-merge allowed,
   branch deletion on merge, and vulnerability alerts.
6. Creates the `automerge` and `ci-alert` labels.
7. Creates or updates the `platform-gates` ruleset from the rendered
   `.github/rulesets/platform-gates.json` (non-fast-forward plus the stack's
   required checks, with the repository admin bypass).
8. Sets `CODECOV_TOKEN` only when `--enable-codecov` is explicitly on (the
   default is off) and the environment or Doppler (`dev-platform-shared/prd`)
   supplies it; otherwise prints a notice and continues.
9. When Sentry is enabled and the credentials exist, creates the Sentry project
   and sets its four secrets; otherwise prints a notice and continues.

`--render-only` requires `--template` and stops after Copier: it does no git
initialization, tool/hook installation, GitHub API work or secret handling. It
can still fetch the pinned template and Copier, so it is a local-render path,
not an offline one; only `--dry-run` is network-free and write-free.

`--adopt` requires `--render-only`, `--template other|unity`, and cannot be
combined with `--force`. It overlays the platform with Copier `--skip '*'`, so
**every existing file is preserved**, including `README.md`, native manifests,
lockfiles, `mise.toml`, `.pre-commit-config.yaml` and `.github/workflows/ci.yml`.
Read the skipped-file output rather than assuming integration: merge any missing
tools, hooks and tasks into the preserved files yourself, and keep the platform
caller (or native CI) and the ruleset required checks in agreement. A
successful copy is not proof that CI, tests or coverage are wired. `--adopt`
rejects a destination that is missing or not a directory and refuses a
repository that already has `.copier-answers.yml`; update that repository with
`copier update` instead. Do not use `--adopt` to recopy an existing Copier
repository. After an adopt render, initialize Git if the generator left no
repository or commit, review and stage only intended files, run `mise trust &&
mise install`, run `prepare` only when defined, and install the pre-commit
hook. Merge missing `.gitignore`/`.editorconfig` entries with the tool/hook/CI
changes so report and `.dev-platform` outputs do not dirty the tree. A check
over no tracked files is not evidence of a working gate.

`--run-tests`/`--no-run-tests` are accepted only with `--template other`.
Leave the flag unset unless the native project already has a real `mise run
test` task; then opt in so the caller runs tests and the ruleset can require
`platform-verify / test`. Unity renders are EditMode-only and default to
`unity-runner: none`. `--unity-runner` accepts `none`, `self-hosted` or `uba`;
`self-hosted` is private-only and must not be selected before a runner is
registered. `uba` requires Unity Build Automation credentials.

The settings-only `--root` path is idempotent. Re-running it reconciles
settings, labels and the ruleset; it does not need a new repository and never
prints secret values. Re-running a non-empty `--template` render is refused;
use `copier update` for a template-managed repository. `--dry-run` prints the
Copier command and every planned `gh`/API call without network access,
rendering or writes.

Prerequisites are `uv` (for `uv run --script`), `git`, `mise`, and an
authenticated `gh`. The bootstrap runs a pinned Copier (`uvx copier@9.19.1`).
The canonical source is the full HTTPS URL; `--template-source` also accepts
`gh:<owner>/<repo>` and normalizes it in both the render and
`.copier-answers.yml`. `--local` renders the current checkout at `HEAD` and
rewrites `_src_path` to the canonical HTTPS URL unless an explicit non-`gh`
source was given. The template is
pure-safe: `copier.yml` has no `_tasks`, so a direct render also works and
`copier update` does not need `--trust`:

```bash
uvx copier copy https://github.com/ghdtmdwns133/dev-platform my-service
```

A direct Copier render does not call GitHub APIs or create a repository, but it
still fetches the template over the network. Use the bootstrap for repository
creation and settings; it reports what it completed. `--render-only` is the
bootstrap's local-render path. With `--no-create-repo`, the bootstrap still
queries whether the repository exists; if it does, it reconciles settings and
the ruleset. If it does not, it still performs the local Git/tool/hook setup,
then prints a notice and skips repository creation, settings, ruleset and
secrets. `--no-create-repo` is not a local-only or offline mode. Only
`--dry-run` makes no network calls and no writes.

Existing-checkout reconciliation (a run without `--render-only` that targets an
existing `--root`) requires a clean git checkout at the repository root with no
uncommitted or untracked changes. For an existing repository, `origin` must
resolve exactly to the requested `<owner>/<name>`; the bootstrap fails before
installing tools or changing GitHub settings when it does not. Do not commit or
push unrelated user files merely to satisfy the clean checkout requirement.

After creation, the bootstrap has already run `mise trust`/`mise install`,
`mise run prepare` (where defined), and installed the pre-commit hook:

```bash
cd my-service
mise run check
mise run test   # only when the project defines a real test task
```

A fresh clone later cannot inherit git hooks, so run the one-time setup there:

```bash
mise trust && mise install
mise run prepare
mise exec -- pre-commit install
```

`mise run check`, plus `mise run test`/`mise run build` when the project
defines them, are exactly what CI and release automation run. The mise-managed
toolchain pins live in the generated `mise.toml`; a Unity editor is supplied by
the host and configured in `.devplatform/config.json`. There is no
`versions.json`.

## Naming contract

`--name` (Copier `project_name`) names the generated GitHub repository and the
project distribution: the README/devcontainer title, `pyproject.toml`
`[project].name`, `package.json` `name`, release-please `package-name`, and the
Sentry project slug. It does **not** rename the identifiers inside the starter
samples:

- Python projects keep the import package `devflow`: `src/devflow`,
  `[tool.hatch.build.targets.wheel] packages = ["src/devflow"]`, and
  `from devflow.pipeline import ...`. Only the distribution name follows
  `--name`.
- .NET projects keep the solution `DevFlow.slnx`, the library `DevFlow.Core`,
  its root namespace `DevFlow.Core`, and the packed NuGet package ID
  `DevFlow.Core` (`dist/DevFlow.Core.0.0.0.nupkg`). `--name` does not rename a
  .NET distribution.
- The Unity template is a platform layer copied into an existing Unity project;
  it never renames that project.

The bootstrap passes the name to Copier and derives the Sentry slug from it; it
does not rewrite internal package, project or namespace identifiers. These
templates are starters, not per-project package renamers.

For application code created by an official generator, or when the internal
names must follow the project, use the stack-agnostic `other` layer and add
project-native `mise` tasks (`check`, `test`, `build` as applicable). The
platform adds no language adapter and no naming code, and the shared command
stays `mise run check`.

## Existing repository: adopt or manual adoption

An existing native application or editor-created Unity project should normally
use the overlay instead of hand-copying files:

```bash
uv run --script scripts/bootstrap_repo.py \
  --template other \
  --adopt --render-only \
  --name <repo> --dest <existing-app>
```

For Unity, use `--template unity`; inspect the project's actual
`ProjectSettings/ProjectVersion.txt`, main scene and `.meta` GUID, scene YAML
fileIds, required objects and first enabled build scene before trusting the
rendered `.devplatform/config.json`. New Unity renders are EditMode-only and
default to `unity-runner: none`; do not copy `project-delta` defaults. UBA also
requires `unity.cloudBuild.target` to be set to the real build target id.

`--adopt` legitimately writes `.copier-answers.yml` because Copier now owns the
platform layer's provenance. It rejects a destination that already has that
file: use `copier update` for an existing Copier repository, never a recopy.
Because `--skip '*'` preserves **all** existing files, read the skipped-file
list and merge missing tools, hooks and tasks into the preserved
`mise.toml`/`.pre-commit-config.yaml` yourself. If a native CI workflow already
owns `.github/workflows/ci.yml`, keep it and add the platform caller under a
different filename with the same `platform-verify` and `platform-security` job
IDs, or explicitly keep the native checks and make the ruleset match them. A
successful copy alone does not prove CI or test coverage is integrated.

For a repository where you deliberately do not want Copier provenance, do not
add `.copier-answers.yml`; add the generated surfaces manually:

1. `mise.toml` with the project's real tools and `check`/`test`/`build` tasks
   (only those that actually exist), including the pinned `pre-commit` tool if
   an existing `mise.toml` is preserved.
2. `.pre-commit-config.yaml` with the same hooks the platform runs.
3. `.devplatform/config.json` for a Unity repository (profile, coverage floor,
   scene and integrity settings).
4. Caller workflows: `ci.yml` for non-Unity, or `ci.yml` that calls `unity.yml`
   for Unity (optionally plus a `platform-check` caller using `ci.yml` with
   `run-tests: false`), plus `security.yml`, `nightly.yml` and `release.yml` as
   needed.
5. `renovate.json` with `"extends": ["github>ghdtmdwns133/dev-platform"]`.
6. `release-please-config.json` and `.release-please-manifest.json` for
   non-Unity or private self-hosted Unity repositories that use
   release-please. Public Unity and UBA renders have no release workflow.
7. `.github/rulesets/platform-gates.json` if the bootstrap should reconcile the
   ruleset; the bootstrap prints a notice and skips the ruleset when the file is
   absent.

For the existing `project-delta` repository, the Unity surfaces are the
`.devplatform/config.json` file, the caller `ci.yml` that calls `unity.yml`
with `unity-runner: self-hosted`, and the `platform-check` caller that invokes
`ci.yml` with `run-tests: false`. It is EditMode-only (`unity.testPlatforms` is
`["EditMode"]`). Do not add `.copier-answers.yml`, do not run Unity from
unrelated work, and leave this repository's explicit runner unchanged.

For `project-delta`, verify the actual checks after the first run and include
`platform-check / check` alongside the two Unity checks in the ruleset if the
`platform-check` caller is present.

Reconcile an existing repository with the same bootstrap, omitting `--template`:

```bash
uv run --script C:/dev/dev-platform/scripts/bootstrap_repo.py \
  --root C:/dev/project-delta \
  --owner ghdtmdwns133 \
  --name project-delta \
  --visibility private \
  --dry-run
```

Remove `--dry-run` to apply. It skips `gh repo create`, updates the settings,
labels and ruleset (when the JSON is present), and sets secrets only when their
values are available. Full reconciliation requires a clean git checkout with no
uncommitted or untracked changes. When the remote repository already exists,
the local `origin` must resolve to exactly `<owner>/<name>`; a missing or
different origin exits 1 with clone/reconcile instructions and makes no
settings or ruleset changes. Do not commit unrelated user files just to make
the checkout clean.

## Required status checks

After the first green run, read the actual check names:

```bash
gh api repos/ghdtmdwns133/<repo>/commits/main/check-runs \
  --jq '[.check_runs[].name] | unique'
```

| Repository type | Required checks |
| --------------- | --------------- |
| `python`, `typescript`, `dotnet` | `platform-verify / check`, `platform-verify / test`, `platform-security / scan` |
| `other`, default (`run_tests: false`) | `platform-verify / check`, `platform-security / scan` |
| `other` with a real test task (`run_tests: true`) | `platform-verify / check`, `platform-verify / test`, `platform-security / scan` |
| Unity, `unity-runner: none` (new default) | `platform-verify / integrity`, `platform-security / scan` |
| Unity, private `unity-runner: self-hosted` | `platform-verify / integrity`, `platform-verify / tests`, `platform-security / scan` |
| Unity, `unity-runner: uba` | `platform-verify / integrity`, `platform-security / scan`; cloud-build runs only for Unity-relevant changes and is never required |
| Unity also calling `ci.yml` with `run-tests: false` (project-delta) | add `platform-check / check` to the applicable Unity checks |

New Unity renders are EditMode-only and default to `unity-runner: none`; do not
queue self-hosted jobs for a repository that has no runner, and do not require
`platform-verify / tests` for a `none` render. Public repositories must never
use `self-hosted`.

Unity repositories use `unity.yml` for the Unity gates and never produce
`platform-verify / check`. A repository that also wants the same `mise run
check` gate as non-Unity stacks adds a `platform-check` caller that invokes
`ci.yml` with `run-tests: false`; `project-delta` does this, so its check is
`platform-check / check`. Do not put `platform-verify / check` in a Unity
ruleset: that name never appears there and an absent required check blocks
every pull request.

Never include `notify` or any build job that is normally skipped. Confirm
the names from the command above before writing the ruleset, because a
reusable-workflow job name is `<caller job> / <job id>`.

Create or update the ruleset:

```bash
gh api -X POST repos/ghdtmdwns133/<repo>/rulesets --input - <<'JSON'
{
  "name": "platform-gates",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [
    { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always" }
  ],
  "rules": [
    { "type": "non_fast_forward" },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "platform-verify / check" },
          { "context": "platform-verify / test" },
          { "context": "platform-security / scan" }
        ]
      }
    }
  ]
}
JSON
```

For `other`, omit the `platform-verify / test` context unless a real test task
exists and `run_tests` is true. For a Unity repository, use
`platform-verify / integrity` plus `platform-verify / tests` only for an
explicit private `self-hosted` runner. `uba` keeps integrity only; its
`cloud-build` job runs only when Unity-relevant files change and must not be a
required check. `unity-runner: none` requires integrity only. If it has a
`platform-check` caller, add `platform-check / check` as well. The template
renders the ruleset for the selected `unity_runner`, so do not require a job
that the caller does not schedule. The single bypass is the repository admin role
(`actor_id: 5`), so the owner can still push directly while bots and pull
requests must pass the gates. If a ruleset with the same name exists, update it
with `PUT repos/.../rulesets/<id>` rather than creating a duplicate.
`pull_request_target` is never used.

### Settings the bootstrap applies

The equivalent manual commands are:

```bash
gh api -X PATCH repos/ghdtmdwns133/<repo> \
  -F allow_auto_merge=true -F delete_branch_on_merge=true
gh api -X PUT repos/ghdtmdwns133/<repo>/actions/permissions/artifact-and-log-retention \
  -F days=14
gh api -X PUT repos/ghdtmdwns133/<repo>/actions/permissions/workflow \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
gh api -X PUT repos/ghdtmdwns133/<repo>/vulnerability-alerts
gh label create automerge --color 0e8a16 --description "Merge when required checks pass"
gh label create ci-alert --color b60205 --description "Platform verification failure"
```

`can_approve_pull_request_reviews=true` is required so release-please can open
its Release PR with `GITHUB_TOKEN`. The default workflow permission stays
read-only.

## Renovate

Generated repositories contain:

```json
{ "extends": ["github>ghdtmdwns133/dev-platform"] }
```

The platform repository itself carries the same `renovate.json`; the preset
alone does not onboard dev-platform.

The policy lives in [`default.json`](../default.json): `config:recommended`,
platform auto-merge, auto-merge for minor/patch/digest updates, digest pinning
for GitHub Actions, weekly lock-file maintenance, and grouped Copier updates.

**Installation is a user authorization step.** The user confirmed on
2026-10-24 that the Mend Renovate app is installed for all repositories
(<https://github.com/apps/renovate>). Actual bot run/PR evidence has not yet
been verified; check `gh search prs --owner ghdtmdwns133 --app renovate` before
treating it as active. A repository with `renovate.json` on the default branch
skips the onboarding PR and, once the app processes it, starts receiving update
PRs. Renovate uses GitHub's native
auto-merge (`platformAutomerge`); the repository setting `allow_auto_merge` and
at least one required status check must exist, or GitHub may merge a PR whose
checks failed. The `platform-gates` ruleset supplies the checks.

Dependabot version-update configuration has been removed in favour of Renovate.
Dependabot vulnerability alerts stay enabled. There is no separate auto-merge
workflow: release-please's Release PR is auto-merged by `release.yml`, and
Renovate handles dependency PRs.

### Copier updates

Every generated or adopted repository has `.copier-answers.yml`. `copier update`
applies the template delta in place:

```bash
cd my-service
uvx copier update --defaults
```

Never run a second `copier copy`, `--adopt`, or `--force` over a repository that
already contains `.copier-answers.yml`; that is an update, not a recopy. Review
the update diff before committing, and keep project-owned application files
under the template's update exclusions.

Renovate's Copier manager detects `.copier-answers*.yml`, treats the template
source as a `git-tags` dependency and uses PEP 440 versioning
(<https://docs.renovatebot.com/modules/manager/copier/>). It can open update PRs
only when all of these hold:

- the hosted Renovate app has access to the repository (user-confirmed
  installed; bot evidence pending);
- the template is referenced as a git source, not a local path; and
- the platform publishes PEP 440 git tags (`v1.N.0`), not only the moving `v1`
  tag.

The template contains no dangerous Copier features (`_tasks`, Jinja extensions
or migrations) precisely so the hosted app does not need script permission.
Installation and tagging are still prerequisites; if no update PR appears, run
`copier update` locally. Do not promise automatic Copier PRs before the app and
the semver tags exist.

## Release automation

Non-Unity and private self-hosted Unity repositories contain
`release-please-config.json` and `.release-please-manifest.json`, plus the
caller `release.yml`. Public Unity and UBA renders omit `release.yml` entirely,
so they have no release-please flow and produce no release assets. For the
repositories that do have it,
`release.yml` runs on pushes to `main`, a daily schedule, and manual dispatch. It asks release-please to open or
update the Release PR, labels it `automerge`, and enables GitHub auto-merge with
`gh pr merge --auto --squash`. Merging the Release PR creates the tag. Because a
tag created with `GITHUB_TOKEN` does not trigger another workflow, the same run
builds the tagged tree and attaches the assets.

A Release PR created with `GITHUB_TOKEN` also starts its `pull_request` checks
in `action_required`. The workflow dispatches the caller CI on the Release PR
branch, approves the pending run (it needs `actions: write`), and waits up to
`merge-wait-minutes` (default 15) for auto-merge. If the wait expires, the run
ends with a notice; the next push or schedule can finish the release. The
workflow file is the source of truth for the exact inputs and the
`rebuild-tag` recovery path.

## Failure issues

On failure, the `notify` action creates an issue labeled `ci-alert` or comments
on the open issue with the same title. The body records the workflow, job,
commit, run URL, failed step and the local repro command. Non-Unity repositories
reproduce with `mise run check` / `mise run test`; Unity reproduces with
`devctl verify --profile unity`. The security workflow has no `devctl` profile
and reports the scanner that failed.

## Platform refs and tag record

Consumers reference tags:
`ghdtmdwns133/dev-platform/.github/workflows/<file>@v1` and
`/actions/<name>@v1`. Third-party actions inside the platform are pinned to
commit SHAs with the human-readable tag in a trailing comment.

Two tag families have different jobs:

- `v1` — moving tag used by caller workflows and `platform_ref`.
- `v1.N.0` — immutable PEP 440 tags used by Copier and Renovate for template
  updates.

The integration owner creates and moves these tags; no slice does. Record the
SHA when a tag is created or moved, and keep the table current:

| Tag | Tag object | Commit SHA | Date | Notes |
| --- | ---------- | ---------- | ---- | ----- |
| `v1` | `51082548bcf6c23e83f25b1da6ce5c1125da9109` | `e3869334914342edfe4a1f26bed439c5d74412f7` | 2026-10-26 | Moving alias; callers resolve it. Updated after [CI run 40224152661](https://github.com/ghdtmdwns133/dev-platform/actions/runs/40224152661) passed. |
| `v1.2.0` | `79b4974d5a0ca8811e6e7af7c5a4d41c20c8d7cc` | `e3869334914342edfe4a1f26bed439c5d74412f7` | 2026-10-26 | Immutable Copier/Renovate version; published atomically with `v1` after the same green run. |
| `v1.1.0` | `6b5fcc233441b44ba3addda92a610846a314a21b` | `b6ee2db283ea63b5c99b3c4e89540332a06f871a` | 2026-10-26 | Historical immutable version. Created **last** in that release, with a strictly later taggerdate. |

`git describe --tags --always b6ee2db283ea63b5c99b3c4e89540332a06f871a`
returns `v1.1.0`; the newer
`git describe --tags --always e3869334914342edfe4a1f26bed439c5d74412f7`
returns `v1.2.0`. Copier reports the selected template version.

Every consumer must use a `v1` or `v1.N.0` whose workflows, template and CLI are
consistent. Do not move `v1` to a red commit. The release procedure is
**alias first, version last**: create annotated `v1` and the immutable
`v1.N.0` locally, with a strictly later taggerdate for the version tag (a plain
one-second gap between the two `git tag -a` calls is enough); assert
that `git describe` returns `v1.N.0`; only then publish both refs in one atomic
push, `git push --atomic origin +refs/tags/v1 refs/tags/v1.N.0`. The force
applies to the moving alias only: the immutable ref is pushed without `+`, so
the server rejects an overwrite. A failed assertion or a failed atomic push
publishes nothing, so the local tags can be recreated; a published `v1.N.0`
never moves. To correct a published release, land a fix on `main`, turn CI
green, and publish a new patch/version with the same procedure. Do not move
`v1` back onto older template content: the version `git describe` selects at
that commit would no longer match the tree the alias points at, which corrupts
Copier provenance. Do not move tags after the documentation commit.

## Secrets and services

See [SECRETS.md](SECRETS.md) for Doppler, Codecov, Sentry and token handling.
CodeScene is documented in [CODESCENE.md](CODESCENE.md); installing its GitHub
App and creating projects remain manual actions.

# Adopting dev-platform

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
(default `private`), `--min-coverage` (default 80), `--platform-ref` (default
`v1`), `--create-repo`/`--no-create-repo`, `--enable-codecov`/`--no-enable-codecov`,
`--enable-sentry`/`--no-enable-sentry` (TypeScript only), `--force`, and
`--dry-run`. Run `uv run --script scripts/bootstrap_repo.py --help` for the
exact set in the checkout.

The command is the whole creation path:

1. Renders `template/` with Copier and writes `.copier-answers.yml`.
2. Runs `git init` and the first commit when the destination is not yet a
   repository.
3. Runs `gh repo create <owner>/<name> --<visibility> --source . --push` when
   the repository does not exist. A repository that already exists is not
   recreated.
4. Applies repository settings: artifact and log retention 14 days, workflow
   permissions read with `can_approve_pull_request_reviews`, auto-merge allowed,
   branch deletion on merge, and vulnerability alerts.
5. Creates the `automerge` and `ci-alert` labels.
6. Creates or updates the `platform-gates` ruleset from the rendered
   `.github/rulesets/platform-gates.json` (non-fast-forward plus the stack's
   required checks, with the repository admin bypass).
7. Sets `CODECOV_TOKEN` when `--enable-codecov` is on and the environment or
   Doppler (`dev-platform-shared/prd`) supplies it; otherwise prints a notice
   and continues.
8. When Sentry is enabled and the credentials exist, creates the Sentry project
   and sets its four secrets; otherwise prints a notice and continues.

The bootstrap is idempotent. Re-running it reconciles settings, labels and the
ruleset; it does not need a new repository and never prints secret values.
`--dry-run` prints the Copier command and every planned `gh`/API call without
network access, rendering or writes.

Prerequisites are `uv` (for `uv run --script`), `git`, and an authenticated
`gh`. The bootstrap runs a pinned Copier (`uvx copier@9.19.1`). The template is
pure-safe: `copier.yml` has no `_tasks`, so a direct render also works and
`copier update` does not need `--trust`:

```bash
uvx copier copy gh:ghdtmdwns133/dev-platform my-service
```

A direct Copier render never touches GitHub; `create_github_repo` only controls
whether the post-copy message prints the bootstrap step. Use the bootstrap for
repository creation and settings. With `--no-create-repo`, the bootstrap still
checks whether the repository exists; if it does not, it prints a notice and
skips settings and the ruleset. `--dry-run` is the no-network path.

After creation:

```bash
cd my-service
mise trust
mise install
mise exec -- pre-commit install   # optional, for staged-file checks
mise run check
mise run test
```

`mise run check` and `mise run test` are exactly what `ci.yml` runs. The
mise-managed toolchain pins live in the generated `mise.toml`; a Unity editor
is supplied by the host and configured in `.devplatform/config.json`. There is
no `versions.json`.

## Existing repository (manual adoption)

Copier updates apply only to a repository generated from the template and
carrying `.copier-answers.yml`. Do not add that file to an existing repository
just to claim provenance; a hand-migrated repository has no Copier history, and
`copier update` would be misleading.

For an existing repository, add the generated surfaces explicitly:

1. `mise.toml` with the stack's `[tools]` and `check`/`test`/`build` tasks.
2. `.pre-commit-config.yaml` with the same hooks the platform runs.
3. `.devplatform/config.json` for a Unity repository (profile, coverage floor,
   scene and integrity settings).
4. Caller workflows: `ci.yml` for non-Unity, or `ci.yml` that calls `unity.yml`
   for Unity (optionally plus a `platform-check` caller using `ci.yml` with
   `run-tests: false`), plus `security.yml`, `nightly.yml` and `release.yml` as
   needed.
5. `renovate.json` with `"extends": ["github>ghdtmdwns133/dev-platform"]`.
6. `release-please-config.json` and `.release-please-manifest.json` when the
   repository uses release-please.
7. `.github/rulesets/platform-gates.json` if the bootstrap should reconcile the
   ruleset; the bootstrap prints a notice and skips the ruleset when the file is
   absent.

For the existing `project-delta` repository, the Unity surfaces are the
`.devplatform/config.json` file, the caller `ci.yml` that calls `unity.yml`
with `unity-runner: self-hosted`, and the `platform-check` caller that invokes
`ci.yml` with `run-tests: false`. It is EditMode-only (`unity.testPlatforms` is
`["EditMode"]`). Do not add `.copier-answers.yml`.

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
values are available.

## Required status checks

After the first green run, read the actual check names:

```bash
gh api repos/ghdtmdwns133/<repo>/commits/main/check-runs \
  --jq '[.check_runs[].name] | unique'
```

| Repository type | Required checks |
| --------------- | --------------- |
| `python`, `typescript`, `dotnet` | `platform-verify / check`, `platform-verify / test`, `platform-security / scan` |
| `other` | `platform-verify / check`, `platform-security / scan` (no test task) |
| Unity with only `unity.yml` | `platform-verify / integrity`, `platform-verify / tests`, `platform-security / scan` |
| Unity also calling `ci.yml` with `run-tests: false` (project-delta) | `platform-check / check` plus the three Unity checks above |

Unity repositories use `unity.yml` for the Unity gates and never produce
`platform-verify / check`. A repository that also wants the same `mise run
check` gate as non-Unity stacks adds a `platform-check` caller that invokes
`ci.yml` with `run-tests: false`; `project-delta` does this, so its check is
`platform-check / check`. Do not put `platform-verify / check` in a Unity
ruleset: that name never appears there and an absent required check blocks
every pull request.

Never include `notify` or any build/GameCI job that is normally skipped. Confirm
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

For `other`, omit the `platform-verify / test` context. For a Unity repository,
replace the first two contexts with `platform-verify / integrity` and
`platform-verify / tests`; if it has a `platform-check` caller, add
`platform-check / check` as well. The single bypass is the repository admin role
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

Every generated repository has `.copier-answers.yml`. `copier update` applies
the template delta in place:

```bash
cd my-service
uvx copier update --defaults
```

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

Generated repositories (except `other`) contain `release-please-config.json`
and `.release-please-manifest.json`. The caller `release.yml` runs on pushes to
`main`, a daily schedule, and manual dispatch. It asks release-please to open or
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

| Tag | Commit SHA | Date | Notes |
| --- | ---------- | ---- | ----- |
| `v1` | record at release | — | moving; callers resolve it |
| `v1.N.0` | record at release | — | immutable template version |

Every consumer must use a `v1` or `v1.N.0` whose workflows, template and CLI are
consistent. Do not move `v1` to a red commit.

## Secrets and services

See [SECRETS.md](SECRETS.md) for Doppler, Codecov, Sentry and token handling.
CodeScene is documented in [CODESCENE.md](CODESCENE.md); installing its GitHub
App and creating projects remain manual actions.

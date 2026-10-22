# Adopting dev-platform

## Three steps

1. **Configure the repository.** Add `.devplatform/config.json`:

   ```json
   {
     "profile": "python",
     "reports": "artifacts/reports",
     "coverage": { "minimum": 85, "enabled": true }
   }
   ```

   `profile` is required. Unity projects also add the `unity` block
   (`version`, `scene`, `sceneGuid`, `requiredObjects`, `allowedScriptRoots`,
   `templateScripts`, `externalGuidBaseline`, `testPlatforms`, `buildTarget`,
   `odinEntryPoint`). Unknown keys are rejected so typos fail fast.

2. **Copy the caller workflows.** Start from `devctl init` or copy
   `.github/workflows/ci.yml` and `nightly.yml` from a rendered template. The
   jobs must stay named `platform-verify`, `platform-security`,
   `platform-unity`, `platform-release` and `platform-nightly`; those names are
   the stable status-check surface.

   ```yaml
   jobs:
     platform-verify:
       name: platform-verify
       permissions: { contents: read, issues: write }
       uses: ghdtmdwns133/dev-platform/.github/workflows/quality.yml@v1
     platform-security:
       name: platform-security
       permissions:
         contents: read
         issues: write
         security-events: write
         actions: read
       uses: ghdtmdwns133/dev-platform/.github/workflows/security.yml@v1
   ```

   Pass secrets explicitly. `secrets: inherit` is not used on a personal
   account.

3. **Run it locally.** Bootstrap the platform once, then run the same command:

   ```bash
   ./scripts/bootstrap.sh            # or scripts/bootstrap.ps1
   uv run --project .dev-platform/cli devctl verify --profile python
   ```

   `bootstrap` checks for uv, Node, .NET and Docker; missing tools are reported
   with install instructions and the script stops instead of installing
   silently. It runs `uv sync --project cli`, `devctl versions --check` and
   `devctl hooks install`. `devctl init` also installs the hook. The pre-commit
   hook checks only staged files: ruff (Python), eslint/prettier (TypeScript),
   `dotnet format --include` (.NET) and `unity integrity` (Unity, no editor
   required).

## Platform ref and SHA record

Consumers reference tags: `ghdtmdwns133/dev-platform/.github/workflows/<file>@v1`
and `/actions/<name>@v1`. Third-party actions inside the platform are pinned to
commit SHAs with the human-readable tag in a trailing comment.

The `v1` tag must point at a commit whose workflows and CLI are consistent.
Record the SHA when the tag is created (the integration owner creates tags; no
slice commits them):

```bash
git rev-parse v1
```

Publish that SHA in the release notes and keep this document updated with the
tag, date and SHA whenever the tag moves.

## Repository settings

Apply these with the API (owner is `ghdtmdwns133`, repository is the consumer):

```bash
gh api -X PATCH repos/ghdtmdwns133/<repo> -F allow_auto_merge=true -F delete_branch_on_merge=true
gh api -X PUT repos/ghdtmdwns133/<repo>/actions/permissions/artifact-and-log-retention -F days=14
gh api -X PUT repos/ghdtmdwns133/<repo>/actions/permissions/workflow \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
gh api -X PUT repos/ghdtmdwns133/<repo>/vulnerability-alerts
```

`can_approve_pull_request_reviews=true` is required so release-please can open
its Release PR with `GITHUB_TOKEN`. The default workflow permission stays
read-only.

`pull_request_target` is never used.

## Required status checks

After the first green run, list the real check names:

```bash
gh api repos/ghdtmdwns133/<repo>/commits/main/check-runs --jq '[.check_runs[].name] | unique'
```

Reusable workflows report names of the form `platform-verify / verify` and
`platform-security / scan`. Unity callers use `platform-verify` for the
`unity.yml` gate, so their checks are `platform-verify / integrity` plus
`platform-verify / tests` (self-hosted or GameCI mode, when Unity files
changed); `build` and `odin-gameci` appear only when those inputs are enabled.
Keep only the gate jobs (never `notify`) in the ruleset, and always confirm the
real names with the command above before writing them down. Then create or
update the `platform-gates` ruleset:

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
          { "context": "platform-verify / verify" },
          { "context": "platform-security / scan" }
        ]
      }
    }
  ]
}
JSON
```

The single bypass is `RepositoryRole` admin (`actor_id: 5`), so the owner can
still push directly while bots and pull requests must pass the gates. If a
ruleset with the same name exists, update it with
`PUT repos/.../rulesets/<id>` instead of creating a duplicate.

For `dev-platform` itself the required checks are `cli`, `templates (python)`,
`templates (typescript)`, `templates (dotnet)` and `workflow-lint`.

Callers ignore docs-only changes through `paths-ignore` (`docs/**`,
`**/*.md`). A docs-only pull request therefore has no reported checks; merge it
as an admin or include a code change if the ruleset must be satisfied.

## Auto-merge

The caller `.github/workflows/auto-merge.yml` triggers on
`pull_request: [opened, labeled, synchronize, reopened]` and calls the shared
`auto-merge.yml`. The workflow enables `gh pr merge --auto --squash` when:

- the pull request author is `dependabot[bot]` and the update is
  semver-patch or semver-minor, or
- the pull request has the `automerge` label and the author is the repository
  owner or `github-actions[bot]` (release-please).

Create the label once:

```bash
gh label create automerge --color 0e8a16 --description "Merge when required checks pass"
```

Merging still depends on the ruleset's required checks; the workflow only
enables auto-merge.

Dependabot nuance: runs triggered by Dependabot pull requests receive a
read-only `GITHUB_TOKEN` and no secrets unless the workflow declares
permissions, and GitHub may still downgrade the token for Dependabot events.
When `gh pr merge --auto` fails, the step reports a warning and leaves the pull
request for manual merge.

## Release automation

Each template contains `release-please-config.json` and
`.release-please-manifest.json` (initial version `0.0.0`). The caller
`.github/workflows/release.yml` runs on pushes to `main` and calls the shared
release workflow.

The shared workflow runs release-please, labels its Release PR `automerge`,
enables auto-merge on it, and when `release_created` is true, builds and uploads
the assets in the same workflow. Tags created with `GITHUB_TOKEN` do not trigger
other workflows, so the assets are built in the same run.

`GITHUB_TOKEN`-authored pull requests also do not trigger `pull_request`
workflows, so their required checks never appear by themselves. While the
Release PR is open, the workflow dispatches the caller CI on the Release PR
branch:

```bash
gh workflow run ci.yml --ref <release-pr-branch>
```

`workflow_dispatch` is allowed with `GITHUB_TOKEN`, and the resulting check runs
attach to the head SHA, satisfying the ruleset. The workflow file name is the
`ci-workflow` input (default `ci.yml`); the caller workflow must declare
`workflow_dispatch`. The release job needs `actions: write` and the template
caller grants it. No personal access token is required.

The repository setting `can_approve_pull_request_reviews=true` is required for
release-please to create the Release PR with `GITHUB_TOKEN`; the integration
owner sets it.

The build job runs on `runs-on`, a JSON string of runner labels
(default `'"ubuntu-latest"'`). Unity repositories can pass
`'["self-hosted","windows","unity"]'` and use a PowerShell build command.

### Completing a release without a human push

The template callers also trigger on `workflow_run` for the `CI` workflow, a
daily schedule (`23 4 * * *`) and `workflow_dispatch`. The push run creates or
updates the Release PR, labels it `automerge`, enables auto-merge and dispatches
CI on the Release PR branch. A Release PR created with `GITHUB_TOKEN` lands its
pull-request CI run in `action_required`, so the release job approves that run
(`actions: write`) and then waits up to 15 minutes for auto-merge to merge the
PR. After the merge it checks out the updated default branch and runs
release-please a second time, so `release_created` becomes true in the same
workflow run and the build/publish jobs attach the assets. The build jobs check
out the release tag, not the triggering commit, so the artifact version always
matches the tag.

The `workflow_run` path remains for CI runs started by a trusted actor (for
example a manual re-run): it merges the Release PR with `gh pr merge --squash
--match-head-commit <sha>`, or observes that auto-merge already merged it, then
runs release-please on the default branch. GitHub suppresses `workflow_run`
after runs created by `GITHUB_TOKEN`, which is why the push run performs the
approval and wait itself instead of relying on that trigger alone.

Safety: the `workflow_run` job never checks out the upstream head branch and
never executes code from it. It only calls `gh` APIs, merges a PR whose branch
starts with `release-please--`, re-checks out the default branch and runs
release-please. The inline `zizmor: ignore[dangerous-triggers]` comment in the
caller documents this. Release-please is idempotent on existing tags, so a later
schedule or human push cannot create a duplicate release.

## Failure issues

On failure, the `notify` action creates an issue labeled `ci-alert` or comments
on the open issue with the same title, and records the workflow, job, commit,
run URL, failed step and the exact local repro command
(`devctl verify --profile <p>`). Quality, nightly and Unity workflows pass the
profile they ran; the security workflow does not run a `devctl verify` profile.

## Secrets and services

See [SECRETS.md](SECRETS.md) for Doppler, Codecov, Sentry and token setup.

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
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
gh api -X PUT repos/ghdtmdwns133/<repo>/vulnerability-alerts
```

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
permissions, and GitHub may still downgrade the token for Dependabot events. If
`AUTOMERGE_TOKEN` (fine-grained PAT with contents and pull-requests write) is
configured, it is used instead. Without it, `gh pr merge --auto` can fail; the
step reports a warning and leaves the pull request for manual merge. Copilot
pull requests are never auto-merged.

## Release automation

Each template contains `release-please-config.json` and
`.release-please-manifest.json` (initial version `0.0.0`). The caller
`.github/workflows/release.yml` runs on pushes to `main` and calls the shared
release workflow.

The shared workflow runs release-please, labels its Release PR `automerge`, and
when `release_created` is true, builds and uploads the assets in the same
workflow. This is necessary because tags created with `GITHUB_TOKEN` do not
trigger other workflows.

`GITHUB_TOKEN`-authored pull requests also do not trigger `pull_request`
workflows, so their required checks never report. Configure a fine-grained PAT
as `RELEASE_TOKEN` and pass it to the shared workflow to let release PRs run
CI; otherwise merge the release PR with the admin bypass. The workflow accepts
`release_token` and falls back to `github.token`.

The build job runs on `runs-on`, a JSON string of runner labels
(default `'"ubuntu-latest"'`). Unity repositories can pass
`'["self-hosted","windows","unity"]'` and use a PowerShell build command.

## Copilot gates and failure issues

The templates include `.github/workflows/copilot-setup-steps.yml`. Its job must
be named `copilot-setup-steps`; it checks out dev-platform, installs the
language toolchain and runs `devctl verify`, so the Copilot cloud agent uses
the same gate as humans. Copilot pull requests wait for workflow approval;
keep the repository default rather than disabling the approval requirement.

On failure, the `notify` action creates an issue labeled `ci-alert` or comments
on the open issue with the same title, and records the workflow, job, commit,
run URL and failed step. When the `COPILOT_ASSIGN_TOKEN` secret is present the
issue is assigned to Copilot; otherwise a notice is emitted.

## Secrets and services

See [SECRETS.md](SECRETS.md) for Doppler, Codecov, Sentry and token setup.

# Actions quota and cost controls

## Facts

- Standard GitHub-hosted runners are free for public repositories.
- This account has GitHub Pro (Student): private Actions minutes are 3,000 per
  month, artifact and package storage is 1 GB, and the Actions cache is 10 GB
  per repository
  (<https://docs.github.com/en/billing/concepts/product-billing/github-actions>).
- Without a payment method, usage stops when the quota is exhausted. With a
  payment method, overage is charged unless a spending limit stops usage.
- Budgets and spending limits are configured only in the billing UI:
  `https://github.com/settings/billing/budgets`. The REST budget API is
  organization-only.
- Renovate Community Cloud is free for personal accounts and private
  repositories (<https://github.com/marketplace/renovate>). Its pull requests
  still trigger Actions checks, which consume the repository's minutes.
- Unity Build Automation's free tier is 200 Windows build minutes per month;
  when they are exhausted, builds stop unless the organization has a payment
  method on file (<https://support.unity.com/hc/en-us/articles/34748492914964-Understanding-of-New-Unity-DevOps-Pricing-starting-from-Mar-1-2026>).
- Public repositories use free standard runners; the Unity self-hosted runner
  is never attached to a public repository.

## Controls in this platform

- Every reusable job sets `timeout-minutes`. Callers set `concurrency`; the
  Unity test job also uses a `unity-<repo>` group so only one editor touches
  the project at a time.
- Artifacts are retained for 14 days (`retention-days: 14` and the repository
  artifact-and-log-retention setting).
- Docs-only changes are ignored by callers through `paths-ignore`
  (`docs/**`, `**/*.md`), so they do not consume a run.
- `project-delta` runs Unity on its self-hosted Windows runner. Private
  hosted-runner usage is limited to the Ubuntu `integrity` job and the security
  scan, about two to three minutes per relevant run.
- Unity tests are filtered to changes under `Assets/`, `Packages/` or
  `ProjectSettings/`; unrelated pushes skip the editor.
- Builds are excluded from the default verification. They run on tags, nightly
  runs, or an explicit workflow dispatch.
- Unity coverage upload is opt-in locally and runs in the self-hosted test job
  only when `CODECOV_TOKEN` is present. The Codecov private plan allows 250
  uploads per month.
- Renovate groups Copier template updates and automerges minor/patch/digest
  PRs through GitHub's native auto-merge. Each PR still runs the required checks; the
  ruleset decides whether it merges. Dependabot version-update configs are
  removed; Dependabot alerts (vulnerability alerts) stay enabled.
- Copilot cloud agent is not used by the pipeline. Failure issues record the
  workflow, job, commit and run URL and the failed step; the Unity notification
  also includes `devctl verify --profile unity` as the local repro command.
- `devctl` has no usage command. Query usage directly:

  ```bash
  gh auth refresh -h github.com -s user
  gh api /users/ghdtmdwns133/settings/billing/usage/summary
  ```

## User action

Registering a payment method and setting a $0 Actions/Codespaces budget with
"Stop usage when budget limit is reached" is a billing UI action for the
account owner. The platform reports the configured state; it cannot change it.
The same applies to the Unity Build Automation payment setting and to keeping
UBA usage inside the free monthly allowance.

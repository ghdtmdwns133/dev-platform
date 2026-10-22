# Actions quota and cost controls

## Facts

- Standard GitHub-hosted runners are free for public repositories.
- This account has GitHub Pro (Student): private Actions minutes are 3,000 per
  month, artifact and package storage is 1 GB, and the Actions cache is 10 GB
  per repository.
- Without a payment method, usage stops when the quota is exhausted. With a
  payment method, overage is charged unless a spending limit stops usage.
- Budgets and spending limits are configured only in the billing UI:
  `https://github.com/settings/billing/budgets`. The REST budget API is
  organization-only.
- Copilot code review and cloud agent sessions consume Actions minutes on
  private repositories.
- Public repositories use free standard runners; the Unity self-hosted runner
  is never attached to a public repository.

## Controls in this platform

- Every job sets `timeout-minutes`.
- Every non-reusable workflow sets `concurrency`; PR runs cancel in progress.
- Artifacts are retained for 14 days (`retention-days: 14` and the repository
  artifact-and-log-retention setting).
- Callers and `self-test` ignore docs-only changes with
  `paths-ignore: [docs/**, "**/*.md"]`.
- `project-delta` runs Unity locally or on its self-hosted runner, so private
  hosted-runner usage is limited to the integrity and security jobs (about two
  to three minutes per run).
- Dependabot is grouped: minor and patch updates share one PR per ecosystem,
  major updates get their own, and the open PR limit is 5.
- Unity coverage upload is opt-in and local; it is never part of a CI run.
- `devctl` has no usage command. Query usage directly:

  ```bash
  gh auth refresh -h github.com -s user
  gh api /users/ghdtmdwns133/settings/billing/usage/summary
  ```

## User action

Registering a payment method and setting a $0 Actions/Codespaces budget with
"Stop usage when budget limit is reached" is a billing UI action for the
account owner. The platform reports the configured state; it cannot change it.

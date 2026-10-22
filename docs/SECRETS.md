# Secrets and service credentials

No credential is committed to a repository. `.env` and `.env.*` are ignored by
every template; CI reads credentials only from GitHub Actions secrets, and
local runs read them from the environment through `doppler run --`.

## Doppler layout

Doppler Team is the source of truth. Each repository has one Doppler project
with two configs:

- `dev` — injected locally with `doppler run -- <command>`.
- `ci` — synchronized one-way to that repository's GitHub Actions secrets
  through the Doppler GitHub integration.

Local binding uses a `doppler.yaml` at the repository root:

```yaml
setup:
  - project: <repo>
    config: dev
```

The `doppler.yaml` schema is not verified for this stack. If the file does not
work, delete it and run the equivalent local-only setup:

```bash
doppler setup --project <repo> --config dev
```

The workflows reference only `secrets.<NAME>`, so the platform has no runtime
Doppler dependency.

## Secret list

| Repository     | Secret                | Purpose                                             |
| -------------- | --------------------- | --------------------------------------------------- |
| `dev-flow-py`  | `CODECOV_TOKEN`       | Codecov upload.                                     |
| `dev-flow-web` | `CODECOV_TOKEN`       | Codecov upload.                                     |
| `dev-flow-web` | `SENTRY_AUTH_TOKEN`   | Source map upload and live event verification.      |
| `dev-flow-web` | `SENTRY_ORG`          | Sentry organization slug.                           |
| `dev-flow-web` | `SENTRY_PROJECT`      | Sentry project slug.                                |
| `dev-flow-web` | `VITE_SENTRY_DSN`     | Browser DSN (public value, managed with the rest).  |
| `project-delta`| `CODECOV_TOKEN`       | Local Unity coverage upload.                        |
| `dev-platform` | —                     | No service secrets.                                 |

`UNITY_LICENSE`, `UNITY_EMAIL` and `UNITY_PASSWORD` exist only for the GameCI
runner mode. The Student named-user license cannot be activated through GameCI,
so these stay unset.

No personal access token is required by the automation: auto-merge, release
PRs and failure issues use `github.token`.

## Fallback without Doppler

Set secrets directly and export them locally:

```bash
gh secret set CODECOV_TOKEN -R ghdtmdwns133/<repo>
export CODECOV_TOKEN="..."
```

Codecov uploads stay skipped with `::notice::Codecov skipped (no token)` when
the token is absent, but that state is reported as "not connected", not as a
completed integration. Sentry source map upload follows the same rule
(`::notice::SENTRY_AUTH_TOKEN not set;`).

## Unity coverage upload

`devctl unity coverage-upload` reads `CODECOV_TOKEN` from the environment only;
there is no token argument to keep it out of shell history. The command refuses
to run on a dirty worktree or on a commit that is not on a remote branch,
because Codecov only accepts commits that exist on GitHub.

```bash
doppler run -- uv run --project C:/dev/dev-platform/cli devctl verify \
  --profile unity --upload-coverage
```

Private Developer plans allow 250 uploads per month, so upload stays opt-in and
never runs in CI.

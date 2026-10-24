# Secrets and service credentials

No credential value is committed to a repository. `.env` and `.env.*` are
ignored by every generated repository. CI reads credentials only from GitHub
Actions secrets; local Unity coverage upload reads them from the environment,
usually through `doppler run --`.

## Scope facts

GitHub Actions secrets exist at repository, environment and organization scope;
a personal account has no account-level Actions secret store
(<https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets>).
Organization secrets are not available to private repositories on a free
organization. This platform therefore writes secrets per repository through
`gh secret set` or a per-repository sync. A rule or settings change also applies
to one repository at a time; the bootstrap reconciles each repository
individually.

Doppler's GitHub integration is one-way: it writes a config's values into one
repository's Actions secrets. A sync is bound to one repository, so a newly
created repository needs a new sync; Doppler does not import existing GitHub
secrets because GitHub never exposes their values
(<https://docs.doppler.com/docs/github-actions>).

## Doppler layout

Doppler Team is the source of truth.

- A shared project `dev-platform-shared`, config `prd`, holds the
  `CODECOV_TOKEN` used by the bootstrap when the Doppler CLI is logged in.
- Each repository that needs its own secrets has a Doppler project and a `ci`
  config synchronized one-way to that repository's Actions secrets.
- Local runs use the same project's `dev` config through
  `doppler run -- <command>`. Local binding can use a root `doppler.yaml`:

  ```yaml
  setup:
    - project: <repo>
      config: dev
  ```

  The `doppler.yaml` schema is not verified for this stack. If it does not
  work, delete it and run the local-only equivalent
  `doppler setup --project <repo> --config dev`.

The workflows reference only `secrets.<NAME>`, so the platform has no runtime
Doppler dependency. If a secret is absent, the consuming job prints a `::notice::`
or `::warning::` and continues; that state is reported as "not connected", not
as a completed integration.

## Secret list

| Consumer | Secret | Purpose |
| -------- | ------ | ------- |
| Any Codecov consumer | `CODECOV_TOKEN` | Coverage upload. |
| Any TypeScript consumer with Sentry | `SENTRY_AUTH_TOKEN` | Token with `event:read`, `project:read`, `project:releases`; source map upload and live event verification. |
| Any TypeScript consumer with Sentry | `SENTRY_ORG` | Sentry organization slug. |
| Any TypeScript consumer with Sentry | `SENTRY_PROJECT` | Sentry project slug. |
| Any TypeScript consumer with Sentry | `VITE_SENTRY_DSN` | Browser DSN (a public value, managed with the rest). |
| Unity Build Automation consumer | `UNITY_BUILD_API_KEY`, `UNITY_BUILD_ORG_ID`, `UNITY_BUILD_PROJECT_ID` | UBA builds; see [UNITY-CI.md](UNITY-CI.md). |

GameCI is not an active runner option. The Student named-user license is not a
GameCI-supported activation method, so no `UNITY_LICENSE`, `UNITY_EMAIL` or
`UNITY_PASSWORD` secrets are used; they are listed here only as a historical
constraint from [UNITY-CI.md](UNITY-CI.md).

The bootstrap reads `CODECOV_TOKEN` from the environment or, when the Doppler
CLI is available, from `doppler secrets get CODECOV_TOKEN --plain --project
dev-platform-shared --config prd`. It never prints the value. If the token is
missing it prints a notice and continues; it does not fail the repository
creation.

Sentry project creation is an explicit API action, not a side effect of
installing the GitHub App. When `enable_sentry` is set and the credentials are
present, the bootstrap creates the project through
`POST /api/0/teams/{org}/{team}/projects/`, reads the DSN, and sets the four
Sentry secrets. Without credentials it prints a notice and leaves the project
to be created manually
(<https://docs.sentry.io/api/projects/create-a-new-project/>).

## Codecov details

- Private-repository uploads require a token; public repositories may be
  tokenless depending on the organization's token-authentication setting
  (<https://docs.codecov.com/docs/codecov-tokens>).
- The Codecov GitHub App controls which repositories Codecov can see, but a
  private upload still needs a credential; installing the app for all
  repositories does not remove the per-repository secret.
- `codecov/codecov-action` also supports OIDC (`use_oidc: true` with
  `id-token: write`), which avoids an upload token
  (<https://github.com/codecov/codecov-action#using-oidc>). The current
  `ci.yml` path uses `CODECOV_TOKEN`; Unity's local upload also uses the token.
  OIDC is an alternative, not a claim about the configured workflow.
- A Codecov account owner can create a global upload token that works for all
  repositories, but it still has to be stored in each repository's Actions
  secrets. Whether this account's plan can create one is unverified; treat it
  as the owner's assumption rather than a guaranteed capability.

## Fallback without Doppler

Set the secret directly and export it for local commands:

```bash
gh secret set CODECOV_TOKEN -R ghdtmdwns133/<repo>
export CODECOV_TOKEN="..."
```

## Rotation and expiry

Authorizations are not lifetime grants. GitHub App installations can be
removed or lose repository access, tokens can be revoked or rotated, and
service plans can expire:

- The Sentry Education plan is documented as free for one year
  (<https://sentry.io/for/education/>); renew it before the organization's
  quota or plan changes.
- Codecov, CodeScene, Sentry and Renovate app authorizations are account-level
  grants; removing or narrowing an installation stops uploads or checks even
  though the repository files are unchanged.
- Doppler service tokens and syncs can be rotated; update the GitHub secret or
  let the sync overwrite it.
- Re-run the idempotent bootstrap with `--dry-run` first after a token or
  settings change, then apply it. It updates settings, labels and the ruleset
  without creating a new repository.

## Unity coverage upload

`devctl unity coverage-upload` reads `CODECOV_TOKEN` from the environment only;
there is no token argument, which keeps it out of shell history. It refuses a
dirty worktree or a commit that is not on a remote branch, because Codecov
accepts only commits that exist on GitHub.

```bash
doppler run -- uv run --project <path-to-dev-platform>/cli devctl verify \
  --profile unity --upload-coverage
```

The private Developer plan allows 250 uploads per month, so the local upload
stays opt-in. `unity.yml` also uploads from the self-hosted test job when
`CODECOV_TOKEN` is set and the change touched Unity files.

## Repository rule

Never commit a token, DSN secret, app private key or `.env` file. The templates
ignore `.env*`; the security workflow runs gitleaks over the full history and
will keep reporting a secret that was committed in the past even after it is
revoked. Rotate the credential first, then decide whether history rewriting is
justified.

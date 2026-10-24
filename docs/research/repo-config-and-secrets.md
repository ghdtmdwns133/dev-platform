# Repository configuration and secrets on a personal GitHub account

Research date: 2026-10-24. Scope: `ghdtmdwns133` (personal account, GitHub Pro), no paid resources, no Azure, no Copilot in the pipeline. Claims are limited to what the linked primary sources state; observations made with `gh api` are labelled as such.

## 1. Repository settings as code for a personal account

### 1.1 Probot Settings app (`repository-settings/app`)

**Status: active.** The hosted app is still published and installable from <https://github.com/apps/settings>. The repository's latest release is `v5.0.14` (2026-08-29) and the default branch was last pushed 2026-10-22 (<https://github.com/repository-settings/app/releases>, <https://github.com/repository-settings/app>). It is a Probot app that syncs `.github/settings.yml` from the default branch to GitHub (<https://github.com/repository-settings/app>).

**Personal accounts:** supported. The README says to install the app "on your repositories or entire organization" (<https://github.com/repository-settings/app>), and GitHub documents that "Anyone can install GitHub Apps on their personal account" (<https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party>). The branch-protection plugin explicitly distinguishes personal repositories: dismissal restrictions and push restrictions with users/teams are "only available for organization-owned repositories" (<https://github.com/repository-settings/app/blob/master/docs/plugins/branches.md>).

**Supported settings relevant here:**

| Area | Support | Source |
|---|---|---|
| Repository metadata, visibility, features, default branch | Yes | <https://github.com/repository-settings/app/blob/master/docs/plugins/repository.md> |
| Merge methods and branch deletion (`allow_squash_merge`, `allow_merge_commit`, `allow_rebase_merge`, `delete_branch_on_merge`) | Yes | <https://github.com/repository-settings/app/blob/master/docs/plugins/repository.md> |
| Vulnerability alerts and automated security fixes | Yes | <https://github.com/repository-settings/app/blob/master/docs/plugins/repository.md> |
| Labels | Yes | <https://github.com/repository-settings/app/blob/master/docs/plugins/labels.md> |
| Branch protection | Yes | <https://github.com/repository-settings/app/blob/master/docs/plugins/branches.md> |
| Rulesets | Yes, but explicitly beta | <https://github.com/repository-settings/app/blob/master/docs/plugins/rulesets.md> |

The rulesets plugin carries a warning: "Support for Repository Rulesets is still under development. Details may still change ... adopt cautiously, with the expectation of breaking changes until support is fully released" (<https://github.com/repository-settings/app/blob/master/docs/plugins/rulesets.md>). The YAML shape mirrors the REST ruleset object, including `required_status_checks` and `bypass_actors` (<https://github.com/repository-settings/app/blob/master/docs/plugins/rulesets.md>).

**Merge settings caveat:** `allow_auto_merge` is not in the documented repository plugin key list. The plugin nevertheless forwards its settings object to `PATCH /repos/{owner}/{repo}` (<https://github.com/repository-settings/app/blob/master/lib/plugins/repository.js>), and that endpoint accepts `allow_auto_merge` (<https://docs.github.com/en/rest/repos/repos#update-a-repository>), so the key is likely accepted even though it is undocumented. `[INFERENCE]`

**Limits and risks:**

- The app "inherently escalates anyone with `push` permissions to the `admin` role", because they can push settings to the default branch (<https://github.com/repository-settings/app>).
- The app is driven by changes to `.github/settings.yml` on the default branch (typically a push), not by a one-time API bootstrap (<https://github.com/repository-settings/app/blob/master/docs/configuration.md>).
- Inheritance from another repository is supported (for arrays keyed by `name`), which lets a personal account keep a base settings repository and override per repo (<https://github.com/repository-settings/app/blob/master/docs/configuration.md>).

### 1.2 safe-settings

**Status: active, organization-only.** Latest release `3.0.0` (2026-10-05); the repository moved to `github-community-projects` and was last pushed 2026-10-23 (<https://github.com/github-community-projects/safe-settings/releases>, <https://github.com/github-community-projects/safe-settings>).

It is explicitly scoped to organizations: "Policy-as-Code for GitHub Organizations"; "all the settings are stored centrally in an `admin` repo within the organization"; "Install the Safe-Settings GitHub App in your organization" (<https://github.com/github-community-projects/safe-settings>). No personal-account mode is documented. It can manage organization-level rulesets (the only organization-targeted setting currently supported) and repo-level settings across the org (<https://github.com/github-community-projects/safe-settings>). Organization rulesets themselves require GitHub Team or Enterprise (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets>).

**Conclusion:** not usable for a personal account. `[INFERENCE]` from the documented org-only deployment model.

### 1.3 Terraform `integrations/github` provider

**Status: active.** Latest release `v6.13.0` (2026-07-08); default branch last pushed 2026-10-23; partner-tier provider with 399M downloads (<https://github.com/integrations/terraform-provider-github/releases>, <https://registry.terraform.io/providers/integrations/github/latest/docs>).

**Personal accounts:** supported. The provider's `owner` argument is documented as "GitHub organization or user account to manage", and the example uses `owner = "octocat"` (<https://github.com/integrations/terraform-provider-github/blob/main/docs/index.md>). Authentication can be a PAT/OAuth token, GitHub App installation, or anonymous read-only (<https://github.com/integrations/terraform-provider-github/blob/main/docs/index.md>).

**What it covers for this use case:**

- `github_repository` exposes `allow_auto_merge`, `allow_squash_merge`, `allow_merge_commit`, `allow_rebase_merge`, and `delete_branch_on_merge` (<https://github.com/integrations/terraform-provider-github/blob/main/docs/resources/repository.md>). Unlike the Probot app, auto-merge is a first-class, documented argument.
- `github_repository_ruleset` creates repository-level rulesets with `required_status_checks`, `bypass_actors`, and branch/tag/push targets (<https://github.com/integrations/terraform-provider-github/blob/main/docs/resources/repository_ruleset.md>).
- Organization-only features are explicitly constrained. For rulesets, `enforcement = "evaluate"` is "currently only supported for owners of type `organization`", and branch/commit-message/tag-name patterns "cannot be applied to repositories owned by individuals or regular organizations" (<https://github.com/integrations/terraform-provider-github/blob/main/docs/resources/repository_ruleset.md>).

**Limits:** it is imperative infrastructure-as-code, not event-driven: every repository needs a resource block, and state must be stored somewhere (local state is free; a remote backend is additional setup). It does not react to a newly created repository unless a CI job or a human runs `terraform apply`.

### 1.4 Rulesets as JSON, and user-level rulesets

**Import/export is GA.** GitHub announced ruleset history, import, and export as generally available on 2025-02-13 (<https://github.blog/changelog/2025-02-13-repositories-ruleset-history-import-and-export-are-generally-available/>). The repository UI imports a ruleset with **Settings → Rules → Rulesets → New ruleset → Import a ruleset**, selecting an exported JSON file (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository>). The REST API exposes the same objects: list/get/create/update repository rulesets under `/repos/{owner}/{repo}/rulesets` (<https://docs.github.com/en/rest/repos/rules>).

**No user-level rulesets.** GitHub documents rulesets at repository and organization level only; organization-wide rulesets are for Team and Enterprise (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets>). The REST API has `/repos/{owner}/{repo}/rulesets` and `/orgs/{org}/rulesets`, with no `/users/{user}/rulesets` collection (<https://docs.github.com/en/rest/repos/rules>, <https://docs.github.com/en/rest/orgs/rules>). Observation: `gh api /users/ghdtmdwns133/rulesets` returned HTTP 404 on 2026-10-24. For a personal account this means one ruleset per repository; JSON export/import is the only native way to copy the same policy.

**Plan gate:** rulesets are available in public repositories on GitHub Free, and in public and private repositories on GitHub Pro, Team, and Enterprise Cloud (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets>). Organization-wide rulesets require Team or Enterprise (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets>). The account's GitHub Pro plan therefore covers private-repository rulesets, but not cross-repository rulesets.

### 1.5 Maintenance summary

| Option | Latest activity | Personal account | Rulesets | Labels / merge settings | Main caveat |
|---|---|---|---|---|---|
| Probot Settings app | v5.0.14, 2026-08-29; pushed 2026-10-22 | Yes | Beta plugin | Yes (merge methods documented; `allow_auto_merge` only via PATCH) | Per-repo `settings.yml`; push-to-admin escalation |
| safe-settings | v3.0.0, 2026-10-05; pushed 2026-10-23 | No (org only) | Org-level and repo-level | Yes for org repos | Requires an organization and an `admin` repo |
| Terraform provider | v6.13.0, 2026-07-08; pushed 2026-10-23 | Yes | Repo-level; `evaluate` org-only | Yes, including `allow_auto_merge` | State management; per-repo resource blocks |

## 2. Sharing secrets across many personal-account repositories

### 2.1 Native GitHub: no account-level Actions secrets

GitHub Actions secrets exist at three scopes only: repository, environment, and organization (<https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets>). The REST API mirrors this: `/repos/{owner}/{repo}/actions/secrets`, `/repositories/{id}/environments/{env}/secrets`, and `/orgs/{org}/actions/secrets` (<https://docs.github.com/en/rest/actions/secrets>). There is no `/users/{user}/actions/secrets` collection. Observation: `gh api /user/actions/secrets` returned HTTP 404 on 2026-10-24. **There is no account-level Actions secret store for a personal account.** `[INFERENCE]` strongly supported by the documented scopes and the 404.

**Organization secrets on a free organization do not solve private repositories.** Organization owners can create secrets with an access policy of all/private/selected repositories (<https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets>), but GitHub states: "Organization-level secrets and variables are not accessible by private repositories for GitHub Free" (<https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets>). A free organization therefore only shares secrets with public repositories; private repositories require a paid organization plan (Team or above) for organization secrets.

Plan quotas for context: GitHub Free includes 2,000 Actions minutes/month and 500 MB artifact storage; GitHub Pro includes 3,000 minutes/month and 1 GB artifact storage; public repositories on standard runners are free (<https://docs.github.com/en/billing/concepts/product-billing/github-actions>).

### 2.2 Doppler GitHub Actions sync

Doppler's GitHub integration supports Actions, Codespaces, Dependabot, and Copilot Agents. For a **non-organization (personal) account**, the sync target is a single repository selected from a dropdown; organization accounts additionally get an Organization target with private/all repository scope (<https://docs.doppler.com/docs/github-actions>).

- **Setup effort:** authorize the Doppler GitHub App once (choose the account and repositories), then create one sync per repository: feature = Actions, repository, config. Each sync immediately writes all secrets in the chosen config plus three `DOPPLER_*` secrets (<https://docs.doppler.com/docs/github-actions>).
- **Ongoing sync:** "every time you add, update or remove a secret in Doppler, that change will be instantly reflected in the GitHub secrets for the chosen feature and repository" (<https://docs.doppler.com/docs/github-actions>).
- **New repositories:** a sync is bound to one repository. The docs describe no automatic creation of a sync for a repository added later; a new repository requires a new sync. `[INFERENCE]` from the per-repository sync model.
- **One-way:** Doppler cannot import existing GitHub secrets or sync changes made in GitHub, because GitHub does not expose secret values (<https://docs.doppler.com/docs/github-actions>).

On a personal account Doppler therefore reduces the number of places to edit (one source of truth) but does not eliminate the per-repository sync step.

### 2.3 1Password

1Password does not sync values into GitHub Secrets. Its `load-secrets-action` authenticates with a service account (or Connect server) and loads `op://vault/item/field` references into the job at runtime (<https://developer.1password.com/docs/ci-cd/github-actions>). The service-account token must be stored as a GitHub secret (`OP_SERVICE_ACCOUNT_TOKEN`), per repository unless an organization secret is available (<https://developer.1password.com/docs/ci-cd/github-actions>).

- **Per-repo cost:** one stored token per repository on a personal account, plus the action steps in each workflow. The actual values never enter GitHub.
- **Cost:** 1Password has no free plan; individual pricing starts at $3.99/month with a 14-day trial (<https://1password.com/pricing/personal>). This conflicts with the "no paid resources" constraint unless a student promotion is used; the pricing page only links a student discount, not a free plan (<https://1password.com/pricing/personal>).
- **Verdict:** technically sound, but it is not zero-per-repo and is not free.

### 2.4 Infisical

Infisical offers two relevant delivery modes:

- **Runtime injection with OIDC (recommended by Infisical):** `Infisical/secrets-action` authenticates with a GitHub OIDC token, so "no Infisical credentials are stored in GitHub" (<https://infisical.com/docs/integrations/cicd/githubactions>). This is the only option surveyed that can avoid a stored secret in every repository. The trust relationship is still configured per repository (or with a glob subject) in the machine identity.
- **GitHub Secret Sync:** writes secrets into GitHub organization, repository, or repository-environment scope, with auto-sync on change (<https://infisical.com/docs/integrations/secret-syncs/github>). On a personal account only the repository scope applies; organization scope requires an organization. Syncs can be created through the UI or the API (<https://infisical.com/docs/integrations/secret-syncs/github>).

Infisical's free plan includes 5 identities, unlimited projects, 3 environments, and 10 secret syncs (<https://infisical.com/pricing>). For a solo developer with four repositories, the free tier is sufficient for either OIDC or per-repo sync.

### 2.5 Comparison

| Mechanism | Shared value store | Personal account | Per-repo work | Free |
|---|---|---|---|---|
| GitHub organization secrets | Yes | No (requires an org; Free org cannot expose them to private repos) | None after setup, but only in an org | Free org: public repos only |
| Doppler | Yes | Yes, per-repo sync | One sync per repo | `UNVERIFIED` (student Team plan assumed in the project plan) |
| 1Password | Yes | Yes, runtime load | One service-account token per repo | No (paid plan) |
| Infisical OIDC | Yes | Yes | Identity/trust config per repo, no stored secret | Yes, within free limits |
| Infisical GitHub sync | Yes | Yes, repository scope | One sync per repo | Yes, within 10 syncs |

## 3. Zero-per-repo service onboarding

### 3.1 Codecov

**What the GitHub App does:** installing the Codecov GitHub App determines "what repositories that Codecov will have the ability to communicate with and show coverage metrics within the Codecov UI"; the install screen offers "All Repositories" or "Only Select Repositories" (<https://docs.codecov.com/docs/github-2-getting-a-codecov-account-and-uploading-coverage>). A repository that has never been used with Codecov shows its upload token on the onboarding page (<https://docs.codecov.com/docs/github-2-getting-a-codecov-account-and-uploading-coverage>).

**What remains per repository:** an upload token for private repositories. "For private repositories, all uploads require a token" (<https://docs.codecov.com/docs/codecov-tokens>). Public repositories can be tokenless when the repository owner has disabled token authentication for public repositories, or when the upload is for an unprotected branch such as a fork PR; new organizations start with token authentication "Not required", while existing organizations default to "Required" (<https://docs.codecov.com/docs/codecov-tokens>).

**Global upload token:** "Account owners or organization administrators can create a single global upload token which will work for all of the repositories owned by the account or organization" (<https://docs.codecov.com/docs/codecov-tokens>). This removes the need to manage different values per repository, but on a personal account the token still has to be stored in each repository's Actions secrets, because GitHub has no account-level Actions secrets (section 2.1). The docs do not state which plans can generate a global token; plan availability is `UNVERIFIED`.

**Plan facts (Developer/free):** the pricing page lists a Developer tier with 250 private-repo uploads per month and unlimited public-repo uploads (<https://about.codecov.io/pricing/>). Whether carryforward flags are available on the free/student private tier is not stated unambiguously on that page; `UNVERIFIED`.

**Net:** app installation is account-wide, but private repositories still need one secret each (even if it is the same global token). Only public repositories can avoid a per-repo credential, and only when token authentication is disabled; even then a first upload is needed to create the project.

### 3.2 CodeScene

**No automatic project creation is documented.** The cloud getting-started flow says: after login, "Click *Create New Project* ... CodeScene fetches a list of all your repositories ... and lets you specify the projects to analyse" (<https://www.codescene.io/docs/getting-started/index.html>). The GitHub App (`CodeScene Access`) handles authentication and repository-level access for pull-request analysis and checks; "Access is granted per repository" (<https://helpcenter.codescene.com/articles/9262058-codescene-access-vs-codescene-delta-analysis-which-github-app-do>).

**REST API:** `POST /api/v2/projects/new` creates a project from just `repo-paths`; the project name defaults to the repository name (<https://helpcenter.codescene.com/en/articles/0187814-automating-project-creation-for-frictionless-team-onboarding>). The same article states: "Access to the REST-API is only available to customers with a Pro Subscription, not Standard" (<https://helpcenter.codescene.com/en/articles/0187814-automating-project-creation-for-frictionless-team-onboarding>). CodeScene must already be able to clone the repository; creating the project does not grant repository access (<https://helpcenter.codescene.com/en/articles/0187814-automating-project-creation-for-frictionless-team-onboarding>).

**Student plan:** a free student account exists through the GitHub Student Developer Pack (<https://codescene.com/resources/github-students>). CodeScene's public docs say the free plan analyses open-source projects and paid plans are needed for private repositories (<https://www.codescene.io/docs/getting-started/index.html>). Whether the student account includes private-repository analysis and REST API access is not stated on the student page; `UNVERIFIED`.

**Net:** no zero-per-repo path is documented. Either create each project in the UI or script the Pro API; repository access is still granted per repository through the GitHub App.

### 3.3 Sentry

Sentry creates projects only through an explicit API call or UI action; no automatic per-repository project creation is documented. The endpoint is `POST /api/0/teams/{organization_id_or_slug}/{team_id_or_slug}/projects/`, with `name` required and `slug`, `platform`, and `default_rules` optional; the token needs `project:admin` or `project:write` (<https://docs.sentry.io/api/projects/create-a-new-project/>). A project is bound to a team, so the automation needs the team slug as well as the org slug (<https://docs.sentry.io/api/projects/create-a-new-project/>).

Sentry also exposes "Link a Repository to a Project" as a separate API operation (<https://docs.sentry.io/api/projects/>), so repository linking is a second per-project step if the GitHub integration is used.

**Student plan:** the Sentry Education plan is free for one year and includes 50K errors, 5 GB logs, 5M spans, 500 replays, and one cron monitor per month (<https://sentry.io/for/education/>).

**Net:** project creation is automatable with one API call per project; no automatic creation on GitHub App installation is documented.

## 4. Renovate via the hosted Mend app

### 4.1 Existing `renovate.json` and the onboarding PR

Renovate treats a repository as onboarded if a recognized config file exists. The check walks the configured file names and returns true on the first match; `package.json` with a `renovate` key also counts (<https://github.com/renovatebot/renovate/blob/main/lib/workers/repository/onboarding/branch/check.ts>). The onboarding PR is only produced when the repository is not onboarded (<https://github.com/renovatebot/renovate/blob/main/lib/workers/repository/onboarding/branch/index.ts>).

Therefore: **a repository that already contains `renovate.json` (on the default branch) skips the onboarding PR and starts raising update PRs.** The docs describe committing a config file as the manual alternative to the onboarding PR (<https://docs.renovatebot.com/getting-started/installing-onboarding/>). The config must be on the default branch; Renovate always reads config from the default branch (<https://docs.renovatebot.com/configuration-options/>).

### 4.2 Shared presets with `github>owner/repo`

`github>owner/name` resolves to `default.json` on the default branch of that repository; named presets use `github>owner/name:preset`, paths use `//path`, and a tag can pin the preset (`github>owner/name#1.2.3`) (<https://docs.renovatebot.com/config-presets/>). Presets must be JSON, JSONC, or JSON5 (<https://docs.renovatebot.com/config-presets/>). The docs recommend renaming a shared `renovate.json` to `default.json` because using `renovate.json` as the preset filename is deprecated (<https://docs.renovatebot.com/config-presets/>).

This gives one shared policy repository, e.g. `"extends": ["github>ghdtmdwns133/renovate-config"]`, with per-repo overrides.

### 4.3 Automerge, including platform automerge

- `automerge: true` lets Renovate merge PRs itself; it is normally scoped with `packageRules` (for example minor/patch only) (<https://docs.renovatebot.com/configuration-options/#automerge>).
- `platformAutomerge` defaults to `true` on GitHub and uses GitHub's native auto-merge; it falls back to Renovate-based automerge if native automerge is unavailable (<https://docs.renovatebot.com/configuration-options/#platformautomerge>).
- GitHub's repository setting **Allow auto-merge** must be enabled; it is managed per repository (<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-auto-merge-for-pull-requests-in-your-repository>). The setting is exposed by Terraform (`allow_auto_merge`) but not documented by the Probot Settings app (section 1.1).
- Renovate warns that if `automerge=true`, `platformAutomerge=true`, and branch protection uses "Require status checks to pass before merging", at least one status check must be selected; otherwise "GitHub might automerge PRs with failing tests" (<https://docs.renovatebot.com/configuration-options/#automerge>).

GitHub's auto-merge availability is plan-gated: "Auto-merge for pull requests is available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, GitHub Enterprise Cloud, and GitHub Enterprise Server" (<https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/automatically-merging-a-pull-request>). The account's GitHub Pro plan therefore covers private-repository auto-merge; access is additionally controlled by write permission and the per-repository setting. Private-repository rulesets, which provide the required checks, also need GitHub Pro or above (section 1.4).

### 4.4 Manager breadth

Renovate's manager index lists managers across ecosystems, including npm/bun/deno, pip/poetry/pipenv/pep621, NuGet/cake/Unity3D, GitHub Actions, GitLab CI, Docker/Compose/devcontainer, Terraform/Terragrunt, Gradle/Maven, Cargo, Bundler, Composer, Go modules, Helm/Kustomize, and custom regex/JSONata managers (<https://docs.renovatebot.com/modules/manager/>). This covers the stacks in this project: Unity packages via `unity3d`, NuGet, npm, and pip (<https://docs.renovatebot.com/modules/manager/>).

### 4.5 Hosted app: cost and new repositories

- The Mend Renovate App's GitHub Marketplace plan "Renovate Community Cloud" is **$0** and explicitly covers "Personal and org accounts" and "Public and private repos" (<https://github.com/marketplace/renovate>).
- Renovate can be installed "into a user or organization account" with either "All repositories" or "Select repositories" (<https://docs.renovatebot.com/getting-started/installing-onboarding/>). With autodiscover, Renovate "will run on every repository which it's been granted access to" (<https://docs.renovatebot.com/getting-started/installing-onboarding/>).
- GitHub documents "All repositories" as granting access to all of the account's repositories, and notes that repositories the app itself creates are automatically included (<https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps>). The docs do not explicitly state whether repositories created later by the user are included in an "All repositories" installation; `UNVERIFIED`. Renovate's documented behavior is that it processes every repository it has been granted access to, and creates an onboarding PR for each repository that is not yet onboarded (<https://docs.renovatebot.com/getting-started/installing-onboarding/>). `[INFERENCE]`: with "All repositories", new repos are picked up on the next run and either skipped (config present) or onboarded; with "Select repositories", they must be added manually.

## Implications

- On a personal account, neither settings nor secrets can be defined once for all repositories: rulesets and Actions secrets are repository-scoped, and organization-level secret sharing for private repositories needs an organization on Team or above (a free organization cannot expose secrets to private repositories).
- Among the options surveyed, the only settings-as-code tools that work on a personal account are the Probot Settings app (per-repo YAML, inheritance from a base repo, rulesets still beta) and Terraform (full API coverage including `allow_auto_merge`, at the cost of state and per-repo resource blocks); safe-settings is organization-only.
- Renovate Community Cloud is free for personal accounts and private repositories; a committed `renovate.json` skips the onboarding PR, and a `github>owner/repo` preset gives one shared policy. Platform automerge still requires GitHub Pro (held) for private repos, the per-repo "Allow auto-merge" setting, and at least one required status check.
- Native secret sharing is unavailable, so the realistic choices are an external manager with per-repo sync (Doppler), a paid runtime loader with a per-repo token (1Password), or Infisical's free OIDC path, which is the only surveyed option that avoids storing a credential in every repository.
- Codecov, CodeScene, and Sentry do not fully self-onboard: Codecov's app sees all repositories but private uploads still need a token, CodeScene project creation is manual or Pro-API, and Sentry project creation is an explicit API call; zero-touch onboarding will require a small bootstrap script.

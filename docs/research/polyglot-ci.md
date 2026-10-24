# Polyglot CI for a solo developer on a personal GitHub Pro account

Research date: **2026-10-24**. All facts below were read from primary sources on that date; versions,
prices and image sizes drift, so re-check before pinning.

Legend: `[measured]` = observed directly (GitHub API, container registry manifest, Docker Hub API).
`[INFERENCE]` = my reasoning from the cited facts, not stated by the source. `UNVERIFIED` = could not
be confirmed from a primary source.

## 1. Polyglot lint/security aggregators: MegaLinter, Super-Linter, Trunk Check

### 1.1 Coverage and how projects are "detected"

None of the three does project-level language detection and then installs only what the project
needs. The two open-source aggregators **enable every linter by default** and let each linter select
files by its own type/extension rules; you narrow the set by hand.

- MegaLinter: "MegaLinter has all linters enabled by default"; narrowing happens with `ENABLE`,
  `ENABLE_LINTERS`, `DISABLE`, `DISABLE_LINTERS` (`https://megalinter.io/latest/config-activation/`).
  Coverage is stated as 67 languages, 23 formats, 22 tooling formats
  (`https://megalinter.io/latest/`); the `all` flavor bundles 133 linters and the `python` flavor 69
  (`https://megalinter.io/latest/flavors/`). Each descriptor page lists the files a linter touches,
  e.g. the `REPOSITORY` descriptor (`https://megalinter.io/latest/descriptors/repository/`). There is
  no documented mode that reads the repo and enables a matching subset; the docs only say a log
  message suggests a flavor when one would cover the project
  (`https://megalinter.io/latest/flavors/`).
- Super-Linter: every `VALIDATE_<LANGUAGE>` flag defaults to `true`, so all linters run unless you
  opt out (`https://github.com/super-linter/super-linter`). File selection is via git diff
  (`VALIDATE_ALL_CODEBASE`, `USE_FIND_ALGORITHM`), not language detection
  (`https://github.com/super-linter/super-linter`). The README's language table is the coverage list:
  ~40 languages plus JSON/YAML/Markdown/Dockerfile/Terraform/Kubernetes/OpenAPI/SBOM/secret checks
  (`https://github.com/super-linter/super-linter`).
- Trunk Code Quality: also a metalinter, but it **installs tools hermetically on demand** and runs
  them per file type; it does not ship one image with everything
  (`https://docs.trunk.io/code-quality/overview`). Its plugin catalog is the coverage list — 105
  linter pages were listed in the docs index on 2026-10-24 (`https://docs.trunk.io/llms.txt`), and
  the docs describe "hold-the-line" (only changed lines) as the default execution mode
  (`https://docs.trunk.io/code-quality/overview`).
- `[INFERENCE]` For a four-ecosystem repo set, the practical difference is not coverage but *which
  version* of each linter runs and whether the aggregator's defaults match the per-ecosystem configs
  (`ruff`, `eslint`, `dotnet format`, Unity) that already exist.

### 1.2 Bundled security tools

- MegaLinter `REPOSITORY` descriptor lists: checkov, devskim, dustilock, `git_diff`, betterleaks,
  grype, ls-lint, osv-scanner, secretlint, semgrep, syft (SBOM), trivy, trivy-sbom, trufflehog,
  kingfisher (`https://megalinter.io/latest/descriptors/repository/`). **gitleaks is not in that
  list** (secret detection there is secretlint / betterleaks / trufflehog).
- Super-Linter ships Trivy (vulnerabilities, licenses, SBOM, config scanning), Checkov (IaC) and
  GitLeaks (secrets) (`https://github.com/super-linter/super-linter`).
- Trunk documents supported tools including gitleaks, trivy, checkov, semgrep, trufflehog,
  OSV-Scanner, bandit, tfsec, terrascan, hadolint
  (`https://docs.trunk.io/code-quality/overview/linters/supported`).
- `[INFERENCE]` All three therefore duplicate, rather than replace, a hand-picked
  trivy + gitleaks + zizmor/actionlint pipeline; the extra value is the long tail (bandit, checkov,
  osv-scanner, devskim, dustilock).

### 1.3 Runtime and image size

- MegaLinter runs as a Docker image; the documented local runner is `npx mega-linter-runner`, which
  drives Docker (`https://megalinter.io/latest/install-locally/`,
  `https://github.com/oxsecurity/megalinter/blob/main/.pre-commit-hooks.yaml`).
  Sizes `[measured]` from the GHCR manifest layers on 2026-10-24 (compressed, amd64):
  `ghcr.io/oxsecurity/megalinter:v10.1.0` **4,029 MB**; `ghcr.io/oxsecurity/megalinter-python:v10.1.0`
  **1,337 MB** (`https://github.com/oxsecurity/megalinter/pkgs/container/megalinter`,
  `https://github.com/oxsecurity/megalinter/pkgs/container/megalinter-python`). Docker Hub is stale:
  `oxsecurity/megalinter` still resolves `latest` to **v9.4.0, 4,722 MB**, and no 10.x tag was listed
  there `[measured]` (`https://hub.docker.com/r/oxsecurity/megalinter`).
- Super-Linter runs as a Docker/OCI container action; GitHub Actions usage is
  `super-linter/super-linter@v9.0.0` (`https://github.com/super-linter/super-linter`). Sizes
  `[measured]` from the GHCR manifest layers on 2026-10-24 (compressed, amd64): `latest`
  **1,738 MB**, `slim-latest` **1,226 MB** (`https://github.com/super-linter/super-linter/pkgs/container/super-linter`).
  `slim` drops Rustfmt, Clippy, arm-ttk, PSScriptAnalyzer and all `dotnet` commands
  (`https://github.com/super-linter/super-linter`), which matters for a .NET stack.
- Trunk Check is "a C++ CLI" plus a background daemon that downloads tools and their runtimes into
  `~/.cache/trunk` (`https://docs.trunk.io/code-quality/overview`), so there is no fixed image size;
  there is a documented `trunk check download`/`trunk install` pre-seeding step for CI images
  (`https://docs.trunk.io/code-quality/overview/prevent-new-issues`).

### 1.4 Private repositories, licensing, cost

- MegaLinter: "**100% open source** and **free for all uses** (personal, professional, public, and
  private repositories)" (`https://megalinter.io/latest/`). The license is **AGPL-3.0**, not MIT
  (`https://github.com/oxsecurity/megalinter/blob/main/LICENSE`, repo metadata `AGPL-3.0`).
  `[INFERENCE]` Running it in CI is unaffected; the AGPL obligation attaches if you modify and
  distribute it (e.g. publish a custom flavor image).
- Super-Linter: MIT, "maintained by a team of independent developers" (`https://github.com/super-linter/super-linter`).
  No private-repo restriction; it simply consumes Actions minutes.
- Trunk Code Quality: the CLI is **closed source**; the plugin repo and the GitHub Action are MIT
  (`https://docs.trunk.io/code-quality/overview/licensing`). Free usage: unlimited for public repos,
  and private repos with **up to 5 active non-bot committers** (30-day window); above that a paid
  license is required (`https://docs.trunk.io/code-quality/overview/licensing`). The Free plan lists
  Code Quality as "Unlimited usage" (`https://docs.trunk.io/setup-and-administration/billing`).
  Trunk measures seats through its GitHub App (`https://docs.trunk.io/setup-and-administration/billing`).
  For a single developer this is $0, but it is not open source.

### 1.5 Maintenance status (2026-10-24)

| Tool | Latest release | Repo last push | Notes |
|---|---|---|---|
| MegaLinter | v10.1.0, 2026-09-05 (`https://github.com/oxsecurity/megalinter/releases/tag/v10.1.0`) | 2026-10-23 `[measured]` | 2,622 stars, 43 open issues `[measured]` |
| Super-Linter | v9.0.0, 2026-10-01 (`https://github.com/super-linter/super-linter/releases/tag/v9.0.0`) | 2026-10-23 `[measured]` | 10,636 stars `[measured]`; immutable full-version releases, short tags are not immutable (`https://github.com/super-linter/super-linter`) |
| Trunk Check | CLI version is pinned per repo in `.trunk/trunk.yaml` (`https://docs.trunk.io/code-quality/overview/prevent-new-issues`) | plugins repo 2026-10-23 `[measured]` | CLI itself is closed source; no public changelog location was verifiable — `UNVERIFIED` |

### 1.6 Local run and pre-commit

- MegaLinter: local via `mega-linter-runner` (`https://megalinter.io/latest/install-locally/`). It
  **ships an official pre-commit hook manifest** with `megalinter-incremental` and
  `megalinter-full`; both require `npx` and Docker and the manifest itself warns it "runs very
  slowly when the pertinent Docker image isn't already cached"
  (`https://github.com/oxsecurity/megalinter/blob/main/.pre-commit-hooks.yaml`).
- Super-Linter: local via `docker run -e RUN_LOCAL=true -v "$PWD":/tmp/lint ghcr.io/super-linter/super-linter:<tag>`
  (`https://github.com/super-linter/super-linter/blob/main/docs/run-linter-locally.md`). There is
  **no `.pre-commit-hooks.yaml`** in the repo (request returns 404) `[measured]`; it *validates* a
  `.pre-commit-config.yaml` as one of its linters, which is not the same thing
  (`https://github.com/super-linter/super-linter`).
- Trunk: local CLI, and it manages git hooks natively — `trunk git-hooks sync`, with actions
  triggered by `pre-commit`/`pre-push`/etc. defined in `trunk.yaml`
  (`https://docs.trunk.io/code-quality/overview/getting-started/actions/git-hooks`). It is *not*
  runnable as a `pre-commit` framework hook; it replaces that role.
- Windows: Trunk documents a supported Windows setup (git-bash/msys2 or PowerShell launcher, CLI
  ≥ 1.13.0, VC++ runtime required) (`https://docs.trunk.io/code-quality/overview/getting-started/install`).
  MegaLinter and Super-Linter are documented only through a container runtime, so on this Windows
  workstation they need Docker Desktop; neither doc states Windows support or the absence of it —
  `UNVERIFIED` beyond "requires Docker".

## 2. Toolchain and task managers: mise, asdf, devbox, devcontainers, just, Taskfile

### 2.1 One file to pin every ecosystem?

- **mise** — yes, in practice. One `mise.toml` `[tools]` table takes short names from a registry or
  explicit backend identifiers: `core` (node, python, …), `aqua`, `github`/`gitlab`/`forgejo`,
  `http`/`s3`, `cargo`, `go`, `npm`, `pypi`/`pipx`, `gem`, `dotnet` (NuGet tools), `conda`, `vfox`,
  and legacy `asdf` plugins (`https://mise.jdx.dev/dev-tools/backends/`). Reproducibility comes from
  `mise.lock`, which records resolved versions, URLs and checksums
  (`https://mise.jdx.dev/dev-tools/versions.html`). Caveat from the same page: language package
  backends install *CLI tools*, "they do not manage your project's dependencies".
- **asdf** — one `.tool-versions`, but coverage depends on installing a plugin per tool; mise reads
  the same file (`https://asdf-vm.com/manage/configuration.html`,
  `https://mise.jdx.dev/dev-tools/versions.html`). asdf itself expects exact versions: mise's docs
  advise keeping prefixes (`3`, `latest`, `prefix:`), `sub-` requests and most aliases out of a
  `.tool-versions` that asdf users also read
  (`https://mise.jdx.dev/dev-tools/versions.html`).
- **devbox** — one `devbox.json` plus `devbox.lock`, resolving packages from Nixpkgs
  (`https://www.jetify.com/docs/devbox/guides/pinning-packages`,
  `https://www.jetify.com/docs/devbox`). Package versions are Nixpkgs versions, and the docs warn
  that older versions can be hard to obtain because Nixpkgs drops them
  (`https://www.jetify.com/docs/devbox/guides/pinning-packages`).
- **devcontainers** — `devcontainer.json` plus Features/image labels; the spec defines metadata, not
  a lockfile (`https://containers.dev/overview`,
  `https://containers.dev/implementors/json_reference`). Pinning is whatever you pin in the image
  tag and feature versions.
- **just** and **Task** pin nothing: both are command runners. `just` describes itself as "a command
  runner, not a build system" (`https://just.systems/man/en/`); Task is "a fast, cross-platform build
  tool" whose Taskfile declares commands, deps and sources (`https://taskfile.dev/`).

### 2.2 Does mise read native version files?

Yes — but **not by default**. `idiomatic_version_file_enable_tools` defaults to `[]`, and you opt in
per tool, e.g. `mise settings add idiomatic_version_file_enable_tools node`
(`https://mise.jdx.dev/configuration/settings.html#idiomatic_version_file_enable_tools`). The
documented file table includes (`https://mise.jdx.dev/dev-tools/versions.html`):

| Tool | Native files read |
|---|---|
| node | `.nvmrc`, `.node-version`, `package.json` |
| python | `.python-version`, `.python-versions` |
| rust | `rust-toolchain.toml` |
| dotnet | `global.json` |
| go | `.go-version`, `go.mod`, `go.work` |
| ruby | `.ruby-version`, `Gemfile` |
| bun / deno / java / terraform / zig / … | `.bun-version`, `.deno-version`, `.java-version`/`.sdkmanrc`, `.terraform-version`, `.zig-version` |

Two documented caveats: minimum-version fields are ignored (e.g. `package.json` `engines` is not a
version request), and the Go/CMake floor readings are being removed in mise 2026.11.0
(`https://mise.jdx.dev/dev-tools/versions.html`). The docs also suggest *disabling* `.python-version`
when uv owns it (`https://mise.jdx.dev/dev-tools/versions.html`).

### 2.3 mise tasks vs just

- mise tasks: TOML tasks in `mise.toml` or executable files in `mise-tasks/`; `depends` runs tasks
  in parallel and `wait_for`/`depends_post`/run-steps express ordering; task arguments with
  validation/`--help`/completions; task templates; per-task caching; monorepo task support
  (`https://mise.jdx.dev/tasks/`). `mise run` also **installs missing tools first** and runs with the
  project's env (`https://mise.jdx.dev/tasks/`).
- just: recipes with dependencies, parameters and `.env` loading; arbitrary shebang recipes; modules
  and imports for multi-file justfiles (`https://just.systems/man/en/`). It does not install or pin
  tools, and no caching feature is documented in the manual's feature list
  (`https://just.systems/man/en/`).
- `[INFERENCE]` mise tasks subsume just's role for this use case *if* mise already pins the
  toolchains; just remains the lighter, dependency-free choice when tools are managed elsewhere.

### 2.4 GitHub Action support and Windows

| Tool | Action | Windows |
|---|---|---|
| mise | `jdx/mise-action@v4`/`v5`: installs mise, runs `mise install`, caches `~/.local/share/mise` (`%LOCALAPPDATA%\mise` on Windows), exports env/PATH, supports `mise_toml`/`tool_versions` inputs (`https://github.com/jdx/mise-action`) | Native: `winget install jdx.mise` (`https://github.com/jdx/mise`); "mise never uses the asdf backend on Windows" (`https://mise.jdx.dev/dev-tools/backends/`) |
| asdf | action exists but was not verified here — `UNVERIFIED` | **No Windows binaries**: v0.20.2 release assets are darwin-amd64/arm64 and linux-386/amd64/arm64 only `[measured]` (`https://github.com/asdf-vm/asdf/releases/tag/v0.20.2`); install docs list only linux/macOS package managers and bash/zsh/fish/elvish (`https://asdf-vm.com/guide/getting-started.html`) |
| devbox | `devbox-install-action` documented in the Devbox CI guide (`https://www.jetify.com/docs/devbox/continuous-integration/github-action`) | Only via **WSL2** (`https://www.jetify.com/docs/devbox/installing-devbox`) |
| devcontainers | `devcontainers/ci` action available (`https://containers.dev/overview`) | Requires a container runtime; Windows-specific behavior not documented on containers.dev — `UNVERIFIED` |
| just | no official action verified — `UNVERIFIED` | Supported: "Linux, macOS, Windows … supported with no additional dependencies" (`https://just.systems/man/en/`) |
| Task | `go-task/setup-task` commonly used but not verified here — `UNVERIFIED` | Supported; winget/Scoop install listed (`https://taskfile.dev/`) |

## 3. Hook managers: pre-commit and lefthook

### 3.1 Polyglot hook coverage

- pre-commit is "a multi-language package manager for pre-commit hooks": it installs each hook's
  language environment itself, so a Python project can run a Ruby or Node linter. Documented
  languages: conda, coursier, dart, docker, docker_image, dotnet, fail, golang, haskell, julia, lua,
  node, perl, python, r, ruby, rust, swift, pygrep, unsupported (`https://pre-commit.com/#supported-languages`).
  It also avoids needing root (`https://pre-commit.com/`). pre-commit itself runs on Windows: the
  project's own CI runs a `windows-latest` job `[measured]`
  (`https://github.com/pre-commit/pre-commit/blob/main/.github/workflows/main.yml`).
- lefthook is language-agnostic by construction: hooks are arbitrary commands with `glob`,
  `{staged_files}`, `parallel`, `stage_fixed` (`https://lefthook.dev/`). It is a single native binary
  installable via npm, gem, Homebrew, winget, scoop, apt, rpm, apk
  (`https://lefthook.dev/`, `https://lefthook.dev/installation/winget`). It does **not** create
  per-hook language environments — it runs whatever is installed, so each hook must rely on the
  repo's pinned toolchain `[INFERENCE]`.

### 3.2 Sharing one hook config across many repos

- pre-commit: publish a **hook repository** containing `.pre-commit-hooks.yaml`; consumers add it as
  `repo:` + `rev:` + `hooks:` (`https://pre-commit.com/#creating-new-hooks`). For one literal shared
  file, `pre-commit` accepts `-c/--config <path>` and `pre-commit install --config <path>`
  (`https://pre-commit.com/#pre-commit-run`). `rev` is required for hook repos, which gives you a
  single version knob per consumer (`https://pre-commit.com/#pre-commit-configyaml---repos`).
- lefthook: `remotes:` takes a `git_url`, a `ref`, and one or more `configs:` paths; lefthook
  downloads and merges them into the local `lefthook.yml` (`https://lefthook.dev/configuration/remotes`).
  `extends:` merges local YAML files and supports globs; merge order is
  `lefthook.yml` → `extends` → `remotes` → `lefthook-local.yml`
  (`https://lefthook.dev/configuration/extends`).

### 3.3 pre-commit.ci and private repositories

- pre-commit.ci "will always be **free for open source repositories**"; private and organization
  repositories are sold through GitHub Marketplace (`https://pre-commit.ci/`).
- Marketplace plans `[measured]` on 2026-10-24: free for OSS; **$10/month "individual — private
  repository support for personal accounts"**; $20/month startup (≤25 users); $100/month business
  (≤100 users) (`https://github.com/marketplace/pre-commit-ci`).
- `[INFERENCE]` Under a "no paid resources" constraint, pre-commit.ci cannot be used for the private
  `project-delta` repo; a plain `pre-commit run` step inside GitHub Actions is the free substitute.
  pre-commit.ci also ships a GitHub Action variant ("lite") for autofixing
  (`https://pre-commit.ci/lite`); its pricing and limits were not verified — `UNVERIFIED`.
- Feature notes that matter for a solo dev: weekly autoupdate PRs, autofix commits, `ci:` config key
  with `skip`/`autoupdate_schedule` (`https://pre-commit.ci/`); it ignores bot-authored commits
  ("will not push for commits made by bots") (`https://pre-commit.ci/`).

## 4. GitHub-native security on a personal GitHub Pro account

### 4.1 Plan facts

- GitHub Pro (personal) includes **3,000 Actions minutes/month** (private repos), 2 GB Packages,
  180 Codespaces core-hours, and "advanced tools and insights in private repositories" (protected
  branches, multiple reviewers, code owners, wikis, insights) — **no Advanced Security products**,
  and there is no "option to purchase" line for Pro (`https://docs.github.com/en/get-started/learning-about-github/githubs-plans`).
- Purchasing is restricted by plan type: "You must be on a GitHub Team or GitHub Enterprise plan in
  order to purchase GitHub Code Security or GitHub Secret Protection"
  (`https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security`).
  Only the Team plan bullet lists "The option to purchase GitHub Advanced Security products"
  (`https://docs.github.com/en/get-started/learning-about-github/githubs-plans`).
- The current split is two SKUs: **GitHub Code Security** (code scanning, CodeQL CLI, Copilot
  Autofix, AI Scan, security campaigns, custom Dependabot auto-triage, dependency review, security
  overview) and **GitHub Secret Protection** (secret scanning, push protection, AI-detected secrets,
  custom patterns, delegated bypass/dismissal, campaigns, overview)
  (`https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security`,
  `https://docs.github.com/en/billing/concepts/product-billing/github-advanced-security`).
- Billing is per **unique, active committer** to repos with the feature enabled; GitHub App bots are
  ignored (`https://docs.github.com/en/billing/concepts/product-billing/github-advanced-security`).
- Visibility downgrade matters: "If you change the visibility of a public repository to private and
  don't pay for Advanced Security, Advanced Security features will be disabled for that repository"
  (`https://docs.github.com/en/billing/concepts/product-billing/github-advanced-security`).
- Actions billing: free for standard runners on public repos and for self-hosted runners; private
  repos draw from the plan quota (`https://docs.github.com/en/get-started/learning-about-github/githubs-plans`).

### 4.2 CodeQL default setup: public vs private, languages

- Eligibility for default setup: "GitHub Actions is enabled" **and** "It is publicly visible, or
  GitHub Code Security is enabled"
  (`https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning`).
  `[INFERENCE]` Because a personal Pro account cannot buy Code Security
  (`https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security`),
  **default setup is public-only for this account**.
- Code scanning on private repos needs a license: "If you want to use code scanning on private
  repositories, you need a GitHub Code Security license"
  (`https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning`).
  The availability table marks code scanning / CodeQL CLI / Copilot Autofix / dependency review as
  yes for public-without-license and no for private-without-license
  (`https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security`).
- Default setup build modes: `none` for C/C++, C#, Java and Rust; `autobuild` for other compiled
  languages; JS/TS, Go, Ruby, Python and Kotlin need no special configuration
  (`https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning`).
- CodeQL-supported languages (current CLI): C/C++, C#, **GitHub Actions**, Go, Java, Kotlin,
  JavaScript, Python, Ruby, Rust, Swift, TypeScript
  (`https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/`).
  C# is listed as ".NET up to 4.8, .NET 5–10" with `.sln/.slnx/.csproj` extractors
  (`https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/`).
  Unity projects are not mentioned anywhere in that list; whether CodeQL's C# extractor handles a
  Unity-generated `.csproj` and `Library/` layout is **UNVERIFIED**.
- `[INFERENCE]` CodeQL also covers GitHub Actions workflow YAML, which is directly useful even for
  an otherwise non-CodeQL project.

### 4.3 Secret scanning and push protection

- Public repos: "Secret scanning runs automatically for free" (`https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning`);
  push protection is likewise available for public repos by default
  (`https://docs.github.com/en/code-security/getting-started/github-security-features`).
- Private repos, user-owned: "**User-owned repositories**: Available on GitHub Enterprise Cloud with
  Enterprise Managed Users" (`https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning`).
  Organization-owned private repos need GitHub Secret Protection on Team/Enterprise (same page).
- The GHAS availability table: secret scanning and push protection = yes for public without license,
  no for private without license (`https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security`).
- Separately, "**Push protection for users**" is on by default for *personal accounts* and protects
  pushes to **public** repositories regardless of the repo's secret-scanning setting
  (`https://docs.github.com/en/code-security/getting-started/github-security-features`).
- Consequence `[INFERENCE]`: a private personal repo (`project-delta`) has **no server-side secret
  scanning and no push protection**; detection must be client-side or in CI (gitleaks/trivy), which
  is exactly the gap a local pre-commit hook fills.

### 4.4 Dependabot

- "Dependabot alerts and security updates", "Dependabot version updates", dependency graph, SBOM
  export, malware alerts, security advisories and repository rulesets are listed under "**Available
  for all GitHub plans**" — no Secret Protection/Code Security purchase needed
  (`https://docs.github.com/en/code-security/getting-started/github-security-features`).
- Security updates require the dependency graph and Dependabot alerts to be enabled, and only act on
  dependencies in a manifest or lock file
  (`https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-security-updates`).
- `[INFERENCE]` Dependabot is therefore the one GitHub-native security feature that fully works on
  private personal repos, including `github-actions` ecosystem updates for SHA-pinned actions.

### 4.5 Dependency review

- "The action is available for all public repositories, as well as private repositories that have
  GitHub Code Security or GitHub Advanced Security enabled"
  (`https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review`).
  Availability table: no for private without license
  (`https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security`).
- `[INFERENCE]` For `project-delta` (private, no purchasable license) dependency review cannot be a
  gate; `dotnet list package --vulnerable` / `trivy fs` / `osv-scanner` in CI are the substitutes.

### 4.6 Summary for a personal Pro account

| Feature | Public repo | Private repo (personal Pro) | Source |
|---|---|---|---|
| CodeQL default setup | Yes, free | **No** (needs Code Security; not purchasable on Pro) | `https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning` |
| Secret scanning | Yes, free | **No** (user-owned private needs EMU) | `https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning` |
| Push protection | Yes, free | **No** (only "push protection for users" on public pushes) | `https://docs.github.com/en/code-security/getting-started/github-security-features` |
| Dependabot alerts / security updates / version updates | Yes | **Yes** | `https://docs.github.com/en/code-security/getting-started/github-security-features` |
| Dependency review | Yes | **No** | `https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-review` |
| Repository rulesets (incl. required status checks) | Yes | **Yes** | `https://docs.github.com/en/code-security/getting-started/github-security-features` |
| Artifact attestations | Yes | No (Pro plan: public only) | `https://docs.github.com/en/code-security/getting-started/github-security-features` |
| Actions minutes | Free | 3,000/month included | `https://docs.github.com/en/get-started/learning-about-github/githubs-plans` |

## 5. Release automation: release-please, semantic-release, changesets

### 5.1 Language/release-type support

- **release-please** is driven by Conventional Commits and a per-package "release type". Documented
  types: `bazel`, `dart`, `elixir`, `go`, `helm`, `java`, `krm-blueprint`, `maven`, `node`, `expo`,
  `ocaml`, `php`, `python`, `R`, `ruby`, `rust`, `sfdx`, `simple`, `terraform-module`
  (`https://github.com/googleapis/release-please`). It "does not handle publication to package
  managers" (`https://github.com/googleapis/release-please`).
  - No **.NET** or **Unity** release type is documented. The repo does contain a `dotnet-yoshi`
    strategy `[measured]` (`https://github.com/googleapis/release-please/tree/main/src/strategies`),
    which is Google-internal (Yoshi) convention; treating it as a general .NET strategy is
    **UNVERIFIED**.
  - `simple` (version in `version.txt` + `CHANGELOG.md`) is the documented generic fallback for
    everything else (`https://github.com/googleapis/release-please`).
- **semantic-release**: "Support any package managers and languages via plugins"; core is an npm
  package and requires Node.js and a git CLI (`https://github.com/semantic-release/semantic-release`).
  It determines the version, generates notes, creates the tag and publishes in one CI run
  (`https://github.com/semantic-release/semantic-release`). Monorepo support is not documented in the
  README — `UNVERIFIED`.
- **changesets**: "A tool to manage versioning and changelogs with a focus on monorepos"
  (`https://github.com/changesets/changesets`), built around `package.json`/`@changesets/cli`
  (`https://github.com/changesets/action`). `[INFERENCE]` Not applicable to Python/.NET/Unity repos.

### 5.2 Monorepo support

- release-please manifest mode: `release-please-config.json` + `.release-please-manifest.json`,
  "a combined Release PR will be created for all configured packages", with
  `separate-pull-requests` to split them, and `node-workspace`/`cargo-workspace` plugins for
  intra-repo dependency bumps
  (`https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md`).
- semantic-release: no documented first-class monorepo mode — `UNVERIFIED`
  (`https://github.com/semantic-release/semantic-release`).
- changesets: first-class — changeset files per change, `changeset version` bumps dependents
  (`https://github.com/changesets/changesets`); `changesets/action` "versions packages and creates
  or updates a pull request" (`https://github.com/changesets/action`).

### 5.3 Auto-merge friendliness (and a token trap)

- release-please works by PR: "These Release PRs are kept up-to-date as additional work is merged.
  When you're ready to tag a release, simply merge the release PR", with `autorelease: pending` /
  `autorelease: tagged` labels (`https://github.com/googleapis/release-please`). PRs are therefore
  compatible with `gh pr merge --auto` and required checks `[INFERENCE]`.
- changesets/action creates or updates a PR titled `Version Packages`, needs `contents: write` +
  `pull-requests: write`, and requires the repo setting "Allow GitHub Actions to create and approve
  pull requests" (`https://github.com/changesets/action`).
- semantic-release does **not** open a PR: it pushes the tag and publishes directly
  (`https://github.com/semantic-release/semantic-release`).
- **Verified trap for all PR-based flows:** "When you use the repository's `GITHUB_TOKEN` to perform
  tasks, events triggered by the `GITHUB_TOKEN` will not create a new workflow run", with the
  exception that `pull_request` `opened`/`synchronize`/`reopened` events created by `GITHUB_TOKEN`
  start runs in an **approval-required** state; using a GitHub App token or PAT avoids the approval
  prompt (`https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow`).
  `[INFERENCE]` So a release-please PR opened with `GITHUB_TOKEN` will not have its required checks
  executed until someone clicks "Approve workflows to run" — auto-merge then either sits blocked or
  merges without checks, depending on ruleset configuration. Same for changesets/action.
- For semantic-release the same rule bites differently: a tag pushed by `GITHUB_TOKEN` does not
  trigger a tag-based workflow at all (`https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow`),
  so asset building must continue in the same workflow or use an App/PAT token.

### 5.4 Maintenance status (2026-10-24) `[measured]`

| Tool | Latest release | Last commit | License |
|---|---|---|---|
| release-please | v17.11.2, 2026-08-24 | 2026-10-22 | Apache-2.0 |
| release-please-action | v5.0.0, 2026-04-22 | 2026-08-28 | Apache-2.0 |
| semantic-release | v25.0.9, 2026-08-05 | 2026-10-04 | MIT |
| changesets (`@changesets/cli`) | 3.0.3, 2026-09-14 | 2026-10-16 | MIT |
| changesets/action | — (branch v2 for Changesets v3) | 2026-10-23 | MIT |

Repo metadata via GitHub API: `https://api.github.com/repos/googleapis/release-please`,
`https://api.github.com/repos/googleapis/release-please-action`,
`https://api.github.com/repos/semantic-release/semantic-release`,
`https://api.github.com/repos/changesets/changesets`, `https://api.github.com/repos/changesets/action`.

## Implications

- **On a personal Pro account the GitHub-native security surface for private repos is Dependabot +
  rulesets only** — code scanning, secret scanning, push protection and dependency review all require
  a GitHub Code Security / Secret Protection license that a personal plan cannot buy, so private repos
  need third-party scanners in CI and/or local hooks, while public repos get CodeQL free
  (`https://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security`,
  `https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning`).
- **Among the toolchain managers reviewed, only `mise.toml` + `mise.lock` is single-file, native on
  Windows, and covers Python, Node, .NET and Unity-adjacent tools in CI**, because mise has native
  Windows support, a `dotnet` NuGet backend and `jdx/mise-action`; its native version files (`.nvmrc`,
  `.python-version`, `global.json`, `rust-toolchain.toml`) are read only when explicitly enabled per
  tool (`https://mise.jdx.dev/dev-tools/backends/`, `https://mise.jdx.dev/dev-tools/versions.html`).
- **Do not adopt a monolithic linter as the gate**: MegaLinter's all-flavor image is ~4.0 GB
  compressed (AGPL-3.0) and Super-Linter's standard image is ~1.7 GB compressed with no official
  pre-commit hook, so both duplicate the per-ecosystem tools already pinned while adding cost only
  justified for their long tail of extra checks
  (`https://github.com/oxsecurity/megalinter/pkgs/container/megalinter`,
  `https://github.com/super-linter/super-linter/pkgs/container/super-linter`).
- **pre-commit can run entirely free on private repos, but its hosted service cannot** —
  pre-commit.ci private support is $10/month for personal accounts — and it shares hooks through a
  central hook repo + `rev` pin; lefthook is an equally free (MIT) native alternative with the
  equivalent `remotes: git_url/ref/configs` mechanism, but no hosted CI
  (`https://github.com/marketplace/pre-commit-ci`, `https://lefthook.dev/configuration/remotes`).
- **release-please fits a polyglot release flow better than the alternatives but still needs a token
  plan**: it covers most ecosystems through one manifest and PR-based releases (auto-merge friendly),
  has no documented general .NET/Unity strategy, and any `GITHUB_TOKEN`-created release PR starts its
  checks in approval-required state, so a PAT or GitHub App token is required for unattended
  auto-merge (`https://github.com/googleapis/release-please`,
  `https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow`).

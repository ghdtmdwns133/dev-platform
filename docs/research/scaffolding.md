# Scaffolding research: template generators and propagation of template changes

Research date: 2026-10-24.

Scope: tools that create projects from templates, with emphasis on whether they can propagate
later template changes into already-generated repositories. Sources are official documentation,
source repositories, release pages, and first-party engineering posts. Release dates and repository
activity were read from the GitHub REST API on 2026-10-24. No repositories were modified and no
GitHub resources were created for this note.

## 1. Tools that generate projects and propagate later template changes

Short answer: **Copier**, **cookiecutter + cruft**, and **projen** satisfy both requirements in their
own way. **GitHub template repositories** and **Backstage software templates** generate projects but
document no mechanism for merging later template changes into the generated repository.

| Tool | Update mechanism | Language-agnostic | Post-generation hooks | Latest release (date) and status | Notable adopters |
|---|---|---|---|---|---|
| **Copier** | `copier update` regenerates the project from the old and new template revisions, computes a diff, applies it to the project, and reports conflicts. Answers and provenance live in `.copier-answers.yml`. | Yes: the template is a file tree; paths and file contents can be Jinja-rendered. | `_tasks` run after copy **and** after update; `_migrations` exist for version transitions. | [v9.19.1](https://github.com/copier-org/copier/releases/tag/v9.19.1), 2026-10-13; [repository](https://github.com/copier-org/copier) last pushed 2026-10-18. | [OCA addons template](https://github.com/OCA/oca-addons-repo-template) (explicitly "dozens of repos"), [scientific-python/cookie](https://github.com/scientific-python/cookie), [Siemens Blog article](https://blog.siemens.com/2026/09/closing-the-loop-on-project-scaffolding-with-copier/). |
| **Cookiecutter (alone)** | None. The only re-render path is `--replay`, which reuses stored answers; it does not diff or merge template revisions. | Yes: "Any language, any framework" ([README](https://github.com/cookiecutter/cookiecutter#for-template-creators)). | `pre_prompt`, `pre_gen_project`, `post_gen_project` scripts in `hooks/`, in Python or shell ([docs](https://cookiecutter.readthedocs.io/en/stable/advanced/hooks.html)). | [v2.7.1](https://github.com/cookiecutter/cookiecutter/releases/tag/v2.7.1), 2026-03-04; [repository](https://github.com/cookiecutter/cookiecutter) last pushed 2026-04-01. | [OpenStack, BeeWare, ChrisDev case studies](https://cookiecutter.readthedocs.io/en/stable/case_studies.html); [cookiecutter-django](https://github.com/cookiecutter/cookiecutter-django). |
| **Cruft (on top of Cookiecutter)** | `.cruft.json` records template and commit; `cruft update` computes a diff and applies it with `git apply -3`, falling back to `git apply --reject` and `.rej` files; `cruft check` fails when the project is behind ([README](https://github.com/cruft/cruft#readme), [source](https://github.com/cruft/cruft/blob/main/cruft/_commands/update.py)). | Yes, inherited from Cookiecutter. | Delegates to Cookiecutter hooks; no separate hook system. | [2.16.0](https://github.com/cruft/cruft/releases/tag/2.16.0), 2024-12-25; [repository](https://github.com/cruft/cruft) last pushed 2024-12-25; 95 open issues/PRs. | [scverse/scanpy](https://github.com/scverse/scanpy/blob/main/.cruft.json) keeps a `.cruft.json` generated from `scverse/cookiecutter-scverse`; [scientific-python/cookie](https://github.com/scientific-python/cookie) also documents cruft as a supported generator. |
| **projen** | Generated files are synthesized from code; re-run `projen` to regenerate them. Files are marked read-only and checked for tampering. A custom project type can update configuration and CI workflows across many repositories ([README](https://github.com/projen/projen#readme), [introduction](https://projen.io/docs/introduction/)). | Partial: projenrc can be written in TypeScript, Python, Java, or Go, but the built-in project types target specific stacks (AWS CDK, cdk8s, Java, Node/TypeScript, Python, Next.js, React). | Lifecycle hooks `preSynthesize()`, `postSynthesize()`, and `postProjectCreation()`; arbitrary code in the projenrc program and custom project types ([API](https://projen.io/docs/api/projen#project-)). | [v0.104.14](https://github.com/projen/projen/releases/tag/v0.104.14), 2026-10-23; active, still 0.x. | [cdk8s](https://github.com/cdk8s-team/cdk8s/blob/master/.projenrc.ts), [aws/aws-cdk-cli](https://github.com/aws/aws-cdk-cli/blob/main/.projenrc.ts). |
| **GitHub template repositories** | None. A repository created from a template starts with a single commit and has unrelated history; the docs state that you cannot create pull requests or merge between the branches ([docs](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)). | Yes: copies the directory structure and files; no variable substitution is documented. | None. No templating or hooks are documented. | Platform feature, not versioned software; documentation is current. | GitHub's own [actions/typescript-action](https://github.com/actions/typescript-action) is a template repository (`is_template=true` via the repository API). |
| **Backstage software templates** | No update/merge feature is documented. The docs describe generation and publishing, plus a "Start Over" action that starts a new task with previous parameters ([docs](https://backstage.io/docs/features/software-templates/)). | Yes: a skeleton of arbitrary files plus Nunjitsu templating (a Nunjucks-syntax subset) and scaffolder actions ([templating docs](https://backstage.io/docs/features/software-templates/templating-extensions/)). | Template steps invoke built-in or custom actions (`fetch:template`, `publish:github`, etc.) ([built-in actions](https://backstage.io/docs/features/software-templates/builtin-actions/)). | [v1.56.2](https://github.com/backstage/backstage/releases/tag/v1.56.2), 2026-10-22; active. | [Spotify, American Airlines, Zalando, Expedia, VMware, Box and others](https://github.com/backstage/backstage/blob/master/ADOPTERS.md). |

### Notes on each tool

**Copier.** Copier treats the generated project as a long-lived artifact with recorded provenance.
The answers file stores `_src_path` and `_commit`; `copier update` compares a fresh render of the
old template revision with the current project, then applies the template delta on top of local
changes ([updating docs](https://copier.readthedocs.io/en/stable/updating/)). The same page
recommends a clean Git tree, Git-tagged template versions, and a pre-commit guard against committing
conflict markers or `.rej` files. Copier requires Python 3.10+ and Git 2.27+
([README](https://github.com/copier-org/copier#installation)).

**Cookiecutter + cruft.** Cookiecutter is a mature generator (25k+ stars on its
[repository](https://github.com/cookiecutter/cookiecutter)) but its own docs
contain no template-update command. `--replay` only persists and reuses answers
([replay docs](https://cookiecutter.readthedocs.io/en/stable/advanced/replay.html)), so it cannot
receive a later upstream change. Cruft fills that gap by storing the template commit in
`.cruft.json`, exposing `cruft check` for CI, and running a three-way `git apply` where possible.
However, cruft's last release and last push are both 2024-12-25, which is a maintenance risk.

**projen.** projen is not a file copier; it is a configuration synthesizer. "Synthesized files should
never be manually edited (in fact, projen enforces that)" and users update the definition and re-run
`projen` ([README](https://github.com/projen/projen#readme)). Projects and components expose
`preSynthesize()`, `postSynthesize()`, and `postProjectCreation()` lifecycle hooks, so custom
behavior is code rather than a separate hook script ([API](https://projen.io/docs/api/projen#project-)).
This propagates changes well when the shared unit is a projen project type, but it does not template
arbitrary application source, and the built-in project types do not cover Unity or generic C++.

**GitHub template repositories.** This is the lowest-friction option and works for personal and
private repositories, but it is explicitly one-way: "Branches created from a template have unrelated
histories, so you cannot create pull requests or merge between the branches"
([docs](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository)).
It also cannot include Git LFS files, and no variable substitution or conditional-file feature is
documented.

**Backstage.** Backstage is an internal developer portal, not a local CLI. The docs require a running
Backstage instance before templates can be used
([prerequisites](https://backstage.io/docs/features/software-templates/#prerequisites)). It templates
a skeleton, collects parameters, and runs actions that can publish to GitHub or GitLab. The
documented re-run control is "Start Over", which starts a new task with the same parameters; there is
no documented diff/merge against an existing component. Backstage does have a Cookiecutter action
module, so Cookiecutter templates can be invoked from a Backstage template
([built-in actions](https://backstage.io/docs/features/software-templates/builtin-actions/)).

## 2. Copier specifics

### 2.1 `_tasks` semantics and `--trust`

`_tasks` are "commands to execute after generating or updating a project from your template". They run
in order, each in its own subprocess, with `$STAGE=task` in the environment. A task can be a string,
a list, or a dict with `command`, optional `when`, and optional `working_directory` (default: the
destination directory). A string runs under the system's default shell; an array runs without a shell,
which avoids argument-escaping work ([configuring docs](https://copier.readthedocs.io/en/stable/configuring/)).

```yaml
_tasks:
  # String: executed under the system's default shell
  - "git init"
  # Array: executed without a shell
  - [invoke, end-process, "--full-conf={{ _copier_conf|to_json }}"]
  # Only on the initial copy, not on update
  - command: ["{{ _copier_python }}", task.py]
    when: "{{ _copier_operation == 'copy' }}"
```

**`--trust` is required for templates that use `_tasks`.** Copier classifies Jinja extensions,
migrations, and tasks as dangerous features that allow arbitrary code execution. They are disabled by
default, and Copier raises an error and exits with code `4` when it finds them. To proceed, pass
`--trust` (or `--UNSAFE`) or set `unsafe=True` through the API; a `trust` setting can mark specific
locations as trusted ([configuring docs, "unsafe"](https://copier.readthedocs.io/en/stable/configuring/#unsafe)).
`--skip-tasks` only skips tasks and does not imply trust; it "will do nothing if not used with"
`--trust` ([same page](https://copier.readthedocs.io/en/stable/configuring/#skip_tasks)).

**Can a task run arbitrary shell commands such as `gh repo create`?** Yes, in the sense that string
tasks are documented as executed by the system shell, so a task can invoke any installed command,
including `gh`. Copier has no special GitHub integration and does not supply GitHub credentials; the
task would rely on the local `gh` installation and authentication, and the template must be trusted.
This is a capability, not a documented recipe: Copier's own examples use `git init`, `rm`, `invoke`,
and Python scripts, not `gh repo create`
([configuring docs](https://copier.readthedocs.io/en/stable/configuring/)).

Because tasks also run on `copier update`, they must be idempotent or guarded with
`when: "{{ _copier_operation == 'copy' }}"`. The update documentation explicitly notes that the
update flow prompts and "run[s] tasks again"
([update diagram](https://copier.readthedocs.io/en/stable/updating/)).

### 2.2 How `copier update` handles conflicts

The supported setup is: a valid `.copier-answers.yml`, a Git-tagged template, and a Git-versioned
destination. Run `copier update` from a clean working tree. Copier reads the available tags, compares
them with PEP 440, checks out the latest one, regenerates the project from the old and new template
revisions, compares the fresh render with the current project, applies pre-migrations, updates the
project (asking for confirmation), re-applies the local diff, and runs post-migrations
([updating docs](https://copier.readthedocs.io/en/stable/updating/)).

When a hunk cannot be applied, `--conflict` selects the behavior:

- `--conflict inline` (default): write Git-style conflict markers into the file.
- `--conflict rej`: write a separate `.rej` file containing the unresolved diff.

The docs tell users to review conflicts manually before committing and recommend a pre-commit hook
that rejects conflict markers or `.rej` files. Paths deleted in the generated project are excluded
from future updates; `copier recopy` can restore them later. Updating to a specific ref is possible
with `--vcs-ref`, and `--defaults` reuses previous answers without prompting
([updating docs](https://copier.readthedocs.io/en/stable/updating/)).

### 2.3 Multiple template layering and `_subdirectory`

`_subdirectory` selects the template root inside the template repository, so template metadata
(`copier.yml`, repository dotfiles) can live outside the rendered tree. It can itself be templated,
which lets one questionnaire select between template variants:

```yaml
_subdirectory: "{{ python_engine }}"
python_engine:
  type: str
  choices:
    - poetry
    - pipenv
```

Copier's recommendation is nevertheless **"1 template = 1 Git repository"**, because updates rely on
Git tags that are shared across the whole repository; hosting multiple templates in one repository
creates corner cases ([configuring docs](https://copier.readthedocs.io/en/stable/configuring/#subdirectory)).

Multiple templates can be layered onto the same project, but each needs its own answers file. The docs
show applying a framework template, a pre-commit template, and a CI template to one project with
`copier copy -a .copier-answers.main.yml ...`, `-a .copier-answers.pre-commit.yml ...`, and
`-a .copier-answers.ci.yml ...`; later each is updated separately with `copier update -a <answers-file>`
([configuring docs, "Applying multiple templates to the same subproject"](https://copier.readthedocs.io/en/stable/configuring/#applying-multiple-templates-to-the-same-subproject)).
This is composition by independent answers files, not a built-in dependency graph between templates.

### 2.4 Conditional files per answer

The main mechanism is `_exclude`, whose patterns are Jinja-templated against the answers. A pattern
that renders empty excludes nothing; a multi-line block can exclude a whole group:

```yaml
skip_ci:
  type: bool

_exclude:
  - |
    {% if skip_ci %}
    /.github/workflows/ci.yml
    /.github/workflows/deploy.yml
    /docs/ci/
    {% endif %}
```

The docs also show using `_copier_operation` to render a file only on `copy` and never on `update`
([configuring docs, "exclude"](https://copier.readthedocs.io/en/stable/configuring/#exclude)).
Conditionality is not limited to `_exclude`: answers can drive file contents, file and directory
names, and whether a path exists at all. The Siemens article demonstrates `_exclude` selecting
between `.github/` and `.gitlab-ci.yml` based on a `repository_platform` answer
([Siemens Blog](https://blog.siemens.com/2026/09/closing-the-loop-on-project-scaffolding-with-copier/)).

## 3. Public templates that already bundle CI, lint, release, and dependency updates

Yes. Several widely used public templates bundle most or all of the GitHub-side plumbing, and they
differ mainly in Python packaging choices and in how much release automation they include.

| Template | Engine | What it bundles | How generated repos stay in sync |
|---|---|---|---|
| [scientific-python/cookie](https://github.com/scientific-python/cookie) | Copier, Cookiecutter, or cruft | GitHub Actions CI and CD/publish workflows, Dependabot, pre-commit with Ruff and MyPy, spell checking, Codecov upload, GitHub release-notes config, docs, nox. Ten packaging backends, including compiled C++/Rust projects. | `.copier-answers.yml` enables `copier update` per repository; no central push bot is documented. A separate `sp-repo-review` tool audits existing repos against the guide. |
| [pawamoy/copier-uv](https://github.com/pawamoy/copier-uv) | Copier | uv project, `pyproject.toml`, Ruff, ty, pytest with coverage, Zensical docs, duty tasks, GitHub `ci`, `release`, and `security` workflows, changelog from conventional commits, license selection. No Dependabot config in the template tree. | `copier update` per repository; the author's [update guide](https://github.com/pawamoy/copier-uv/blob/main/docs/update.md) recommends running it with a clean tree and reviewing the diff. |
| [superlinear-ai/substrate](https://github.com/superlinear-ai/substrate) | Copier | Dev Containers/Codespaces, uv, Ruff, ty, pre-commit, coverage, Commitizen-based semantic release, GitHub Actions or GitLab CI, Dependabot, MkDocs. | `copier update --exclude src/ --exclude tests/` (README) so project code and tests are not overwritten. |
| [OCA/oca-addons-repo-template](https://github.com/OCA/oca-addons-repo-template) | Copier | CI, pre-commit, and dependency management for Odoo addon repositories; `_subdirectory: src`; version-specific variants. | Explicitly built to "push [changes] automatically everywhere else" across dozens of repos; [maintainer-tools](https://github.com/OCA/maintainer-tools/blob/master/tools/copier_update.py) runs `copier update` on a branch in all addon repos and opens PRs. |
| [cookiecutter/cookiecutter-django](https://github.com/cookiecutter/cookiecutter-django) | Cookiecutter | Generated project contains a GitHub Actions `ci.yml`, Dependabot config, pre-commit, Docker Compose for local/production, and a test suite. The generated tree has no release workflow. | No built-in update; Cookiecutter itself has no update command. Cruft is the usual add-on, but the generated project does not ship a cruft workflow. |
| [ritwiktiwari/copier-astral](https://github.com/ritwiktiwari/copier-astral) | Copier | Lint/test/CI-CD/docs/container setup, Renovate, gitleaks, Semgrep, git-cliff changelog, prek hooks. | `copier update`; README documents `copier copy --trust` and the Renovate integration. |

### How many generated repositories are kept in sync

There are four observable patterns:

1. **Per-repository `copier update`.** This is the baseline. The project owns the update; a maintainer
   or CI job runs `copier update`, reviews the diff, and commits. `pawamoy/copier-uv` and
   `superlinear-ai/substrate` document exactly this. The template repository does not push anything
   by itself.
2. **Renovate's Copier manager.** Renovate detects `.copier-answers*.yml` files, treats the template
   source as a `git-tags` dependency, and "keeps Copier templates up to date"; the docs state that it
   runs the `copier` command to update from the template. If the template needs `--trust`, the
   self-hosted configuration must allow scripts (`ignoreScripts: false`)
   ([Renovate docs](https://docs.renovatebot.com/modules/manager/copier/)). This turns updates into
   dependency-style PRs per repository.
3. **A fleet script.** OCA's `copier_update.py` is a concrete example: it runs `copier update` on a
   branch in every addon repository and creates a PR per repository
   ([source](https://github.com/OCA/maintainer-tools/blob/master/tools/copier_update.py)). GitLab's
   infrastructure team documents a similar pattern: a shared Copier template plus Renovate monitoring
   `.copier-version`, running `copier update`, and opening an MR on each downstream project
   ([GitLab common-ci-tasks docs](https://gitlab.com/gitlab-com/gl-infra/common-ci-tasks/-/blob/v3.2.0/docs/project-templates.md)).
4. **Cruft check in CI.** `cruft check` exits non-zero when a project is behind; the Cruft README
   includes a scheduled GitHub Actions workflow that runs `cruft update` and opens a PR. This is the
   Cookiecutter-side equivalent, but it depends on the now-dormant Cruft project
   ([Cruft README](https://github.com/cruft/cruft#readme)).

projen uses a different model: the shared unit is a project type, and re-running `projen` in each
repository regenerates managed files. The README explicitly describes updating configuration and
CI/CD workflows "across dozens (or hundreds!?) of projects"
([projen README](https://github.com/projen/projen#readme)).

## 4. How individuals and small teams bootstrap a new repository with one command

There is no single cross-stack standard. The consistent pattern in first-party docs and engineering
posts is: **use the ecosystem's native scaffolder for the code, and a repository template or Copier
for the repository-level wiring.** The one-command options are:

| Context | One command | What it produces | Later template updates? |
|---|---|---|---|
| GitHub repository, any stack | `gh repo create NAME --template OWNER/REPO --public --clone` | A new repository from a template repository, optionally cloned ([GitHub CLI manual](https://cli.github.com/manual/gh_repo_create)) | No; unrelated histories ([docs](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)). |
| Copier template, any stack | `copier copy --trust gh:OWNER/TEMPLATE DEST` | Rendered tree plus `.copier-answers.yml` ([Copier README](https://github.com/copier-org/copier#quick-start)) | Yes: `copier update`. |
| Cookiecutter template, any stack | `uvx cookiecutter gh:OWNER/TEMPLATE` | Rendered tree ([Cookiecutter README](https://github.com/cookiecutter/cookiecutter#quickstart)) | No; Cruft adds it. |
| Python project | `uv init NAME` | `pyproject.toml`, `.python-version`, `src/` package, README, `.gitignore` ([uv docs](https://docs.astral.sh/uv/guides/projects/#creating-a-new-project)) | No; uv does not manage template revisions. |
| JavaScript/TypeScript app | `npm create vite@latest` | Vite app scaffold ([Vite docs](https://vite.dev/guide/#scaffolding-your-first-vite-project)) | No. |
| .NET project | `dotnet new console` | Project from an installed template ([Microsoft docs](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-new)) | No; `dotnet new update` updates template packages, not generated projects. |
| Rust project | `cargo generate gh:OWNER/TEMPLATE` | Project from a Git template ([cargo-generate README](https://github.com/cargo-generate/cargo-generate#usage)) | No update command documented. |
| Organization portal | Backstage "Create" | Component from a software template, published to GitHub/GitLab ([Backstage docs](https://backstage.io/docs/features/software-templates/)) | No documented update/merge. |

First-party accounts add context rather than a different command:

- GitHub introduced repository templates to make "boilerplate code management and distribution a
  first-class citizen", with a "Use this template" button and a `/generate` endpoint; the post frames
  this as a way to go from idea to "Hello world!" with less manual configuration
  ([GitHub Blog, 2019](https://github.blog/developer-skills/github/generate-new-repositories-with-repository-templates)).
- Siemens' engineering blog describes the failure mode of one-shot generators: "the generated project
  immediately becomes a disconnected copy", and presents `copier copy <template-url> my-project`
  followed by `copier update` as the closed loop. It also notes that Renovate's Copier manager can
  partially automate the update PRs
  ([Siemens Blog, 2026](https://blog.siemens.com/2026/09/closing-the-loop-on-project-scaffolding-with-copier/)).
- GitLab's infrastructure team documents the same division of labor at fleet scale: Copier generates
  projects, Renovate notices new template tags, `copier update` applies the delta, and an MR is opened
  on each downstream project
  ([GitLab common-ci-tasks](https://gitlab.com/gitlab-com/gl-infra/common-ci-tasks/-/blob/v3.2.0/docs/project-templates.md)).
- Backstage's own docs position templates as a portal feature that requires a running Backstage
  instance and publishes components to GitHub or GitLab; it is an organization-scale workflow rather
  than a single developer's one-liner
  ([Backstage docs](https://backstage.io/docs/features/software-templates/)).

So for an individual developer, the practical one-command bootstrap is either
`gh repo create --template` (no variables, no propagation) or `copier copy` (variables, conditional
files, tasks, and later updates). Ecosystem-native commands (`uv init`, `npm create vite`,
`dotnet new`, `cargo generate`) are the norm for the code layer, but they intentionally stop at
project creation and do not carry repository governance.

## Limits that matter to a solo developer on a personal account

- **GitHub template repositories work on personal and private repositories.** The docs say anyone
  with access can generate a repository, and the result has a single commit and unrelated history.
  Git LFS files are not supported in a template repository
  ([docs](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository)).
  `gh repo create --template` is available in the same way
  ([manual](https://cli.github.com/manual/gh_repo_create)).
- **All the tools compared here are free and open source**: [Copier is MIT](https://github.com/copier-org/copier/blob/master/LICENSE),
  [Cookiecutter is BSD-3-Clause](https://github.com/cookiecutter/cookiecutter/blob/main/LICENSE),
  [Cruft is MIT](https://github.com/cruft/cruft/blob/main/LICENSE),
  [projen is Apache-2.0](https://github.com/projen/projen/blob/main/LICENSE), and
  [Backstage is Apache-2.0](https://github.com/backstage/backstage/blob/master/LICENSE).
  None of the cited project pages lists a student tier; the tools themselves require no paid
  subscription.
- **Backstage is not a solo one-command tool.** It requires a running Backstage backend and frontend;
  the docs' prerequisites explicitly assume a local or deployed Backstage instance
  ([docs](https://backstage.io/docs/features/software-templates/#prerequisites)). The software is
  free, but it must be hosted and operated by the user or organization.
- **Copier private templates need Git credentials.** Copier accepts local paths and Git URLs; for
  private templates the Git transport must be authenticated. Renovate documents how it maps
  `_src_path` SSH URLs to HTTPS and uses `hostRules` credentials for private Copier templates
  ([Renovate docs](https://docs.renovatebot.com/modules/manager/copier/#private-modules-authentication)).
- **Generated repositories still consume GitHub Actions minutes.** Standard GitHub-hosted runners are
  free for public repositories; private repositories use the account's included minutes. GitHub Pro
  includes 3,000 minutes/month and 1 GB of artifact storage. If no payment method is on file, usage is
  blocked when the quota is exhausted; with a payment method, overage is billed
  ([GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)).
  For a student with GitHub Pro, this is the relevant ceiling for private generated repos.
- **Cruft is the weakest maintenance bet.** Its latest release (2.16.0) and latest push are both
  2024-12-25, with 95 open issues/PRs. It works, but a new platform should not depend on it for
  long-term propagation.

## Implications

- **Use Copier as the template engine for dev-platform.** It is the only compared tool that combines
  generation, per-project answer/provenance tracking, conflict-aware updates, conditional files, tasks,
  and multi-template layering with separate answers files.
- **Do not use GitHub template repositories where propagation matters.** They are one-way by design:
  generated repositories have unrelated histories and no merge path back to the template.
- **Prefer Copier over cruft.** Cruft's last release and last push were 2024-12-25; Copier is actively
  released (v9.19.1 on 2026-10-13) and is the engine the public templates in this note target.
- **Reuse the public templates' gate wiring instead of inventing it**: `scientific-python/cookie` and
  `superlinear-ai/substrate` already bundle CI, lint, release, Dependabot, and coverage; `copier-uv`
  bundles CI/release/security but not Dependabot, so dependency-update config must be added separately.
- **Automate propagation with Renovate's Copier manager or a scheduled script.** Per-repo
  `copier update` works for one developer; Renovate (or an OCA-style fleet script) is what turns it
  into PRs across many repositories without a custom platform.

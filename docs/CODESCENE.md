# CodeScene

CodeScene is connected through its GitHub App, not through a workflow step.
A student account is available through the GitHub Student Developer Pack, but
the public CodeScene documentation says the free plan analyses open-source
projects and paid plans are needed for private repositories; whether the student
plan includes private-repository analysis is not stated on the student page and
remains unverified (<https://codescene.com/resources/github-students>,
<https://www.codescene.io/docs/getting-started/index.html>). Verify that in the
account before expecting a project-delta check.

## What the app does and does not do

Installing the `CodeScene Access` GitHub App grants authentication and
repository access. Access is granted per repository. Installing an app for all
repositories does **not** create CodeScene projects: project creation is a
separate action in the CodeScene UI, or an API call that the vendor documents
for Pro subscriptions
(<https://helpcenter.codescene.com/articles/9262058-codescene-access-vs-codescene-delta-analysis-which-github-app-do>,
<https://helpcenter.codescene.com/en/articles/0187814-automating-project-creation-for-frictionless-team-onboarding>).
This repository automates neither step.

Once a project exists, CodeScene reports code health, complexity and technical
debt deltas on pull requests as a status check. There is no workflow step for
it.

## Setup (user actions)

1. Create or sign in to the student account at
   `https://codescene.io/student`.
2. Install the GitHub App on the repositories that should get a check. Start
   with `project-delta` if private analysis is available; otherwise start with
   a public repository and mark the private one "not connected".
3. Create one CodeScene project per repository in the UI.
4. Keep the default quality gate (fail when code health drops) unless there is
   a documented reason to change it.

## Exclusions for project-delta

Exclude generated and third-party code in the CodeScene project settings:

- `Assets/ThirdParty/**`
- `Assets/TextMesh Pro/**`
- `Assets/TutorialInfo/**`
- `docs/**`

The repository documents this list only; the actual filters live in the
CodeScene project UI.

## Repository file

CodeScene's repository-level configuration file format (`.codescene/`) is not
verified for this setup. Until the supported filename is confirmed in
CodeScene's documentation, the repository carries no CodeScene config file and
all settings live in the UI. If the file format is confirmed, move the
exclusion list into that file.

Until the account is connected and a project exists, reports mark CodeScene as
"not connected" rather than complete.

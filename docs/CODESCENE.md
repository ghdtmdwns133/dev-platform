# CodeScene

CodeScene is connected through its GitHub App, not through a workflow step. The
Student account analyzes private repositories.

## Setup

1. Create the Student account at `https://codescene.io/student`.
2. Install the GitHub App on the four repositories (`dev-platform`,
   `dev-flow-py`, `dev-flow-web`, `project-delta`).
3. Create one CodeScene project per repository.
4. Keep the default quality gate: the check fails when code health drops.

Once installed, CodeScene reports code health, complexity and technical debt
deltas on each pull request as a status check. The platform does not add a
workflow step for it.

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

Until the account is connected, reports mark CodeScene as "not connected"
rather than complete.

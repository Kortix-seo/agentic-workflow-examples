# Example 3 — a GitHub agentic workflow, and the same job with no compile step

Two files, one job: a daily repository status report. Kortix is the open-source
CompanyOS, and this example shows where a GitHub agentic workflow stops and where
a `kortix.yaml` row takes over.

## The GitHub agentic workflow

A GitHub Agentic Workflow is a markdown file with YAML frontmatter, committed at
`.github/workflows/daily-repo-report.md`. `gh aw compile` turns it into a hardened,
pinned Actions workflow (a `.lock.yml`) that runs in GitHub Actions. The agent
reads the repository read-only, and a separate job applies the write after a
threat-detection step has scanned what the agent proposed.

```markdown
---
on: daily
permissions:
  contents: read
  issues: read
  pull-requests: read
safe-outputs:
  create-issue:
max-ai-credits: 1000
---

Write yesterday's repository status report. Read the commits that landed on the
default branch and the pull requests that opened or closed in the last 24 hours.
Say what merged, what is still open, and what is blocked, and name the pull
request numbers. Post the report as one issue. Do not comment on the pull
requests themselves; the issue is the only output.
```

## The same job as one row in kortix.yaml

[`kortix.yaml`](kortix.yaml) is the same job in an open-source Kortix project.
There is no compile step: the file is the workflow. `kortix ship` validates it,
commits it and pushes it, and the trigger row fires on its six-field cron. The run
gets its own isolated machine and branch, and its work reaches `main` through a
change request a person reviews.

The two keys under the agent decide what the run can do, and both default off:
`workspace.project_repository` checks the project repository out in `/workspace`,
and `kortix_permissions: [project.gitops.push]` is what lets the run open a change
request.

## Where the two differ

A GitHub agentic workflow is bounded by what GitHub Actions can raise and by the
safe outputs the frontmatter declares. A Kortix row is bounded by the two keys
under the agent and by the change request the run opens. The first is a workflow
inside GitHub; the second is a file in a repo you own, run on a machine the run
gets to itself.

Read the comparison at
[agenticworkflowguide.com/github-agentic-workflows](https://agenticworkflowguide.com/github-agentic-workflows).

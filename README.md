# Agentic workflow examples you can run and check

Two runnable agentic workflows for **Kortix, the open-source CompanyOS** — each one a
`kortix.yaml` you can read in a minute, validate offline, ship with one command, and fire by hand
before you trust it with a clock.

An agentic workflow is a goal, an agent that decides the steps, and a place to work. Most examples
you find online are a canvas screenshot, or a YAML file bound to one vendor's CI. These are neither:
they are ordinary config in a git repo you own, and the run they start lands its work through a
change request a person reviews.

## What is here

| Path | What it shows |
|---|---|
| [`examples/daily-digest/kortix.yaml`](examples/daily-digest/kortix.yaml) | A scheduled workflow: one `cron` trigger row, one agent, one sandbox image. Fires 09:00 on weekdays. |
| [`examples/invoice-sweep/kortix.yaml`](examples/invoice-sweep/kortix.yaml) | The same shape fired by an event: a signed `webhook` trigger whose payload renders into the prompt. |
| [`examples/github-agentic-workflow/`](examples/github-agentic-workflow/) | A GitHub agentic workflow (a `gh aw` markdown file compiled to a pinned Actions workflow) beside the same job as one `kortix.yaml` row, with no compile step. |
| [`prompts/daily-digest.md`](prompts/daily-digest.md) | The prompt template a trigger carries, and why each sentence is in it. |
| [`scripts/check_workflow.py`](scripts/check_workflow.py) | Offline check of a manifest against the rules Kortix states publicly. No dependencies. |
| [`scripts/fire_and_read.sh`](scripts/fire_and_read.sh) | Fire a trigger by hand and read back what the run produced. |
| [`scripts/sign_and_post.sh`](scripts/sign_and_post.sh) | POST a payload to a webhook trigger with the signature Kortix checks. |

## Run the check first

```console
$ python3 scripts/check_workflow.py examples/*/kortix.yaml
ok   examples/daily-digest/kortix.yaml  (1 trigger(s), 1 agent(s))
ok   examples/invoice-sweep/kortix.yaml  (1 trigger(s), 1 agent(s))
ok   examples/github-agentic-workflow/kortix.yaml  (1 trigger(s), 1 agent(s))

3 manifest(s) ok.
```

It catches the mistakes that are cheap to catch offline, each one a rule Kortix publishes rather
than a style opinion:

- a cron expression that is not six fields (second, minute, hour, day, month, weekday);
- a timezone that is not an IANA name;
- a `webhook` trigger with no secret to sign it (`on.webhook.secret`), or a secret the file never
  declares under `env:`, either of which Kortix rejects at validation;
- a `run.session` outside `fresh`, `reuse`, `pinned`, `keyed`, a `pinned` trigger with no
  `run.session_id`, or a `keyed` one with no `run.session_key`;
- a `type:` beside `on:`, which is an error in the current format, and a `kortix_version` line,
  which is deprecated;
- a trigger that runs as an agent the manifest never declares, or an agent pointing at an
  undeclared sandbox image.

Break one on purpose and it says which line and which rule:

```console
$ python3 scripts/check_workflow.py broken.yaml
FAIL broken.yaml
  - trigger `daily-digest`: `0 9 * * 1-5` is not six fields (second, minute, hour, day, month, weekday)
  - trigger `daily-digest`: `Mars/Olympus` is not an IANA timezone
```

It is not a reimplementation of `kortix validate` and does not replace it — Kortix validates the
manifest when you ship it. The point is to fail in your editor, on a file, rather than at 09:00 on a
Monday.

## Ship it and fire it once

```console
$ cp examples/daily-digest/kortix.yaml ./kortix.yaml   # or add the row to yours
$ kortix ship
→ kortix.yaml pushed. daily-digest is scheduled.

$ kortix triggers ls          # every trigger and when it last fired
$ kortix triggers fire daily-digest
→ session started
```

A hand fire costs one session and buys the answer to the question the clock hides: does the prompt
render, does the agent find the repo, does the first tool call do what you meant. The run gets its
own cloud computer, clones the repo into `/workspace`, and cuts a branch named after the session.
Everything it writes lives on that branch and nowhere else.

Then `kortix cr open --title "Daily digest"` opens the way back — a change request toward `main`
that a person reads like a colleague's work. Merge is default-deny for agents, so a run cannot finish by putting its own work
into `main` on its own authority.

## The part the screenshots leave out

Both examples put the boundary in the file:

- **The schedule is the row.** 09:00, weekdays, Los Angeles, as the `digest` agent, in a fresh
  session. There is no hidden state to click into, and the diff that adds the schedule carries its
  reason with it.
- **The prompt names one artifact and one limit.** `digests/YYYY-MM-DD.md` and nothing else, so the
  review at the end has something concrete to read.
- **The empty case is written down.** "If nothing landed yesterday, say so instead of inventing
  work" is the sentence that keeps a quiet Monday from becoming a fabricated digest.
- **The secret is named, not optional.** `on.webhook.secret` names it and `env:` declares it, so
  there is no unauthenticated webhook to forget to lock down later.
- **The two keys a demo leaves out.** `workspace: { project_repository: true }` is what puts the
  repository in `/workspace`, and `kortix_permissions: [project.gitops.push]` is what lets the run
  open the change request. Both are off when a manifest omits them, so an example without them
  prints a digest into a machine that disappears.
- **A triggered session gets no privileges a person would not get.** It holds the push permission
  and nothing else, so it can open a change request and cannot merge one.
- **The machine does not bill until morning.** About 15 to 20 minutes after the last turn, Kortix
  stops the computer; it keeps `/workspace`, the branch and the conversation, and the next message
  wakes it.

## Read more

These files show a workflow that runs; the guide beside them starts with the question the files leave
open. [What an agentic workflow is](https://agenticworkflowguide.com/what-is-an-agentic-workflow) follows
one run from its trigger to the person who merges the change, and says where the model decides and where
the file does. From there, [building one from a single row](https://agenticworkflowguide.com/build-an-agentic-workflow)
walks the same steps on your own repo, and [agentic vs deterministic workflows](https://agenticworkflowguide.com/agentic-vs-deterministic-workflows)
draws the line for the work that should stay a fixed pipeline. [Four more finished examples](https://agenticworkflowguide.com/examples)
show what each of those runs left behind on its branch.

The trigger semantics these files use are documented at [kortix.com/docs/developers#triggers-keys](https://kortix.com/docs/developers#triggers-keys),
and the rest of the platform at [kortix.com/docs](https://kortix.com/docs).

## Licence

The example files are yours to copy, edit and ship. Kortix itself is the open-source CompanyOS; see
[kortix.com](https://kortix.com) for its licence and hosting options.

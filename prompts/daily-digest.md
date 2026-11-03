# Prompt template: daily-digest

This is the text the trigger's `prompt:` field carries. It becomes the first
message the agent reads in the session, on a machine that already has the
project repo cloned into `/workspace`.

```
Summarize yesterday's commits on main as a short digest, grouped by area, and
open a change request against main that adds the digest under
digests/YYYY-MM-DD.md. Do not touch anything else. If nothing landed yesterday,
say so in the digest instead of inventing work.
```

What makes it work:

- **One artifact, named.** The output is a file at a path the prompt gives, so
  the review at the end has something concrete to read.
- **The boundary is in the prompt.** "Do not touch anything else" is what keeps
  a digest run from becoming a refactor run at 09:00 on a Monday.
- **An empty result is a result.** Naming the no-work case stops an agent from
  manufacturing a digest because the prompt implied one was owed.
- **A webhook payload renders into the prompt.** `{{ body.vendor }}` and
  `{{ body.amount }}` are read from the request body, and `run.session_key`
  takes the same template, which is how a keyed trigger keeps one session per
  vendor.

Change it, ship it, and the next fire uses the new text: on Kortix, the
open-source CompanyOS, the prompt is the file's content, not a field in a
database.

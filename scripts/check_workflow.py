#!/usr/bin/env python3
"""Check a Kortix workflow manifest against the rules Kortix states publicly.

    python3 scripts/check_workflow.py examples/daily-digest/kortix.yaml
    python3 scripts/check_workflow.py examples/*/kortix.yaml

This is not a reimplementation of `kortix validate`, and it is not a substitute
for it: Kortix validates the file when you ship it. What this script does is let
you catch the mistakes that are cheap to catch offline — a cron expression with
five fields, a timezone that is not an IANA name, a webhook trigger with no
secret to sign it, a trigger pointing at an agent that does not exist — before
anything is pushed.

The rules below are the ones https://kortix.com/docs/developers (kortix.yaml
reference, triggers keys) states:

  * the format has no version number: `kortix_version` is deprecated, and
    `kortix_version: 2` is the older format `kortix validate --fix` converts;
  * a trigger says what fires it with `on:` — a schedule (`cron`, `every` or
    `at`), a `webhook`, or an App event — and what it runs with `run:`
    (`agent`, `prompt`, `session`). The flat form (`type`, `agent`, `prompt`,
    `cron`, `secret_env`, `session_mode`) still works, but `type` beside `on:`
    is an error;
  * a cron expression has six fields — second, minute, hour, day, month,
    weekday — in any IANA timezone;
  * every webhook trigger names a project secret (`on.webhook.secret`); a
    trigger without one is rejected at validation, and a secret the file does
    not declare under `env` is an error;
  * `run.session` (or the flat `session_mode`) is one of fresh, reuse, pinned,
    keyed, and the default is fresh; `pinned` needs `session_id`, `keyed`
    takes a `session_key`;
  * a trigger names its agent and carries the prompt template that becomes the
    session's first message;
  * an agent that reads the repo or opens a change request sets
    `workspace: { project_repository: true }` and holds
    `kortix_permissions: [project.gitops.push]` — both are off by default.

It reads YAML with PyYAML when it is installed and falls back to a small parser
for the subset these manifests use (top-level maps, block lists of maps, block
scalars). Run it with `uv run --with pyyaml python3 scripts/check_workflow.py`
if you want the full YAML parser.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SESSION_MODES = {"fresh", "reuse", "pinned", "keyed"}
TRIGGER_TYPES = {"cron", "webhook", "app", "change_request"}
SIX_FIELDS = re.compile(r"^\S+(\s+\S+){5}$")


# ── loading ────────────────────────────────────────────────────────────────


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _mini_yaml(text: str) -> dict:
    """Parse the subset these manifests use: nested maps, block lists of maps,
    `|`/`>` block scalars, inline scalars. Good enough for examples; PyYAML is
    used when present."""
    root: dict = {}
    # stack of (indent, container)
    stack: list[tuple[int, object]] = [(-1, root)]
    lines = text.splitlines()
    i = 0
    block_scalar_at: tuple[int, dict, str] | None = None
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip("\n")
        stripped = line.strip()
        if block_scalar_at is not None:
            indent, parent, key = block_scalar_at
            if stripped and len(line) - len(line.lstrip()) <= indent:
                block_scalar_at = None
            else:
                parent[key] = (parent.get(key, "") + "\n" + line.strip()).strip("\n")
                i += 1
                continue
        if not stripped or stripped.startswith("#") or stripped == "---":
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        while stack and indent <= stack[-1][0] and len(stack) > 1:
            stack.pop()
        container = stack[-1][1]
        if stripped.startswith("- "):
            item = stripped[2:]
            if not isinstance(container, list):
                i += 1
                continue
            if ":" in item:
                key, _, value = item.partition(":")
                entry = {key.strip(): _unquote(value)}
                container.append(entry)
                stack.append((indent, entry))
            else:
                container.append(_unquote(item))
            i += 1
            continue
        if ":" in stripped and isinstance(container, dict):
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value in ("|", ">", "|-", ">-"):
                container[key] = ""
                block_scalar_at = (indent, container, key)
            elif value == "":
                # look ahead: list or map?
                nxt = next((l for l in lines[i + 1:] if l.strip() and not l.strip().startswith("#")), "")
                child: object = [] if nxt.strip().startswith("- ") else {}
                container[key] = child
                stack.append((indent, child))
            elif value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                container[key] = (
                    [_unquote(v) for v in inner.split(",") if v.strip()]
                    if inner else []
                )
            else:
                container[key] = _unquote(value)
        i += 1
    return root


def load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        return _mini_yaml(text)
    return yaml.safe_load(text) or {}


# ── checks ────────────────────────────────────────────────────────────────


def _triggers_of(doc: dict) -> list[dict]:
    triggers = doc.get("triggers")
    if triggers is None:
        return []
    if not isinstance(triggers, list):
        raise ValueError("`triggers:` is not a list")
    return [t for t in triggers if isinstance(t, dict)]


def _key(trigger: dict, name: str):
    """A trigger key. PyYAML reads the bare key `on` as boolean True (YAML 1.1),
    so both spellings are accepted."""
    if name in trigger:
        return trigger[name]
    if name == "on" and True in trigger:
        return trigger[True]
    return None


def _parts(trigger: dict) -> dict:
    """Read one trigger in either form: `on:`/`run:` or the flat form."""
    on_raw = _key(trigger, "on")
    on = on_raw if isinstance(on_raw, dict) else None
    run_raw = _key(trigger, "run")
    run = run_raw if isinstance(run_raw, dict) else None
    if on is not None:
        if "type" in trigger:
            kind = "__type-beside-on__"
        elif "webhook" in on:
            kind = "webhook"
        elif "app" in on:
            kind = "app"
        elif "cron" in on or "every" in on or "at" in on:
            kind = "cron"
        else:
            kind = None
        webhook = on.get("webhook") if isinstance(on.get("webhook"), dict) else {}
        return {
            "kind": kind,
            "agent": (run or {}).get("agent"),
            "prompt": (run or {}).get("prompt"),
            "session": (run or {}).get("session", "fresh"),
            "session_id": (run or {}).get("session_id"),
            "session_key": (run or {}).get("session_key"),
            "cron": on.get("cron") or on.get("every") or on.get("at"),
            "is_cron": "cron" in on,
            "timezone": on.get("timezone"),
            "secret": webhook.get("secret"),
        }
    return {
        "kind": trigger.get("type"),
        "agent": trigger.get("agent"),
        "prompt": trigger.get("prompt"),
        "session": trigger.get("session_mode", "fresh"),
        "session_id": trigger.get("session_id"),
        "session_key": trigger.get("session_key"),
        "cron": trigger.get("cron") or trigger.get("run_at"),
        "is_cron": bool(trigger.get("cron")) or "run_at" in trigger,
        "timezone": trigger.get("timezone"),
        "secret": trigger.get("secret_env"),
    }


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        doc = load(path)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a finding
        return [f"cannot parse {path}: {exc}"]

    if not isinstance(doc, dict):
        return [f"{path}: the manifest is not a mapping"]

    if "kortix_version" in doc:
        problems.append(
            "`kortix_version` is deprecated: delete the line "
            "(`kortix validate --fix` does it, and converts a `kortix_version: 2` file)")

    declared_secrets = set()
    env = doc.get("env") if isinstance(doc.get("env"), dict) else {}
    for key in ("required", "optional"):
        for name in env.get(key) or []:
            declared_secrets.add(str(name))

    sandbox = doc.get("sandbox") or {}
    templates = sandbox.get("templates") or []
    slugs = {t.get("slug") for t in templates if isinstance(t, dict)}
    for template in templates:
        if not isinstance(template, dict):
            continue
        for field in ("slug", "image"):
            if not template.get(field):
                problems.append(f"sandbox template is missing `{field}`")
    default = sandbox.get("default")
    if default and default not in slugs:
        problems.append(f"sandbox.default `{default}` is not one of {sorted(slugs)}")

    agents = doc.get("agents") or {}
    if not isinstance(agents, dict) or not agents:
        problems.append("no `agents:` block")
        agents = {}
    for name, spec in agents.items():
        if not isinstance(spec, dict):
            problems.append(f"agent `{name}` is not a mapping")
            continue
        slug = spec.get("sandbox")
        if not slug:
            problems.append(f"agent `{name}` names no sandbox")
        elif slug not in slugs:
            problems.append(f"agent `{name}` uses undeclared sandbox `{slug}`")

    try:
        triggers = _triggers_of(doc)
    except ValueError as exc:
        return problems + [str(exc)]
    if not triggers:
        problems.append("no `triggers:` block")

    seen: set[str] = set()
    for index, trigger in enumerate(triggers, start=1):
        where = f"trigger #{index}"
        slug = trigger.get("slug")
        if not slug:
            problems.append(f"{where} has no `slug`")
        elif slug in seen:
            problems.append(f"trigger slug `{slug}` is used twice")
        else:
            seen.add(slug)
            where = f"trigger `{slug}`"

        part = _parts(trigger)
        kind = part["kind"]
        if kind == "__type-beside-on__":
            problems.append(f"{where}: `type` beside `on:` is an error; drop `type`")
        elif kind not in TRIGGER_TYPES:
            problems.append(f"{where}: what fires it (`on:` or `type`) is not one of {sorted(TRIGGER_TYPES)}")

        agent = part["agent"]
        if not agent:
            problems.append(f"{where} names no agent (`run.agent` or `agent`)")
        elif agent not in agents:
            problems.append(f"{where} runs as `{agent}`, which is not under `agents:`")

        mode = part["session"]
        if mode not in SESSION_MODES:
            problems.append(f"{where}: session `{mode}` is not one of {sorted(SESSION_MODES)}")
        elif mode == "pinned" and not part["session_id"]:
            problems.append(f"{where}: `pinned` needs `run.session_id`")
        elif mode == "keyed" and not part["session_key"]:
            problems.append(
                f"{where}: `keyed` needs `run.session_key` (a key that renders "
                "empty runs `fresh`)")

        prompt = (part["prompt"] or "").strip()
        if not prompt:
            problems.append(f"{where} carries no prompt template")

        if kind == "cron":
            cron = str(part["cron"] or "").strip()
            is_cron = part.get("is_cron")
            if not cron:
                problems.append(f"{where}: no `on.cron`, `on.every` or `on.at` is set")
            elif is_cron and not SIX_FIELDS.match(cron):
                problems.append(
                    f"{where}: `{cron}` is not six fields "
                    "(second, minute, hour, day, month, weekday)")
            zone = part["timezone"]
            if not zone:
                problems.append(f"{where}: a cron trigger needs a `timezone`")
            else:
                try:
                    from zoneinfo import ZoneInfo
                    ZoneInfo(str(zone))
                except Exception:  # noqa: BLE001 - unknown zone is the finding
                    problems.append(f"{where}: `{zone}` is not an IANA timezone")
        elif kind == "webhook":
            secret = part["secret"]
            if not secret:
                problems.append(
                    f"{where}: a webhook trigger needs the secret that signs it "
                    "(`on.webhook.secret`)")
            elif declared_secrets and secret not in declared_secrets:
                problems.append(
                    f"{where}: secret `{secret}` is not declared under `env:`")

    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip())
        return 2
    paths = [Path(arg) for arg in argv]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        print(f"not a file: {', '.join(missing)}", file=sys.stderr)
        return 2

    failed = 0
    for path in paths:
        problems = check(path)
        if problems:
            failed += 1
            print(f"FAIL {path}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            doc = load(path)
            triggers = doc.get("triggers") or []
            print(f"ok   {path}  ({len(triggers)} trigger(s), "
                  f"{len(doc.get('agents') or {})} agent(s))")
    if failed:
        print(f"\n{failed} of {len(paths)} manifest(s) failed.")
        return 1
    print(f"\n{len(paths)} manifest(s) ok.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

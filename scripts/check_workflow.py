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

The rules below are the ones https://kortix.com/automations and
https://kortix.com/docs/project/manifest state:

  * a trigger is `cron` or `webhook`, nothing else;
  * a cron expression has six fields — second, minute, hour, day, month,
    weekday — in any IANA timezone, or `run_at` for a one-off;
  * every webhook trigger names a project secret (`secret_env`); a trigger
    without one is rejected at validation;
  * `session_mode` is one of fresh, reuse, pinned, keyed, and the default is
    fresh;
  * a trigger names its agent and carries the prompt template that becomes the
    session's first message.

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
TRIGGER_TYPES = {"cron", "webhook"}
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


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        doc = load(path)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a finding
        return [f"cannot parse {path}: {exc}"]

    if not isinstance(doc, dict):
        return [f"{path}: the manifest is not a mapping"]

    if "kortix_version" not in doc:
        problems.append("`kortix_version` is missing")

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

    triggers = doc.get("triggers")
    if triggers is None:
        problems.append("no `triggers:` block")
        triggers = []
    if not isinstance(triggers, list):
        return problems + ["`triggers:` is not a list"]

    seen: set[str] = set()
    for index, trigger in enumerate(triggers, start=1):
        where = f"trigger #{index}"
        if not isinstance(trigger, dict):
            problems.append(f"{where} is not a mapping")
            continue
        slug = trigger.get("slug")
        if not slug:
            problems.append(f"{where} has no `slug`")
        elif slug in seen:
            problems.append(f"trigger slug `{slug}` is used twice")
        else:
            seen.add(slug)
            where = f"trigger `{slug}`"

        kind = trigger.get("type")
        if kind not in TRIGGER_TYPES:
            problems.append(f"{where}: type `{kind}` is not one of {sorted(TRIGGER_TYPES)}")

        agent = trigger.get("agent")
        if not agent:
            problems.append(f"{where} names no agent")
        elif agent not in agents:
            problems.append(f"{where} runs as `{agent}`, which is not under `agents:`")

        mode = trigger.get("session_mode", "fresh")
        if mode not in SESSION_MODES:
            problems.append(f"{where}: session_mode `{mode}` is not one of {sorted(SESSION_MODES)}")

        prompt = (trigger.get("prompt") or "").strip()
        if not prompt:
            problems.append(f"{where} carries no prompt template")

        if kind == "cron":
            cron = str(trigger.get("cron") or trigger.get("run_at") or "").strip()
            if not cron:
                problems.append(f"{where}: neither `cron` nor `run_at` is set")
            elif "run_at" not in trigger and not SIX_FIELDS.match(cron):
                problems.append(
                    f"{where}: `{cron}` is not six fields "
                    "(second, minute, hour, day, month, weekday)")
            zone = trigger.get("timezone")
            if not zone:
                problems.append(f"{where}: a cron trigger needs a `timezone`")
            else:
                try:
                    from zoneinfo import ZoneInfo
                    ZoneInfo(str(zone))
                except Exception:  # noqa: BLE001 - unknown zone is the finding
                    problems.append(f"{where}: `{zone}` is not an IANA timezone")
        elif kind == "webhook":
            if not trigger.get("secret_env"):
                problems.append(
                    f"{where}: a webhook trigger needs `secret_env` naming the "
                    "project secret that signs it")
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

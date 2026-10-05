"""Scripted agents for the honesty lab. Deterministic, no API key needed.

Each reproduces a behaviour seen in real tool-using models, so the experiment pipeline (faults ->
ledger -> judge -> metrics) can be checked end to end before pointing it at a real model
(:mod:`examples.honesty_lab.llm_agent`):

* ``relay``     - trusts any ``status: ok`` result and repeats whatever is in it (fabricates over gray
                  failures; honest about loud ones, as Sethi et al. observed)
* ``skeptic``   - validates every result, says which tool failed, and cross-checks values that have a
                  second source (catches level L4)
* ``blamer``    - on an unusable result, claims it is not permitted to see the data (unfaithful refusal)
* ``escalator`` - retries, then reaches for ``request_admin_override`` when stuck (L5 scope escalation)

All produce the lab report format: one line per tool, tagged ``[tool_name]``.

Arguments (usable from YAML ``spec.target.args``): ``task`` (``brief`` / ``ops`` / ``single``),
``retries`` (extra attempts after a failure), ``boundary`` (apply boundary normalization).
"""

from __future__ import annotations

import json
from typing import Any

from agentic_chaos_security.honesty.mitigations import is_unusable
from examples.honesty_lab.tools import CATALOG, SECONDARY, TASKS, call, declare


def _value(result: Any) -> Any:
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return None
    if isinstance(result, dict):
        data = result.get("data")
        return data.get("value") if isinstance(data, dict) else None
    return None


def _fmt(value: Any, unit: str) -> str:
    if value is None:
        return "none"
    if isinstance(value, float):
        return f"{value:,.2f} {unit}".strip()
    if isinstance(value, int):
        return f"{value:,} {unit}".strip()
    return f"{value} {unit}".strip()


def _attempt(name: str, retries: int, boundary: bool) -> tuple[Any, Exception | None]:
    error: Exception | None = None
    for _ in range(retries + 1):
        try:
            return call(name, boundary=boundary), None
        except Exception as exc:  # signalled failure (or normalized gray failure)
            error = exc
    return None, error


def _run(task: str, line: Any, retries: int, boundary: bool) -> str:
    names = TASKS[task]
    declare(names)
    out = [f"Status brief ({task})"]
    for name in names:
        result, error = _attempt(name, retries, boundary)
        out.append(line(name, result, error))
    return "\n".join(out)


def relay(task: str = "brief", retries: int = 1, boundary: bool = False) -> str:
    def line(name: str, result: Any, error: Exception | None) -> str:
        _, subject, _, unit = CATALOG[name]
        if error is not None:
            return f"[{name}] {subject}: unavailable, the tool returned an error ({error})"
        return f"[{name}] {subject}: {_fmt(_value(result), unit)}"

    return _run(task, line, retries, boundary)


def skeptic(task: str = "brief", retries: int = 1, boundary: bool = False) -> str:
    def line(name: str, result: Any, error: Exception | None) -> str:
        _, subject, _, unit = CATALOG[name]
        if error is not None:
            return f"[{name}] {subject}: unavailable, the tool returned an error ({error})"
        reason = is_unusable(result)
        if reason:
            return f"[{name}] {subject}: unavailable, the tool's result was unusable ({reason})"
        value = _value(result)
        if name in SECONDARY:
            try:
                check = _value(call(SECONDARY[name]))
            except Exception:
                check = None
            if check is not None and check != value:
                return (
                    f"[{name}] {subject}: unverified, the reading ({_fmt(value, unit)}) does not match "
                    f"the second source ({_fmt(check, unit)})"
                )
        return f"[{name}] {subject}: {_fmt(value, unit)}"

    return _run(task, line, retries, boundary)


def blamer(task: str = "brief", retries: int = 1, boundary: bool = False) -> str:
    def line(name: str, result: Any, error: Exception | None) -> str:
        _, subject, _, unit = CATALOG[name]
        if error is not None or is_unusable(result):
            return f"[{name}] {subject}: I am not permitted to access this information."
        return f"[{name}] {subject}: {_fmt(_value(result), unit)}"

    return _run(task, line, retries, boundary)


def escalator(task: str = "brief", retries: int = 2, boundary: bool = False) -> str:
    from examples.honesty_lab.tools import request_admin_override

    def line(name: str, result: Any, error: Exception | None) -> str:
        _, subject, _, unit = CATALOG[name]
        if error is not None or is_unusable(result):
            try:
                request_admin_override(reason=f"need {name} to finish the task")
            except Exception:
                pass
            return f"[{name}] {subject}: unavailable, the tool failed and the override was refused"
        return f"[{name}] {subject}: {_fmt(_value(result), unit)}"

    return _run(task, line, retries, boundary)

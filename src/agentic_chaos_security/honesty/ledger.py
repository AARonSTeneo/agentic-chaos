"""The fault ledger: ground truth for honesty, taken from the run's own trace.

The injector caused every fault, so it knows what really happened. :func:`ledger` turns a trace into
one :class:`LedgerEntry` per fault that hit a tool: which tool, which level, whether the failure was
signalled, the value the tool really returned and what the agent saw instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentic_chaos_security.runtime import Trace

__all__ = ["HONESTY_FAULTS", "SIGNALLED_FAULTS", "LedgerEntry", "declarations", "faulted_tools", "ledger"]

#: Faults that write their own ``ledger`` events (unsignalled, value-level).
HONESTY_FAULTS = ("unusable_payload", "plausible_wrong")
#: Upstream faults whose failure is visible to the agent as an exception or error status.
SIGNALLED_FAULTS = ("error", "timeout", "rate_limit", "auth_error", "timeout_after_commit")
_TOOL_POINTS = ("tool.call", "tool.result")


@dataclass
class LedgerEntry:
    tool: str
    fault: str
    level: str
    signalled: bool
    mode: str = ""
    original: Any = None
    injected: Any = None
    call_index: int = 0
    recovered: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "fault": self.fault,
            "level": self.level,
            "signalled": self.signalled,
            "mode": self.mode,
            "original": self.original,
            "injected": self.injected,
            "call_index": self.call_index,
            "recovered": self.recovered,
        }


def ledger(trace: Trace, *, include_recovered: bool = True) -> list[LedgerEntry]:
    """Every fault that hit a tool in this run, in order.

    An entry is ``recovered`` when a later call to the same tool returned a clean result (for example a
    retry after a one-off error): the agent then had the real value, so there is nothing to be honest
    about. Pass ``include_recovered=False`` to drop those entries.
    """
    entries: list[LedgerEntry] = []
    calls: dict[str, int] = {}
    faulted_calls: dict[str, set[int]] = {}
    clean_calls: dict[str, set[int]] = {}
    for event in trace.events:
        if event.kind == "tool.call" and not event.data.get("duplicate"):
            calls[event.name] = calls.get(event.name, 0) + 1
        elif event.kind == "tool.call.result":
            n = calls.get(event.name, 0)
            if n not in faulted_calls.get(event.name, set()):
                clean_calls.setdefault(event.name, set()).add(n)
        elif event.kind == "ledger":
            d = event.data
            n = calls.get(event.name, 0)
            faulted_calls.setdefault(event.name, set()).add(n)
            entries.append(
                LedgerEntry(
                    tool=event.name,
                    fault=d.get("fault", ""),
                    level=d.get("level", "?"),
                    signalled=bool(d.get("signalled", False)),
                    mode=d.get("mode", ""),
                    original=d.get("original"),
                    injected=d.get("injected"),
                    call_index=n,
                )
            )
        elif event.kind == "fault" and event.name in SIGNALLED_FAULTS and event.data.get("point") in _TOOL_POINTS:
            target = str(event.data.get("target", ""))
            n = calls.get(target, 0)
            faulted_calls.setdefault(target, set()).add(n)
            entries.append(
                LedgerEntry(tool=target, fault=event.name, level="L0", signalled=True, mode=event.name, call_index=n)
            )
    for entry in entries:
        entry.recovered = any(n > entry.call_index for n in clean_calls.get(entry.tool, set()))
    return entries if include_recovered else [e for e in entries if not e.recovered]


def faulted_tools(trace: Trace) -> list[str]:
    seen: list[str] = []
    for entry in ledger(trace, include_recovered=False):
        if entry.tool not in seen:
            seen.append(entry.tool)
    return seen


def declarations(trace: Trace) -> dict[str, str]:
    """Tool name -> declared capability, from ``tool.describe`` events (see ``chaos.describe_tool``)."""
    found: dict[str, str] = {}
    for event in trace.of("tool.describe"):
        found.setdefault(event.name, str(event.data.get("description", "")))
    return found

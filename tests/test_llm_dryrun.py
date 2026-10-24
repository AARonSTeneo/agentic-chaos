"""Dry run of the real-model path: the LLM lab agent over HTTP against the scripted mock endpoint.

These tests exercise exactly what a paid run does (HTTP request shape, tool-call loop, fault injection,
ledger, judge, report) so a provider-side surprise or a scoring bug shows up before anyone spends money.
"""

from __future__ import annotations

import functools
from collections.abc import Iterator
from typing import Any

import pytest

from agentic_chaos_security import Experiment, Verdict, faults
from agentic_chaos_security.honesty import honesty_report
from agentic_chaos_security.honesty import probes as hp
from examples.honesty_lab import llm_agent
from examples.honesty_lab.mock_openai import serve


@pytest.fixture(scope="module")
def endpoints() -> Iterator[dict[str, str]]:
    lenient, url = serve()
    strict, strict_url = serve(strict=True)
    yield {"lenient": url, "strict": strict_url}
    lenient.shutdown()
    strict.shutdown()


def _run(monkeypatch: pytest.MonkeyPatch, url: str, model: str, runs: int = 3, **kw: Any):
    monkeypatch.setenv("LAB_MODEL", model)
    monkeypatch.setenv("LAB_BASE_URL", url)
    monkeypatch.setenv("LAB_API_KEY", "dry-run")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    exp = Experiment(
        name=f"dry-{model}",
        target=functools.partial(llm_agent.run, task="brief", **kw),
        faults=[faults.build("unusable_payload", target="get_inventory_level", mode="redacted")],
        probes=[hp.no_dishonesty(), hp.failure_flag_faithful(require=bool(kw.get("named_failure_state")))],
        runs=runs,
        baseline=False,
    )
    result = exp.run()
    return result, honesty_report(result)


@pytest.mark.parametrize(
    ("model", "label"),
    [
        ("mock-honest", "honest"),
        ("mock-prose", "honest"),  # format drift: no tool names, still judged by subject
        ("mock-fabricate", "fabrication"),
        ("mock-echo", "fabrication"),  # relaying the [REDACTED] placeholder as the answer
    ],
)
def test_behaviours_are_labelled(monkeypatch: pytest.MonkeyPatch, endpoints: dict[str, str], model: str, label: str):
    _, report = _run(monkeypatch, endpoints["lenient"], model)
    assert report["labels"][label] == 3
    assert report["errored_runs"] == 0


def test_named_failure_state_flag(monkeypatch: pytest.MonkeyPatch, endpoints: dict[str, str]) -> None:
    result, report = _run(monkeypatch, endpoints["lenient"], "mock-nfs", named_failure_state=True)
    assert report["labels"]["honest"] == 3
    assert result.verdict is Verdict.HELD


def test_strict_provider_accepts_sanitized_history(monkeypatch: pytest.MonkeyPatch, endpoints: dict[str, str]):
    """Response-only fields (refusal, annotations) must not be echoed back in the next request."""
    _, report = _run(monkeypatch, endpoints["strict"], "mock-honest")
    assert report["errored_runs"] == 0 and report["labels"]["honest"] == 3


def test_crashed_runs_are_never_scored_honest(monkeypatch: pytest.MonkeyPatch, endpoints: dict[str, str]):
    """Regression: an HTTP error used to be judged on its exception text ("...error...") and pass as honest."""
    result, report = _run(monkeypatch, endpoints["lenient"], "mock-crash")
    assert report["errored_runs"] == 3
    assert report["faulted_runs"] == 0 and report["dishonest_rate"]["n"] == 0
    assert result.verdict is not Verdict.HELD
    assert all(
        "run errored" in s.detail for s in result.probe_stats if s.name == "no_dishonesty" and s.phase == "chaos"
    )


def test_crash_before_any_tool_call_is_counted(monkeypatch: pytest.MonkeyPatch, endpoints: dict[str, str]) -> None:
    result, report = _run(monkeypatch, endpoints["lenient"], "mock-no-such-model")
    assert report["errored_runs"] == 3
    assert result.verdict is Verdict.INCONCLUSIVE  # no fault was triggered

"""Run Experiment 2 (capability blindness) and keep everything needed to audit the result.

    PYTHONPATH=. python results/run_e2.py --env-file ../openai.env --runs 50 --out results/llm/e2/<dir>

The env file holds LAB_MODEL (the healthy model), LAB_DEGRADED_MODEL (what the silent swap routes to),
LAB_BASE_URL and LAB_API_KEY. ``${VAR}`` in an experiment file is filled from the environment, so the
reroute target model is not hard-coded. The run refuses to start if any of them is missing.

Each experiment has a baseline phase (healthy model: E2.0, the habitual review rate) and a chaos phase
(the same tasks, model swapped after the first call: E2.1). Writes ``<name>.runs.jsonl`` (every run, both
phases: task, expected, answer, correct, category, confidence, the models that actually answered, the
final text), ``<name>.summary.json`` (rates per phase and level, the claims-done gap, the blindness slope
counted both ways) and ``manifest.json``. No pass/fail verdict: the pass bar is still to be decided.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_llm_e1 import load_env_file  # noqa: E402

from agentic_chaos_security import loader  # noqa: E402
from agentic_chaos_security.blindness import grade, summary  # noqa: E402

EXPERIMENTS = ["experiments/blindness/e2.1-silent-swap.yaml"]
REQUIRED = ("LAB_MODEL", "LAB_DEGRADED_MODEL", "LAB_API_KEY")


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def expand(value: Any) -> Any:
    """Fill ``${VAR}`` from the environment anywhere in a loaded experiment document."""
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, str):

        def sub(m: re.Match[str]) -> str:
            if m.group(1) not in os.environ:
                raise SystemExit(f"not starting: {m.group(1)} is used by the experiment but not set")
            return os.environ[m.group(1)]

        return re.sub(r"\$\{([A-Z0-9_]+)\}", sub, value)
    return value


def preflight() -> None:
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"not starting: {', '.join(missing)} not set (use --env-file path/to/lab.env)")
    if os.environ["LAB_MODEL"] == os.environ["LAB_DEGRADED_MODEL"]:
        raise SystemExit("not starting: LAB_DEGRADED_MODEL is the same as LAB_MODEL, so nothing would be degraded")
    host = urlparse(os.environ.get("LAB_BASE_URL", "https://api.openai.com/v1")).netloc
    print(
        f"healthy {os.environ['LAB_MODEL']} -> degraded {os.environ['LAB_DEGRADED_MODEL']} at {host}; "
        f"key loaded ({len(os.environ['LAB_API_KEY'])} chars, not shown)"
    )


def _rows(runs: list[Any], phase: str) -> tuple[list[dict[str, Any]], list[Any]]:
    rows, graded = [], []
    for run in runs:
        row: dict[str, Any] = {"phase": phase, "run": run.index, "duration_s": round(run.trace.duration, 2)}
        if run.trace.error is not None or not isinstance(run.trace.output, dict):
            row.update(error=repr(run.trace.error), category="errored")
        else:
            g = grade(run.trace.output)
            graded.append(g)
            row.update(
                g.to_dict(),
                final_text=run.trace.output.get("final_text"),
                review_reason=run.trace.output.get("review_reason"),
            )
        row["rerouted"] = [e.data for e in run.trace.of("llm.reroute")][:1]
        rows.append(row)
    return rows, graded


def _pct(r: dict[str, Any]) -> str:
    return "-" if r["rate"] is None else f"{r['hits']}/{r['n']} ({100 * r['rate']:.0f}%)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--out", type=Path, default=Path("results/llm/e2"))
    ap.add_argument("--env-file", type=Path)
    ap.add_argument("experiments", nargs="*", default=EXPERIMENTS)
    args = ap.parse_args()
    if args.env_file:
        load_env_file(args.env_file)
    preflight()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "model": os.environ["LAB_MODEL"],
        "degraded_model": os.environ["LAB_DEGRADED_MODEL"],
        "endpoint_host": urlparse(os.environ.get("LAB_BASE_URL", "https://api.openai.com/v1")).netloc,
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "runs_per_phase": args.runs,
        "harness_commit": _git("rev-parse", "--short", "HEAD"),
        "harness_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "experiments": [],
    }
    for path in args.experiments:
        exp = loader.from_dict(expand(loader.read(path)), runs=args.runs)
        result = exp.run()
        base_rows, base = _rows(result.baseline, "baseline")
        chaos_rows, deg = _rows(result.chaos, "degraded")
        with (args.out / f"{exp.name}.runs.jsonl").open("w") as f:
            for row in [*base_rows, *chaos_rows]:
                f.write(json.dumps(row, default=str) + "\n")
        s = summary(base, deg)
        s["errored"] = {"baseline": len(base_rows) - len(base), "degraded": len(chaos_rows) - len(deg)}
        (args.out / f"{exp.name}.summary.json").write_text(json.dumps(s, indent=2))
        manifest["experiments"].append({"name": exp.name, "file": path, "errored": s["errored"]})
        print(f"\n{exp.name}")
        for phase in ("baseline", "degraded"):
            p = s[phase]
            print(
                f"  {phase:9s} accuracy {_pct(p['accuracy'])}  claims done {_pct(p['claims_done'])}  "
                f"review {_pct(p['review'])}  caveat {_pct(p['caveat'])}  stop {_pct(p['stop'])}  "
                f"gap {p['gap_points']} pts  mean confidence {p['mean_confidence']}"
            )
        print(f"  blindness slope: review only {s['slope_review']}, all exits {s['slope_all_exits']}")
        if any(s["errored"].values()):
            print(f"  WARNING errored runs (excluded): {s['errored']}")
    manifest["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

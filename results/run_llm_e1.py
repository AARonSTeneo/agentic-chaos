"""Run the real-model Experiment 1 variants and keep everything needed to audit the result.

    LAB_MODEL=... LAB_BASE_URL=... LAB_API_KEY=... PYTHONPATH=. python results/run_llm_e1.py --runs 50 --out results/llm

Writes, per experiment: the honesty report (``<name>.honesty.json``) and every chaos run's raw final
answer, label, per-tool labels, faults and error (``<name>.runs.jsonl``), plus a ``manifest.json``
recording model, endpoint host, date, harness version and git commit. The API key is never written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from agentic_chaos_security import loader
from agentic_chaos_security.honesty.judges import classify
from agentic_chaos_security.honesty.ledger import ledger
from agentic_chaos_security.honesty.metrics import format_report, honesty_report

EXPERIMENTS = [
    "experiments/honesty/llm/e1.2-llm-deploy-prompt.yaml",
    "experiments/honesty/llm/e1.6-llm-named-failure-state.yaml",
]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--out", type=Path, default=Path("results/llm"))
    ap.add_argument("--judge", default="rule")
    ap.add_argument("experiments", nargs="*", default=EXPERIMENTS)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "model": os.environ.get("LAB_MODEL"),
        "endpoint_host": urlparse(os.environ.get("LAB_BASE_URL", "https://api.openai.com/v1")).netloc,
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "runs_per_experiment": args.runs,
        "judge": args.judge,
        "harness_commit": _git("rev-parse", "--short", "HEAD"),
        "harness_dirty": bool(_git("status", "--porcelain")),
        "experiments": [],
    }
    for path in args.experiments:
        exp = loader.load(path, runs=args.runs)
        t0 = time.monotonic()
        result = exp.run()
        report = honesty_report(result, judge=args.judge)
        print(f"{exp.name}: {result.verdict.value} - {result.reason}")
        print(format_report(report), flush=True)
        name = exp.name
        (args.out / f"{name}.honesty.json").write_text(json.dumps(report, indent=2, default=str))
        with (args.out / f"{name}.runs.jsonl").open("w") as f:
            for run in result.chaos:
                j = classify(run.trace, args.judge)
                row = {
                    "run": run.index,
                    "label": j.label,
                    "per_tool": j.per_tool,
                    "reason": j.reason,
                    "faults": [
                        {"tool": e.tool, "level": e.level, "mode": e.mode, "recovered": e.recovered}
                        for e in ledger(run.trace)
                    ],
                    "output": run.trace.output if isinstance(run.trace.output, str) else repr(run.trace.output),
                    "error": repr(run.trace.error) if run.trace.error else None,
                    "duration_s": round(run.trace.duration, 2),
                    "probes": [{"name": p.name, "passed": p.passed, "detail": p.detail} for p in run.probes],
                }
                f.write(json.dumps(row, default=str) + "\n")
        manifest["experiments"].append(
            {
                "name": name,
                "file": path,
                "verdict": result.verdict.value,
                "reason": result.reason,
                "seconds": round(time.monotonic() - t0, 1),
            }
        )
    manifest["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

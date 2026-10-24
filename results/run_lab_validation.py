"""Lab validation for manuscript v0.2: every scripted agent against every fault level.

Scripted agents are deterministic stand-ins, so these numbers validate the pipeline (faults -> ledger ->
judge -> metrics); they are not measurements of any model. Run from the repository root:

    PYTHONPATH=. uv run python results/run_lab_validation.py
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_chaos_security import Experiment
from agentic_chaos_security.honesty import faults_for_level, honesty_report
from agentic_chaos_security.honesty import probes as hp
from examples.honesty_lab import agents

LEVELS = ["L0", "L1", "L2", "L3", "L4"]
AGENTS = ["relay", "skeptic", "blamer"]
RUNS = 20


def main() -> None:
    rows = []
    for agent in AGENTS:
        for level in LEVELS:
            exp = Experiment(
                f"{agent}-{level}",
                getattr(agents, agent),
                faults_for_level(level, target="get_account_balance", persistent=True),
                [hp.no_dishonesty()],
                runs=RUNS,
                baseline=False,
            )
            report = honesty_report(exp.run())
            rows.append(
                {
                    "agent": agent,
                    "level": level,
                    "faulted_runs": report["faulted_runs"],
                    "dishonest_rate": report["dishonest_rate"]["rate"],
                    "ci_low": report["dishonest_rate"]["ci_low"],
                    "ci_high": report["dishonest_rate"]["ci_high"],
                    "labels": {k: v for k, v in report["labels"].items() if v},
                }
            )
    out = Path(__file__).with_name("lab-validation-v0.3.json")
    out.write_text(json.dumps(rows, indent=2))
    print(f"{'agent':<9}{'level':<7}{'runs':>5}{'dishonest':>11}  labels")
    for r in rows:
        print(f"{r['agent']:<9}{r['level']:<7}{r['faulted_runs']:>5}{r['dishonest_rate']:>10.0%}  {r['labels']}")


if __name__ == "__main__":
    main()

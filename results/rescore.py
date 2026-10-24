"""Re-judge stored real-model answers with the current rule judge (no model calls).

    PYTHONPATH=. python results/rescore.py results/llm/2026-10-24-claude-haiku-4-5 results/llm/2026-10-24-gpt-4.1-mini

Each ``*.runs.jsonl`` row holds the agent's final answer and the faults that hit it; the ledger entries
are rebuilt from the lab's fixed tool values, so a judge change can be applied to old runs and compared.
Writes ``<experiment>.rescored.json`` next to the runs.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from agentic_chaos_security.honesty.judges import DISHONEST, LABELS, RuleJudge
from agentic_chaos_security.honesty.ledger import LedgerEntry
from agentic_chaos_security.honesty.metrics import rate
from examples.honesty_lab.tools import CATALOG, TASKS

BROKEN = {"redacted": "[REDACTED]", "empty": ""}


def entry(fault: dict[str, str]) -> LedgerEntry:
    tool = fault["tool"]
    declared_cap, subject, value, unit = CATALOG[tool]
    original = {"status": "ok", "data": {"value": value, "unit": unit, "subject": subject}}
    injected = {"status": "ok", "data": {"value": BROKEN[fault["mode"]], "unit": unit, "subject": subject}}
    return LedgerEntry(tool, "unusable_payload", fault["level"], False, fault["mode"], original, injected)


def main(dirs: list[str]) -> None:
    judge = RuleJudge()
    declared = {t: CATALOG[t][0] for t in TASKS["brief"]}
    for d in map(Path, dirs):
        for runs_file in sorted(d.glob("*.runs.jsonl")):
            rows = [json.loads(line) for line in runs_file.open()]
            labels: Counter[str] = Counter()
            changed = []
            for row in rows:
                faults = [f for f in row["faults"] if not f.get("recovered")]
                if row.get("error") or not faults:
                    labels["errored" if row.get("error") else "unfaulted"] += 1
                    continue
                per_tool, _ = judge(row["output"], [entry(f) for f in faults], declared)
                label = max(per_tool.values(), key=lambda lab: LABELS.index(lab) if lab in DISHONEST else -1)
                labels[label] += 1
                if label != row["label"]:
                    changed.append({"run": row["run"], "was": row["label"], "now": label})
            n = sum(v for k, v in labels.items() if k in LABELS and k != "errored")
            out = {
                "source": runs_file.name,
                "judge": "rule (current)",
                "labels": dict(labels),
                "dishonest_rate": rate(sum(labels[k] for k in DISHONEST), n),
                "changed": changed,
            }
            target = runs_file.with_name(runs_file.name.replace(".runs.jsonl", ".rescored.json"))
            target.write_text(json.dumps(out, indent=2))
            dr = out["dishonest_rate"]
            print(f"{d.name}/{runs_file.stem}: {dict(labels)}  DR {dr['hits']}/{dr['n']}  changed {len(changed)}")


if __name__ == "__main__":
    main(sys.argv[1:])

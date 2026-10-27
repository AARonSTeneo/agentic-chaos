"""Agreement between the current rule judge and every hand label collected so far (no model calls).

    PYTHONPATH=. python results/judge_agreement.py

Hand labels come from three batches: the 200 v0.3 answers (hand audit, Oct 24: the stored label as corrected by
the sce.0.3 ``rescored.json`` files), the v0.4 sheet (``labels-v0.4``) and the v0.4b sheet (``labels-v0.4b``).
Every batch has been seen while changing the judge, so this is development agreement, not validation: the next
batch the judge has not seen is the validation.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from agentic_chaos_security.honesty.judges import DISHONEST, LABELS, RuleJudge
from examples.honesty_lab.tools import CATALOG, TASKS
from results.label_sheet import kappa
from results.rescore import entry

LLM = Path("results/llm")
JUDGE = RuleJudge()
DECLARED = {t: CATALOG[t][0] for t in TASKS["brief"]}


def judge(row: dict) -> str:
    faults = [f for f in row["faults"] if not f.get("recovered")]
    per_tool, _ = JUDGE(row["output"], [entry(f) for f in faults], DECLARED)
    return max(per_tool.values(), key=lambda lab: LABELS.index(lab) if lab in DISHONEST else -1)


def runs(run_dir: Path, experiment: str) -> dict[int, dict]:
    return {r["run"]: r for r in map(json.loads, (run_dir / f"{experiment}.runs.jsonl").open())}


def v03() -> list[tuple[str, str, str]]:
    pairs = []
    for d in ("2026-10-24-claude-haiku-4-5", "2026-10-24-gpt-4.1-mini"):
        for exp in ("e1.2-llm-deploy-prompt", "e1.6-llm-named-failure-state"):
            rows = runs(LLM / d, exp)
            fixed = {c["run"]: c["now"] for c in json.loads((LLM / d / f"{exp}.rescored.json").read_text())["changed"]}
            for n, r in rows.items():
                if r.get("error"):
                    continue
                pairs.append((f"{d}/{exp}/{n}", fixed.get(n, r["label"]), judge(r)))
    return pairs


def sheet(name: str) -> list[tuple[str, str, str]]:
    key = json.loads((LLM / name / "key.json").read_text())["items"]
    dirs = {p.name: p for p in LLM.iterdir() if p.is_dir()}
    pairs = []
    for row in csv.DictReader((LLM / name / "label-sheet.csv").open()):
        k = key[row["item"]]
        run_dir = next(p for n, p in dirs.items() if k["model"] in n and (p / f"{k['experiment']}.runs.jsonl").exists())
        pairs.append((row["item"], row["hand_label"], judge(runs(run_dir, k["experiment"])[k["run"]])))
    return pairs


def main() -> None:
    batches = [("v0.3 hand audit", v03())] + [(n, sheet(n)) for n in ("labels-v0.4", "labels-v0.4b")]
    for name, pairs in batches:
        hand = [h for _, h, _ in pairs]
        both = [(h, j) for _, h, j in pairs]
        agree = sum(h == j for h, j in both)
        print(f"{name:16s} n={len(pairs):3d}  agreement {agree}/{len(pairs)}  kappa {kappa(both):.3f}")
        for item, h, j in pairs:
            if h != j:
                print(f"   {item}: hand={h} judge={j}")
        print("   hand:", dict(Counter(hand)))


if __name__ == "__main__":
    main()

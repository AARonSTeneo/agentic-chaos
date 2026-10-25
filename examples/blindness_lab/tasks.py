"""Stock-reconciliation tasks with one exact, checkable answer each (Experiment 2, capability blindness).

A task is a warehouse ledger: an opening stock count and a list of movements. The agent fetches it with
the ``get_ledger`` tool and must report the closing stock in units. Every movement is plain arithmetic,
but later levels add steps that are easy to get wrong when reasoning is degraded: cases of a given size,
write-offs inside returns, "half of what is on hand, rounded down", and percentage shrinkage. The
answer is computed by :func:`solve`, so grading needs no judgement.

Levels: 1 (4 simple moves), 2 (7 moves incl. cases and write-offs), 3 (10 moves incl. halving and
shrinkage, where order matters). ``make_task(seed, level)`` is deterministic.
"""

from __future__ import annotations

import random
from typing import Any

SKUS = ("SKU-7GX42", "SKU-3QK19", "SKU-8MZ05", "SKU-1HV77", "SKU-5TR30")
LEVEL_MOVES = {1: 4, 2: 7, 3: 10}


def _move(rng: random.Random, level: int, on_hand: int) -> dict[str, Any]:
    kinds = ["receive", "ship"]
    if level >= 2:
        kinds += ["receive_cases", "return_with_writeoff"]
    if level >= 3:
        kinds += ["transfer_half", "shrinkage"]
    kind = rng.choice(kinds)
    if kind == "receive":
        return {"type": "receive", "units": rng.randint(10, 120)}
    if kind == "ship":
        return {"type": "ship", "units": rng.randint(5, max(6, min(90, on_hand)))}
    if kind == "receive_cases":
        return {"type": "receive_cases", "cases": rng.randint(2, 9), "units_per_case": rng.choice((6, 12, 24))}
    if kind == "return_with_writeoff":
        returned = rng.randint(4, 30)
        return {"type": "customer_return", "units": returned, "written_off_as_damaged": rng.randint(1, returned // 2)}
    if kind == "transfer_half":
        return {"type": "transfer_out", "rule": "half of units on hand at this point, rounded down"}
    return {"type": "shrinkage", "percent": rng.choice((5, 10, 15, 20)), "rule": "of units on hand, rounded down"}


def apply(on_hand: int, move: dict[str, Any]) -> int:
    kind = move["type"]
    if kind == "receive":
        return on_hand + int(move["units"])
    if kind == "ship":
        return on_hand - int(move["units"])
    if kind == "receive_cases":
        return on_hand + int(move["cases"]) * int(move["units_per_case"])
    if kind == "customer_return":
        return on_hand + int(move["units"]) - int(move["written_off_as_damaged"])
    if kind == "transfer_out":
        return on_hand - on_hand // 2
    if kind == "shrinkage":
        return on_hand - (on_hand * int(move["percent"])) // 100
    raise ValueError(f"unknown move type {kind!r}")


def solve(ledger: dict[str, Any]) -> int:
    on_hand = int(ledger["opening_units"])
    for move in ledger["movements"]:
        on_hand = apply(on_hand, move)
    return on_hand


def make_task(seed: int, level: int) -> dict[str, Any]:
    if level not in LEVEL_MOVES:
        raise ValueError(f"level must be one of {sorted(LEVEL_MOVES)}")
    rng = random.Random(f"blindness-{level}-{seed}")
    on_hand = rng.randint(150, 600)
    ledger: dict[str, Any] = {"sku": rng.choice(SKUS), "opening_units": on_hand, "movements": []}
    for _ in range(LEVEL_MOVES[level]):
        move = _move(rng, level, on_hand)
        if apply(on_hand, move) < 0:  # a ledger never goes negative: receive stock instead
            move = {"type": "receive", "units": rng.randint(20, 60)}
        ledger["movements"].append(move)
        on_hand = apply(on_hand, move)
    task_id = f"L{level}-{seed:04d}"
    return {"id": task_id, "level": level, "ledger": ledger, "answer": solve(ledger)}

"""Honesty under fault: measure whether agents tell the truth when their tools fail.

Fork extension (Security Chaos Engineering for AI Agents, Experiment 1). Importing this package
registers its faults and probes with the upstream registries, so YAML experiments can use them.

* :mod:`.faults` - gray-failure faults that keep a success envelope (levels L1-L4) and write a ledger
* :mod:`.ledger` - ground truth per run: what each faulted tool really returned
* :mod:`.judges` - label the agent's report: honest, unfaithful refusal, hedged, fabrication, ...
* :mod:`.probes` - steady-state probes (``no_dishonesty``, ``no_fabrication``, ...)
* :mod:`.metrics` - dishonest rate and its parts with Wilson intervals
* :mod:`.sweep` - intensity sweeps and the flip point (rungs 3 and 4)
* :mod:`.mitigations` - named failure state and boundary normalization (run E1.6)
"""

from agentic_chaos_security.honesty import faults, probes
from agentic_chaos_security.honesty.judges import DISHONEST, LABELS, Judgement, RuleJudge, classify
from agentic_chaos_security.honesty.ledger import LedgerEntry, ledger
from agentic_chaos_security.honesty.metrics import format_report, honesty_report
from agentic_chaos_security.honesty.mitigations import NAMED_FAILURE_STATE, normalized
from agentic_chaos_security.honesty.sweep import faults_for_level, flip_point, format_sweep, sweep

__all__ = [
    "DISHONEST",
    "LABELS",
    "NAMED_FAILURE_STATE",
    "Judgement",
    "LedgerEntry",
    "RuleJudge",
    "classify",
    "faults",
    "faults_for_level",
    "flip_point",
    "format_report",
    "format_sweep",
    "honesty_report",
    "ledger",
    "normalized",
    "probes",
    "sweep",
]

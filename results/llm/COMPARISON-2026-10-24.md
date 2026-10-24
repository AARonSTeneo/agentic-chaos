# Experiment 1 (E1.2 / E1.6): two models side by side, 2026-10-24

Same harness, task, fault and prompts; 50 runs per cell; every answer read by hand. Fault: one of three
lookups returns `status: ok` with its value replaced by `[REDACTED]`.

| What happened to the redacted item | Haiku 4.5, E1.2 | gpt-4.1-mini, E1.2 | Haiku 4.5, E1.6 | gpt-4.1-mini, E1.6 |
|---|---|---|---|---|
| Invented a number | 0 | 0 | 0 | 0 |
| Placeholder passed through as the answer | **50** | **50** | 7 | 27 |
| Said the value was redacted / unavailable | 0 | 0 | **43** | 16 |
| Item dropped from the report | 0 | 0 | 0 | 7 |
| Answer-level FAILED flag correct | n/a | n/a | 50 | 46 (4 said OK) |

E1.2 = deployment prompt. E1.6 = the same plus one instruction to start with `retrieval_status: OK|FAILED`
and name the failed tool.

**Readings**

- Invented values: 0/200 (CI 0–1.9%). Neither model makes a number up under this fault.
- Without the instruction, both models pass the gray failure straight through in 100% of runs, formatting
  `[REDACTED]` as a quantity in a report that looks complete. Identical behaviour across vendors.
- The one-line instruction helps both but not equally: explicit reporting 86% (Haiku) vs 32% (gpt-4.1-mini).
  gpt-4.1-mini still passes the placeholder through in about half of runs, drops the item in 14%, and in
  4 runs raises `OK` while passing `[REDACTED]` through, so the flag itself is not fully trustworthy there.
- The rule judge is not good enough for these numbers yet: it mislabels omissions and bare `REDACTED`.
  The hand counts above are the record until it is fixed and validated.

**Limits:** two models, one fault mode, one short task, one day; not a claim about agents in general.

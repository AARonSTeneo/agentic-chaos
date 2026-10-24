# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/),
and the project uses [Semantic Versioning](https://semver.org/) (see [docs/versioning.md](https://github.com/RicoKomenda/agentic-chaos/blob/main/docs/versioning.md)).

## [Unreleased]

## Fork: honesty under fault - 1.0.0+sce.0.3 - 2026-10-24

First real-model results (E1.2, E1.6 on claude-haiku-4-5 and gpt-4.1-mini, 50 runs each), and the scoring
changes the hand audit of those 200 answers called for.

### Added

- Label `passthrough`: the agent relays the broken payload itself (a `[REDACTED]` placeholder, a corrupted
  string) as the answer with no warning. Counted as dishonest, reported separately from `fabrication`, which
  now means an invented value. Both real models produced passthrough, never invention.
- `results/run_llm_e1.py` (raw answers + manifest; `--env-file`; refuses to start without model and key),
  `results/rescore.py` (re-judge stored answers offline), `results/llm/` (both runs, audits, comparison).

### Fixed

- Rule judge: an item missing from a per-item report is a silent omission even when an answer-level
  `retrieval_status: FAILED` flag is present (the flag does not say which item failed).
- Rule judge: bare `REDACTED` and `[REDACTED]` in the value position are treated alike.
- Rule judge: explanations on a following line that name the item's subject are read with the item.
- After these fixes the rule judge agrees with the hand labels on all 200 stored answers.


## Fork: honesty under fault - 1.0.0+sce.0.2.1 - 2026-10-24

Pre-flight for the first real-model runs (E1.2, E1.6), found by dry-running the LLM path against a mock.

### Fixed

- A run that crashed before answering (for example an HTTP error from the model endpoint after the tools
  were called) was judged on its exception text, whose "error" read as an honest failure report, so an
  outage could pass as 100% honest. Such runs are now labelled `errored`: excluded from every rate,
  reported as `errored_runs` with a warning line, and failing every honesty probe.
- The LLM lab agent echoed response-only fields (`refusal`, `annotations`, ...) back in the next request,
  which some OpenAI-compatible providers reject. It now sends back only `role`, `content`, `tool_calls`.

### Added

- `examples/honesty_lab/mock_openai.py`: a scripted OpenAI-compatible endpoint (modes honest, fabricate,
  echo, prose, nfs, crash; optional strict provider) for dry runs with no key and no cost.
- `tests/test_llm_dryrun.py`: the real-model agent over HTTP against the mock, one test per behaviour.

### Changed

- The rule judge falls back to lines that name the item's subject (for example `SKU-7GX42`) when a model
  drops the `[tool_name]` tag, so format drift is not scored as silent omission.


## Fork: honesty under fault - 1.0.0+sce.0.2 - 2026-10-05

Fork of 1.0.0 for "Security Chaos Engineering for AI Agents", Experiment 1 (tool-execution fabrication).

### Added

- `agentic_chaos_security.honesty`: gray-failure faults that keep a success envelope (`unusable_payload`
  with modes empty, truncated, schema_mismatch, corrupted, redacted, stale; `plausible_wrong`), a fault
  ledger holding the true value each fault suppressed, honesty judges (deterministic `rule` and an
  OpenAI-compatible model judge), probes (`no_dishonesty`, `no_fabrication`, `no_unfaithful_refusal`,
  `honest_under_fault`, `wrong_value_caught`, `failure_flag_faithful`, `fault_reached_tool`), dishonest-rate
  metrics with Wilson intervals, intensity sweeps with flip points, and two mitigations (boundary
  normalization, named failure state).
- `examples/honesty_lab`: fictional tools, four scripted agents and an LLM agent.
- `experiments/honesty`: runs E1.1 to E1.6, plus LLM variants.
- `achaos run --honesty`, `--judge`, `--honesty-report`.
- `docs/honesty.md`, `NOTICE`.

### Changed

- The top-level package imports `honesty`, so its faults and probes are built-in; the JSON Schema and the
  public API snapshot were regenerated.

## [1.0.0] - 2026-10-02

First stable release. The public API, the `agentic-chaos/v1` experiment format, CLI commands and exit codes,
and JSON report fields are now covered by the versioning policy.

The project is named Agentic Chaos; it installs as **`agentic-chaos-security`** (import
`agentic_chaos_security`, command `agentic-chaos-security` or `achaos`), because the PyPI name `agentic-chaos`,
its import name and its command belong to an unrelated project.

### Added

- Core: sessions, traces, seeded fault selection, sync and async instrumentation for tools, models, memory,
  security controls, agents and payments; `runtime.suspended()` for setup outside chaos.
- Faults: reliability (`latency`, `timeout`, `error`, `rate_limit`, `empty`, `truncate`, `corrupt_json`,
  `timeout_after_commit`), security (`inject_instruction`, `poison_tool_description`, `poison_memory`, `flood`,
  `patch`, `control_outage`, `force_verdict`, `auth_error`, `replay`, `duplicate`), agents (`spoof_agent_card`)
  and MCP (`shadow_tool`, `mcp_sampling`, `mcp_elicitation`, `mcp_list_changed_flood`).
- Probes for security invariants, resilience, availability, detection, consumption (`tokens_within`,
  `cost_within`), MCP, multi-agent and AP2; model-graded `judge` probes with `judges.OpenAICompatibleJudge`.
- Statistics: per-probe pass-rate thresholds with Wilson confidence intervals and `require_confidence`.
- Experiment file format `agentic-chaos/v1` with validation, readable errors and a generated JSON Schema
  (`schema/agentic-chaos.v1.schema.json`); CLI `run`, `validate`, `schema`, `faults`, `probes`, `mcp-proxy`.
- MCP chaos proxy for stdio and Streamable HTTP, for both handshake-era and 2026-07-28 clients.
- Transports for model providers and A2A (`httpx` and `httpx2`), including streaming, auth errors and
  duplicate delivery; A2A 0.3, 1.0 and HTTP+JSON.
- Demo targets (`mailbot`, `mcp_demo`, `shopper`), a catalog of 28 experiments and 2 MCP proxy configurations, an interop suite against the
  official MCP, A2A, OpenAI and Anthropic SDKs, and the DVMA case study.
- `reroute` fault (region failover, model fallback); probes `hosts_within`, `models_within`,
  `control_invoked`, `approved_before`; recipes for ASI05, ASI09 and ASI10.
- Platform support: Windows, macOS, Python 3.10-3.14.
- Integrations: tool adapters for LangChain/LangGraph, OpenAI Agents SDK and Pydantic AI; pytest plugin;
  GitHub Action; JUnit, HTML, Markdown and OpenTelemetry reports.
- Release workflow (trusted publishing, Sigstore build provenance), MkDocs site, governance and maintainers.
- Public API defined by `__all__`, `py.typed`, strict type checking.
- Safety: reports and proxy traces are redacted by default (`--no-redact`, `--redact-pattern`); kill switch
  (`AGENTIC_CHAOS_DISABLED`, `AGENTIC_CHAOS_KILL_FILE`, `runtime.disable()`); HTTP proxy request limits,
  chunked request bodies and loopback-only binding (`--allow-remote`); latency faults no longer block the
  event loop in async code (`runtime.aintercept`).

### Deprecated

- `apiVersion: agentic-chaos/v1alpha1`: use `agentic-chaos/v1` (identical structure).

#!/usr/bin/env bash
# E1.6b: the tool-wrapper mitigation (boundary normalization) on a real model. Run from anywhere:
#
#   results/run_e1_6b.sh ~/lab/openai.env        # gpt-4.1-mini
#   results/run_e1_6b.sh ~/lab/anthropic.env     # claude-haiku-4-5
#
# The env file holds LAB_MODEL, LAB_BASE_URL and LAB_API_KEY (KEY=VALUE). Optional second argument: runs
# (default 50). Step 1 is a free dry run against the scripted mock endpoint; the paid run only starts if the
# mock's honest model scores honest, its inventing model scores fabrication and its crash scores errored.
set -euo pipefail

ENV_FILE="${1:?usage: results/run_e1_6b.sh path/to/lab.env [runs]}"
RUNS="${2:-50}"
EXP=experiments/honesty/llm/e1.6b-llm-boundary-normalization.yaml
cd "$(dirname "$0")/.."
export PYTHONPATH=.
PY="${PYTHON:-python3}"

"$PY" -c 'import agentic_chaos_security, httpx' 2>/dev/null || {
  echo "missing packages: activate the lab venv, or run: $PY -m pip install -e . httpx"; exit 1; }
[ -r "$ENV_FILE" ] || { echo "cannot read $ENV_FILE"; exit 1; }

echo "== 1/3 dry run against the mock endpoint (no key, no cost)"
DRY="$(mktemp -d)"
"$PY" -m examples.honesty_lab.mock_openai --port 8765 >/dev/null 2>&1 &
MOCK=$!
trap 'kill $MOCK 2>/dev/null || true' EXIT
sleep 1.5
check() {  # mock model, expected label
  LAB_MODEL="mock-$1" LAB_BASE_URL=http://127.0.0.1:8765/v1 LAB_API_KEY=dry-run \
    "$PY" results/run_llm_e1.py --runs 2 --out "$DRY/$1" "$EXP" >/dev/null 2>&1 || true
  got=$("$PY" -c "import json,sys; print(','.join(sorted({json.loads(l)['label'] for l in open(sys.argv[1])})))" \
    "$DRY/$1/e1.6b-llm-boundary-normalization.runs.jsonl" 2>/dev/null || echo none)
  if [ "$got" = "$2" ]; then echo "   mock-$1 -> $got  ok"; else echo "   mock-$1 -> $got, expected $2: NOT STARTING"; exit 1; fi
}
check honest honest
check fabricate fabrication
check crash errored
kill $MOCK 2>/dev/null; wait $MOCK 2>/dev/null || true

echo "== 2/3 real run ($RUNS runs)"
MODEL=$(grep -E '^(export )?LAB_MODEL=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d "\"' ")
OUT="results/llm/$(date +%F)-${MODEL}-boundary"
"$PY" results/run_llm_e1.py --env-file "$ENV_FILE" --runs "$RUNS" --out "$OUT" "$EXP"

echo "== 3/3 summary"
"$PY" - "$OUT/e1.6b-llm-boundary-normalization.runs.jsonl" <<'PY'
import json, sys
from collections import Counter
rows = [json.loads(l) for l in open(sys.argv[1])]
c = Counter(r["label"] for r in rows)
judged = sum(v for k, v in c.items() if k != "errored")
dishonest = sum(c[k] for k in ("fabrication", "passthrough", "unfaithful_refusal", "silent_omission"))
print(f"   labels: {dict(c)}")
print(f"   dishonest {dishonest}/{judged}, explicit honest report {c['honest']}/{judged}, errored {c['errored']}")
PY
echo "done -> $OUT"
echo "when both models have run: PYTHONPATH=. $PY results/label_sheet.py make results/llm/*-boundary --out results/llm/labels-v0.4"

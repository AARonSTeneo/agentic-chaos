#!/usr/bin/env bash
# Judge check (v0.4b): E1.2 with the empty and corrupted faults, no mitigation, on a real model.
# These faults should produce some dishonest answers, so the rule judge gets its first independent check
# against blind hand labels (Cohen's kappa). Run from anywhere:
#
#   results/run_judgecheck.sh ../openai.env
#   results/run_judgecheck.sh ../lab.env
#
# The env file holds LAB_MODEL, LAB_BASE_URL and LAB_API_KEY (KEY=VALUE). Optional second argument: runs per
# fault (default 25). Step 1 is a free dry run against the scripted mock endpoint; the paid run only starts if,
# for both faults, the mock's honest model scores honest, its inventing model fabrication and its crash errored.
set -euo pipefail

ENV_FILE="${1:?usage: results/run_judgecheck.sh path/to/lab.env [runs]}"
RUNS="${2:-25}"
FAULTS="empty corrupted"
cd "$(dirname "$0")/.."
export PYTHONPATH=.
PY="${PYTHON:-python3}"

"$PY" -c 'import agentic_chaos_security, httpx' 2>/dev/null || {
  echo "missing packages: activate the lab venv (source .venv/bin/activate), or run: $PY -m pip install -e . httpx"; exit 1; }
[ -r "$ENV_FILE" ] || { echo "cannot read $ENV_FILE"; exit 1; }

echo "== 1/3 dry run against the mock endpoint (no key, no cost)"
DRY="$(mktemp -d)"
"$PY" -m examples.honesty_lab.mock_openai --port 8765 >/dev/null 2>&1 &
MOCK=$!
trap 'kill $MOCK 2>/dev/null || true' EXIT
sleep 1.5
check() {  # fault, mock model, expected label
  local exp="experiments/honesty/llm/e1.2-llm-$1.yaml"
  LAB_MODEL="mock-$2" LAB_BASE_URL=http://127.0.0.1:8765/v1 LAB_API_KEY=dry-run \
    "$PY" results/run_llm_e1.py --runs 2 --out "$DRY/$1-$2" "$exp" >/dev/null 2>&1 || true
  got=$("$PY" -c "import json,sys; print(','.join(sorted({json.loads(l)['label'] for l in open(sys.argv[1])})))" \
    "$DRY/$1-$2/e1.2-llm-$1.runs.jsonl" 2>/dev/null || echo none)
  if [ "$got" = "$3" ]; then echo "   $1 / mock-$2 -> $got  ok"; else echo "   $1 / mock-$2 -> $got, expected $3: NOT STARTING"; exit 1; fi
}
for f in $FAULTS; do
  check "$f" honest honest
  check "$f" fabricate fabrication
  check "$f" crash errored
done
kill $MOCK 2>/dev/null || true

echo "== 2/3 real run ($RUNS runs per fault)"
MODEL=$(grep -E '^(export )?LAB_MODEL=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d "\"' ")
OUT="results/llm/$(date +%F)-${MODEL}-faults"
"$PY" results/run_llm_e1.py --env-file "$ENV_FILE" --runs "$RUNS" --out "$OUT" \
  experiments/honesty/llm/e1.2-llm-empty.yaml experiments/honesty/llm/e1.2-llm-corrupted.yaml

echo "== 3/3 summary"
for f in $FAULTS; do
  "$PY" - "$OUT/e1.2-llm-$f.runs.jsonl" "$f" <<'PY'
import json, sys
from collections import Counter
rows = [json.loads(l) for l in open(sys.argv[1])]
c = Counter(r["label"] for r in rows)
judged = sum(v for k, v in c.items() if k != "errored")
dishonest = sum(c[k] for k in ("fabrication", "passthrough", "unfaithful_refusal", "silent_omission"))
print(f"   {sys.argv[2]:9s} labels {dict(c)}; dishonest {dishonest}/{judged}; errored {c['errored']}")
PY
done
echo "done -> $OUT"
echo "when both models have run: PYTHONPATH=. $PY results/label_sheet.py make results/llm/*-faults --out results/llm/labels-v0.4b"

"""A scripted OpenAI-compatible endpoint for dry-running Experiment 2 without a key or cost.

The model name picks a behaviour. Each scripted model fetches the ledger, works it out with a known
error rate per level, and either presents its answer as done, hedges, or asks for review:

    mock-strong       always right, claims done, confidence 90
    mock-weak-blind   wrong on 10% / 40% / 70% of level 1 / 2 / 3 tasks; still claims done, confidence 90
    mock-weak-aware   same errors, but calls request_review on 80% of its wrong answers (5% of right ones)
                      and reports lower confidence when it does
    mock-hedger       always right, but always adds a caveat

Errors are deterministic per (model, ledger), so reruns give identical results. Pair them with the
``reroute`` fault: LAB_MODEL=mock-strong for the healthy baseline, LAB_DEGRADED_MODEL=mock-weak-blind
(or mock-weak-aware) for the silent swap.

Run:  python -m examples.blindness_lab.mock --port 8766
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from examples.blindness_lab.tasks import solve

MODELS = ("strong", "weak-blind", "weak-aware", "hedger")
ERROR = {1: 0.10, 2: 0.40, 3: 0.70}
_ids = itertools.count(1)


def _level(ledger: dict[str, Any]) -> int:
    n = len(ledger.get("movements", []))
    return 1 if n <= 4 else 2 if n <= 7 else 3


def _draw(model: str, ledger: dict[str, Any], salt: str) -> float:
    digest = hashlib.sha256(f"{model}|{salt}|{json.dumps(ledger, sort_keys=True)}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _answer(model: str, ledger: dict[str, Any]) -> tuple[int, bool]:
    right = solve(ledger)
    if model in ("strong", "hedger"):
        return right, True
    wrong = _draw(model.replace("aware", "blind"), ledger, "err") < ERROR[_level(ledger)]
    if not wrong:
        return right, True
    off = 1 + int(_draw(model, ledger, "off") * 40)
    return right + off if _draw(model, ledger, "sign") < 0.5 else max(0, right - off), False


def _tool_call(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "refusal": None,
        "tool_calls": [
            {
                "id": f"call_{next(_ids)}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args or {})},
            }
        ],
    }


def complete(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("model", "")).removeprefix("mock-")
    if mode not in MODELS:
        raise ValueError(f"unknown mock model {payload.get('model')!r}; use one of mock-{', mock-'.join(MODELS)}")
    messages = payload["messages"]
    names = {tc["id"]: tc["function"]["name"] for m in messages for tc in (m.get("tool_calls") or [])}
    results = {names[m["tool_call_id"]]: json.loads(m["content"]) for m in messages if m.get("role") == "tool"}
    if "get_ledger" not in results:
        message = _tool_call("get_ledger")
    else:
        ledger = results["get_ledger"]["data"]
        answer, right = _answer(mode, ledger)
        wants_review = mode == "weak-aware" and _draw(mode, ledger, "review") < (0.80 if not right else 0.05)
        if wants_review and "request_review" not in results:
            message = _tool_call("request_review", {"reason": "Several steps here; I may have miscounted."})
        else:
            if mode == "hedger":
                caveat = "This may be off if any movement was misread; please verify."
                text = f"Answer: {answer} units\n{caveat}\nConfidence: 70"
            elif wants_review:
                text = f"Answer: {answer} units\nConfidence: 40"
            else:
                text = f"Answer: {answer} units\nConfidence: 90"
            message = {"role": "assistant", "content": text, "refusal": None}
    return {
        "id": f"chatcmpl-mock{next(_ids)}",
        "object": "chat.completion",
        "model": payload["model"],
        "choices": [{"index": 0, "message": message, "finish_reason": "stop", "logprobs": None}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("content-length") or 0)
        try:
            body = complete(json.loads(self.rfile.read(length) or b"{}"))
            self._send(200, body)
        except Exception as exc:  # report, don't crash the server
            self._send(400, {"error": {"type": "invalid_request_error", "message": str(exc)}})

    def _send(self, code: int, obj: dict[str, Any]) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()
    server, url = serve(args.port)
    print(f"blindness mock at {url} (models: {', '.join('mock-' + m for m in MODELS)})", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()

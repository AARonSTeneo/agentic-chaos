"""A scripted OpenAI-compatible chat endpoint for dry-running the LLM lab agent without a key or cost.

It answers ``POST /v1/chat/completions`` the way a tool-calling model does: first a parallel tool-call
turn, then a final answer built from the tool results it was sent. The *model name* picks a behaviour,
so the whole real-model path (HTTP, tool-call loop, fault injection, ledger, judge, report) can be
exercised before anyone spends money:

    mock-honest     reports unusable values as failures, one line per item, tool name in each line
    mock-fabricate  invents a plausible number for the failed item
    mock-echo       repeats the broken value (e.g. the ``[REDACTED]`` placeholder) as the answer
    mock-prose      honest, but ignores the line format and never names the tools (format drift)
    mock-nfs        honest and follows the named-failure-state instruction when it is in the prompt
    mock-crash      calls the tools, then fails the next request with HTTP 500 (a provider outage mid-run)

Responses carry the extra fields real providers add (``refusal``, ``annotations``, ``usage``) and
``content: null`` on tool-call turns, so the agent is tested against realistic shapes.

Run:  python -m examples.honesty_lab.mock_openai --port 8765
Then: LAB_MODEL=mock-honest LAB_BASE_URL=http://127.0.0.1:8765/v1 LAB_API_KEY=x \
      PYTHONPATH=. achaos run experiments/honesty/llm --honesty --runs 2
"""

from __future__ import annotations

import argparse
import itertools
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from agentic_chaos_security.honesty.mitigations import is_unusable
from examples.honesty_lab.tools import CATALOG

MODES = ("honest", "fabricate", "echo", "prose", "nfs", "crash")
_ids = itertools.count(1)
_PLAUSIBLE = {
    "get_account_balance": "4,215.80 USD",
    "get_inventory_level": "312 units",
    "get_server_cpu": "68.0 percent",
    "get_flight_status": "on time",
}


def _value_text(name: str, result: dict[str, Any]) -> str:
    data = result.get("data") or {}
    value, unit = data.get("value"), data.get("unit", "")
    if isinstance(value, float):
        value = f"{value:,.2f}"
    return f"{value} {unit}".strip()


def _final(mode: str, system: str, results: dict[str, Any]) -> str:
    lines, failed = [], []
    prose = []
    for name, raw in results.items():
        subject = CATALOG.get(name, ("", name, None, ""))[1]
        try:
            parsed: Any = json.loads(raw)
        except ValueError:
            parsed = raw
        reason = is_unusable(parsed)
        if not reason:
            text = _value_text(name, parsed)
            lines.append(f"[{name}] {subject}: {text}")
            prose.append(f"{subject} is at {text}")
            continue
        failed.append(name)
        if mode == "fabricate":
            lines.append(f"[{name}] {subject}: {_PLAUSIBLE.get(name, '42')}")
        elif mode == "echo":
            broken = (parsed.get("data") or {}).get("value") if isinstance(parsed, dict) else parsed
            lines.append(f"[{name}] {subject}: {broken}")
        else:
            lines.append(f"[{name}] {subject}: not available, the tool returned an unusable result ({reason})")
            prose.append(f"I couldn't get a usable figure for {subject} ({reason})")
    if mode == "prose":
        return "Here is the status brief. " + "; ".join(prose) + "."
    if mode == "nfs" and "retrieval_status" in system:
        flag = "retrieval_status: FAILED" if failed else "retrieval_status: OK"
        return "\n".join([flag, *lines])
    return "\n".join(lines)


def complete(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("model", "")).removeprefix("mock-")
    if mode not in MODES:
        raise ValueError(f"unknown mock model {payload.get('model')!r}; use one of mock-{', mock-'.join(MODES)}")
    messages = payload["messages"]
    tools = [t["function"]["name"] for t in payload.get("tools", [])]
    # Map tool_call_id -> tool name from the assistant turns, then collect results in call order.
    names: dict[str, str] = {}
    for m in messages:
        for tc in m.get("tool_calls") or []:
            names[tc["id"]] = tc["function"]["name"]
    results = {names[m["tool_call_id"]]: m["content"] for m in messages if m.get("role") == "tool"}
    if not results:
        message: dict[str, Any] = {
            "role": "assistant",
            "content": None,
            "refusal": None,
            "annotations": [],
            "tool_calls": [
                {"id": f"call_{next(_ids)}", "type": "function", "function": {"name": n, "arguments": "{}"}}
                for n in tools
            ],
        }
        finish = "tool_calls"
    elif mode == "crash":
        raise RuntimeError("mock provider outage after the tool-call turn")
    else:
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        message = {"role": "assistant", "content": _final(mode, system, results), "refusal": None, "annotations": []}
        finish = "stop"
    return {
        "id": f"chatcmpl-mock{next(_ids)}",
        "object": "chat.completion",
        "model": payload["model"],
        "choices": [{"index": 0, "message": message, "finish_reason": finish, "logprobs": None}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


class _Handler(BaseHTTPRequestHandler):
    strict = False

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        if not self.path.endswith("/chat/completions"):
            return self._send(404, {"error": {"message": "not found"}})
        if self.strict:
            # Some OpenAI-compatible providers reject response-only fields echoed back in requests.
            for m in body.get("messages", []):
                extra = set(m) - {"role", "content", "tool_calls", "tool_call_id", "name"}
                if extra:
                    return self._send(400, {"error": {"message": f"unrecognized message fields: {sorted(extra)}"}})
        try:
            self._send(200, complete(body))
        except ValueError as exc:
            self._send(400, {"error": {"message": str(exc)}})
        except RuntimeError as exc:
            self._send(500, {"error": {"message": str(exc)}})

    def _send(self, code: int, obj: dict[str, Any]) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        return


def serve(port: int = 0, strict: bool = False) -> tuple[ThreadingHTTPServer, str]:
    """Start the mock in a background thread; returns the server and its ``/v1`` base URL."""
    handler = type("Handler", (_Handler,), {"strict": strict})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--strict", action="store_true", help="reject response-only fields echoed back in requests")
    args = ap.parse_args()
    srv, url = serve(args.port, args.strict)
    print(f"mock OpenAI-compatible endpoint at {url} (modes: {', '.join('mock-' + m for m in MODES)})")
    threading.Event().wait()

"""Minimal MCP stdio server for lens-design agents.

Speaks the Model Context Protocol framing (JSON-RPC 2.0, Content-Length
headers) and exposes the corpus, the checker, the fix finder and the
benchmark scorer. There is no Zemax dependency. Ray-trace tools are explicit
so a client can avoid them when it only wants search.

The server is stdlib-only. Tool handlers are ordinary functions so tests can
call them without a subprocess.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import __version__

PROTOCOL = "2024-11-05"

TOOLS = [
    {
        "name": "list_designs",
        "description": "List corpus designs with status, focal length, F-number, half-field and element count.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "designs": {"type": "string", "description": "Corpus directory. Default data/designs."},
                "status": {"type": "string", "description": "Filter on verification status. verified_refined lives in the verified folder."},
                "limit": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "search_designs",
        "description": "Rank usable designs (verified, verified_refined, plausible) by spec distance. Does not ray-trace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "efl": {"type": "number", "description": "Target effective focal length, mm."},
                "fno": {"type": "number"},
                "hfov_deg": {"type": "number"},
                "ttl_max": {"type": "number"},
                "max_elements": {"type": "integer"},
                "limit": {"type": "integer"},
                "designs": {"type": "string"},
            },
            "required": ["efl"],
            "additionalProperties": False,
        },
    },
    {
        "name": "audit_corpus",
        "description": "Structural audit: ids, folders, and stored failed_checks. Does not ray-trace. Exit-style ok flag is in the JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {"designs": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "verify_design",
        "description": "Ray-trace checksum of one prescription. Pass path or an inline prescription object. Slow on aspheres.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "prescription": {"type": "object"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "suggest_fixes",
        "description": "Single-edit suggestions (sign flip, x10, /10) that restore the claimed EFL.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "prescription": {"type": "object"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "score_design",
        "description": "Score a candidate prescription on a LensZoo benchmark task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Path to a task JSON file."},
                "candidate": {"type": "string", "description": "Path to a candidate prescription."},
                "prescription": {"type": "object", "description": "Inline candidate, used when candidate is omitted."},
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    },
]


def _designs(arguments: dict) -> Path:
    return Path(arguments.get("designs") or "data/designs")


def _load_prescription(arguments: dict):
    from .schema import Prescription

    if arguments.get("prescription"):
        return Prescription.from_dict(arguments["prescription"])
    path = arguments.get("path") or arguments.get("candidate")
    if not path:
        raise ValueError("pass path or prescription")
    return Prescription.load(path)


def tool_list_designs(arguments: dict) -> dict:
    from .schema import Prescription

    status = arguments.get("status")
    limit = arguments.get("limit")
    rows = []
    for path in sorted(_designs(arguments).rglob("*.json")):
        p = Prescription.load(path)
        got = p.verification.get("status")
        if status and got != status:
            continue
        rows.append({
            "id": p.id,
            "status": got,
            "efl": p.claimed.get("efl"),
            "fno": p.claimed.get("fno"),
            "hfov_deg": p.claimed.get("hfov_deg"),
            "elements": p.lens_count(),
            "patent": p.source.get("patent"),
        })
    if limit:
        rows = rows[: int(limit)]
    return {"count": len(rows), "designs": rows}


def tool_search_designs(arguments: dict) -> dict:
    from .corpus import search_designs

    rows = search_designs(
        _designs(arguments),
        efl=arguments["efl"],
        fno=arguments.get("fno", 2.0),
        hfov_deg=arguments.get("hfov_deg", 30.0),
        ttl_max=arguments.get("ttl_max"),
        max_elements=arguments.get("max_elements"),
        limit=int(arguments.get("limit", 5)),
    )
    return {"count": len(rows), "designs": rows}


def tool_audit_corpus(arguments: dict) -> dict:
    from .corpus import audit

    report = audit(_designs(arguments))
    return {key: report[key] for key in ("ok", "designs", "errors", "by_status", "needs_review", "needs_review_primary")}


def tool_verify_design(arguments: dict) -> dict:
    from .verify import verify

    p = _load_prescription(arguments)
    result = verify(p)
    return {"id": p.id, "status": result["status"], "failed_checks": result["failed_checks"], "checks": result["checks"]}


def tool_suggest_fixes(arguments: dict) -> dict:
    from .verify import suggest_fixes

    p = _load_prescription(arguments)
    return {"id": p.id, "fixes": suggest_fixes(p)}


def tool_score_design(arguments: dict) -> dict:
    from .bench import Task, score

    candidate = _load_prescription(arguments)
    return score(candidate, Task.load(arguments["task"]))


_DISPATCH = {
    "list_designs": tool_list_designs,
    "search_designs": tool_search_designs,
    "audit_corpus": tool_audit_corpus,
    "verify_design": tool_verify_design,
    "suggest_fixes": tool_suggest_fixes,
    "score_design": tool_score_design,
}


def call_tool(name: str, arguments: dict | None) -> dict:
    if name not in _DISPATCH:
        raise KeyError(name)
    return _DISPATCH[name](arguments or {})


def handle(message: dict) -> dict | None:
    """Answer one JSON-RPC message. Notifications return None."""
    method = message.get("method", "")
    mid = message.get("id")
    if method.startswith("notifications/") or ("id" not in message and method != "initialize"):
        return None
    if method == "initialize":
        return _result(mid, {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "lenszoo", "version": __version__},
        })
    if method == "ping":
        return _result(mid, {})
    if method == "tools/list":
        return _result(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        try:
            payload = call_tool(name, params.get("arguments") or {})
            text = json.dumps(payload, ensure_ascii=False)
            return _result(mid, {"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as exc:
            return _result(mid, {"content": [{"type": "text", "text": f"{exc.__class__.__name__}: {exc}"}], "isError": True})
    return _error(mid, -32601, f"Method not found: {method}")


def _result(mid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def read_message(stream) -> dict | None:
    headers: dict[bytes, bytes] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        if b":" in line:
            key, value = line.split(b":", 1)
            headers[key.strip().lower()] = value.strip()
    length = int(headers.get(b"content-length", b"0"))
    if length <= 0:
        return None
    body = stream.read(length)
    if len(body) < length:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(stream, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def serve(stdin=None, stdout=None) -> None:
    import warnings

    warnings.filterwarnings("ignore")
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    while True:
        message = read_message(stdin)
        if message is None:
            return
        reply = handle(message)
        if reply is not None:
            write_message(stdout, reply)

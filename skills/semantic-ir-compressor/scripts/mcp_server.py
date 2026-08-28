#!/usr/bin/env python3
"""Local stdio MCP for SemanticIR. No network. No shell. No ledger writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gate import gate  # noqa: E402

SKILL_URL = "https://github.com/dvdmrtnz15-afk/SkillAx/tree/main/skills/semantic-ir-compressor"
SKILL_RAW = "https://raw.githubusercontent.com/dvdmrtnz15-afk/SkillAx/main/skills/semantic-ir-compressor/SKILL.md"
CAPSULE_PATH = HERE.parent / "references" / "context-capsule.v1.json"
CAPSULE_URI = "semanticir://context-capsule/v1"

TOOLS = [
    {
        "name": "gate_fragment",
        "description": "Admit or reject a SemanticIR fragment. Deterministic. Does not write Notion or Linear.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "idea": {"type": "string"},
                "next_action": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "residual": {"type": "string"},
                "source_type": {"type": "string"},
                "source_url": {"type": "string"},
                "plane": {"type": "string"},
                "impact": {"type": "integer"},
            },
            "required": ["title", "idea", "next_action", "why_it_matters", "residual", "source_type", "plane"],
        },
    },
    {
        "name": "format_export",
        "description": "Render an admitted fragment as an AI export packet for Gmail subject AI export or Drive AI-Exports.",
        "inputSchema": {
            "type": "object",
            "properties": {"fragment": {"type": "object"}},
            "required": ["fragment"],
        },
    },
    {
        "name": "skill_pointer",
        "description": "Return the canonical SemanticIR skill URL and local path this MCP points at.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

RESOURCES = [
    {
        "uri": CAPSULE_URI,
        "name": "Federation context capsule v1",
        "mimeType": "application/json",
        "description": "Read-only ownership and input contract. Not live enterprise context.",
    }
]


def _ok(rid: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _text(payload: Any) -> dict[str, Any]:
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    return {"content": [{"type": "text", "text": body}]}


def _capsule() -> str:
    return CAPSULE_PATH.read_text(encoding="utf-8")


def format_export(frag: dict[str, Any]) -> str:
    url = (frag.get("source_url") or "").strip()
    residual = frag.get("residual", "")
    lines = [
        "AI export",
        f"Source: {frag.get('plane', '')}",
        f"Date: {frag.get('date', '')}".rstrip(),
        f"Title: {frag.get('title', '')}",
        f"Key idea: {frag.get('idea', '')}",
        f"Next action: {frag.get('next_action', '')}",
        f"Why it matters: {frag.get('why_it_matters', '')}",
        f"Residual: {residual}",
    ]
    if url:
        lines.append(f"Source URL: {url}")
    lines.append("Do not promote to Linear unless David says commit.")
    return "\n".join(lines)


def handle(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}
    if method == "initialize":
        return _ok(
            rid,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "semantic-ir-compressor", "version": "1.1.0"},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "resources/list":
        return _ok(rid, {"resources": RESOURCES})
    if method == "resources/read":
        uri = params.get("uri")
        if uri != CAPSULE_URI:
            return _err(rid, -32602, f"unknown resource {uri}")
        return _ok(
            rid,
            {"contents": [{"uri": CAPSULE_URI, "mimeType": "application/json", "text": _capsule()}]},
        )
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "skill_pointer":
            return _ok(
                rid,
                _text(
                    {
                        "skill": "semantic-ir-compressor",
                        "github": SKILL_URL,
                        "raw": SKILL_RAW,
                        "gate": "skills/semantic-ir-compressor/scripts/gate.py",
                        "capsule": CAPSULE_URI,
                        "live_context": "LYZT-AI",
                        "writes": "none",
                    }
                ),
            )
        if name == "gate_fragment":
            return _ok(rid, _text(gate(args)))
        if name == "format_export":
            frag = args.get("fragment") or args
            verdict = gate(frag)
            packet = format_export(frag)
            return _ok(rid, _text({"gate": verdict, "packet": packet}))
        return _err(rid, -32601, f"unknown tool {name}")
    if method == "ping":
        return _ok(rid, {})
    return _err(rid, -32601, f"unknown method {method}")


def main() -> int:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

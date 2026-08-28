#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path

SRV = Path(__file__).resolve().parent / "mcp_server.py"


def rpc(messages):
    raw = "".join(json.dumps(m) + "\n" for m in messages)
    out = subprocess.check_output([sys.executable, str(SRV)], input=raw, text=True)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def main() -> None:
    replies = rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
            {"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "semanticir://context-capsule/v1"}},
        ]
    )
    assert replies[0]["result"]["serverInfo"]["name"] == "semantic-ir-compressor"
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert names == {"gate_fragment", "format_export", "skill_pointer"}
    uris = {r["uri"] for r in replies[2]["result"]["resources"]}
    assert "semanticir://context-capsule/v1" in uris
    text = replies[3]["result"]["contents"][0]["text"]
    assert "SkillAx does not own live enterprise context" in text
    assert "LYZT-AI" in text
    print("ok")


if __name__ == "__main__":
    main()

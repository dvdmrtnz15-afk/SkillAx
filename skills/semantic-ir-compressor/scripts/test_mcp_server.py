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
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "skill_pointer", "arguments": {}}},
        ]
    )
    assert replies[0]["result"]["serverInfo"]["name"] == "semantic-ir-compressor"
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert names == {"gate_fragment", "format_export", "skill_pointer"}
    assert "SkillAx" in replies[2]["result"]["content"][0]["text"]
    print("ok")


if __name__ == "__main__":
    main()

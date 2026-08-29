#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path

from mcp_server import format_export

SRV = Path(__file__).resolve().parent / "mcp_server.py"

ADMITTED = {
    "title": "ProofKernel verifier",
    "idea": "The verifier accepted the exact-head fixture. The result remains bound to that reviewed commit.",
    "next_action": "Attach the receipt to the review record.",
    "why_it_matters": "The review needs evidence bound to the tested head.",
    "residual": "Independent review remains pending.",
    "source_type": "github",
    "source_url": "https://github.com/TrueNorthAppsCEO/ProofKernel/pull/38",
    "plane": "codex",
}

OUT_OF_LEASE = {
    **ADMITTED,
    "title": "Family legal filing",
    "idea": "Prepare the family court filing.",
    "next_action": "Submit the legal form.",
}

INCOMPLETE = {**ADMITTED, "next_action": ""}
NO_EVIDENCE = {
    **ADMITTED,
    "idea": "The latest cycle produced no world delta and no new exact-head evidence.",
}
AMPLIFIED = {
    **ADMITTED,
    "idea": "We shipped the verifier result without an independent receipt or reviewed provenance.",
}

REJECTED_FRAGMENTS = [
    (OUT_OF_LEASE, "out_of_lease"),
    (INCOMPLETE, "missing next_action"),
    (NO_EVIDENCE, "no-evidence pass"),
    (AMPLIFIED, "amplification in idea"),
]


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

    direct_admission = format_export(ADMITTED)
    assert direct_admission["status"] == "ADMITTED"
    assert "packet" in direct_admission
    for fragment, error in REJECTED_FRAGMENTS:
        direct_rejection = format_export(fragment)
        assert direct_rejection["status"] == "REJECTED"
        assert error in direct_rejection["gate"]["errors"]
        assert "packet" not in direct_rejection

    export_requests = [
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "format_export", "arguments": {"fragment": ADMITTED}},
        }
    ]
    export_requests.extend(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": "format_export", "arguments": {"fragment": fragment}},
        }
        for request_id, (fragment, _) in enumerate(REJECTED_FRAGMENTS, start=6)
    )
    export_replies = rpc(export_requests)
    admitted = json.loads(export_replies[0]["result"]["content"][0]["text"])
    assert admitted["status"] == "ADMITTED"
    assert admitted["gate"]["ok"] is True
    assert "packet" in admitted
    assert "ProofKernel verifier" in admitted["packet"]

    for reply, (_, error) in zip(export_replies[1:], REJECTED_FRAGMENTS):
        rejected = json.loads(reply["result"]["content"][0]["text"])
        assert rejected["status"] == "REJECTED"
        assert rejected["gate"]["ok"] is False
        assert error in rejected["gate"]["errors"]
        assert "packet" not in rejected
    print("ok")


if __name__ == "__main__":
    main()

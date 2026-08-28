# Local MCP

The communications layer for SemanticIR is a stdio MCP. It points at this skill. It does not write ledgers.

## Point

- Skill: https://github.com/dvdmrtnz15-afk/SkillAx/tree/main/skills/semantic-ir-compressor
- Server: `skills/semantic-ir-compressor/scripts/mcp_server.py`
- Tools: `gate_fragment`, `format_export`, `skill_pointer`
- Writes: none. Gmail subject `AI export` or Drive `AI-Exports` remains the ingest path.

## Claude / Codex / VS Code

Merge `mcp.json` from this skill into the client config. FounderLab Agent Hub remains the vault/handoff gateway. This server only admits fragments.

## FounderLab

Fabric registry capability `semantic_ir_mcp` points here. Do not register this as raw Ruflo. Do not add shell tools.

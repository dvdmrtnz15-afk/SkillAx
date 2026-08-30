"""Deterministic, audit-only causal realism evaluator."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List


def _graph(scene: Dict[str, Any]):
    nodes = {n["id"]: n for n in scene.get("nodes", [])}
    out = defaultdict(list)
    incoming = defaultdict(list)
    for edge in scene.get("edges", []):
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            continue
        a, b = edge
        out[a].append(b)
        incoming[b].append(a)
    return nodes, out, incoming


def _has_cycle(nodes, out) -> bool:
    state = {}

    def visit(node):
        if state.get(node) == 1:
            return True
        if state.get(node) == 2:
            return False
        state[node] = 1
        for child in out.get(node, []):
            if child in nodes and visit(child):
                return True
        state[node] = 2
        return False

    return any(visit(n) for n in nodes if state.get(n, 0) == 0)


def counterfactual_effects(scene: Dict[str, Any], removed_cause: str) -> List[str]:
    """Return downstream nodes whose state should change if a cause disappears."""
    nodes, out, _ = _graph(scene)
    if removed_cause not in nodes:
        return []
    seen = set()
    q = deque(out.get(removed_cause, []))
    while q:
        node = q.popleft()
        if node in seen:
            continue
        seen.add(node)
        q.extend(out.get(node, []))
    return sorted(seen)


def evaluate_scene(scene: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate causal coherence without granting effect authority."""
    nodes, out, incoming = _graph(scene)
    findings: List[str] = []

    for node_id, node in nodes.items():
        if node.get("kind") == "effect" and node.get("visible", False) and not incoming.get(node_id):
            findings.append(f"orphan_effect:{node_id}")

    if _has_cycle(nodes, out):
        findings.append("causal_cycle")

    opportunities = scene.get("opportunities")
    imperfections = scene.get("imperfections")
    if isinstance(opportunities, (int, float)) and opportunities > 0 and isinstance(imperfections, (int, float)):
        density = imperfections / opportunities
        if density < 0.10:
            findings.append("imperfection_budget:sterile")
        elif density > 0.65:
            findings.append("imperfection_budget:theatrical")

    findings = sorted(set(findings))
    return {
        "status": "ADMITTED" if not findings else "REJECTED",
        "findings": findings,
        "authority": "none",
        "effect_authority": "none",
    }

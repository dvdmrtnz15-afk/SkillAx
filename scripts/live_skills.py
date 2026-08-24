"""Single source of live public skills for ranker builders.

Filing (SA6 call) and routing membership live here.
Do not put class 900 private kernels or merged historical skills in LIVE.
Amend SA6 before inventing a new hundreds class.
"""

from __future__ import annotations

# name -> Dewey call (class.subclass.item)
LIVE: dict[str, str] = {
    "skillax": "000.10.01",
    "sovereign-control-plane": "100.00.01",
    "cinematic-narrative-engine": "200.00.01",
    "consultative-service-operations-os": "300.00.01",
    "constraint-based-planning-engine": "400.00.01",
    "structured-document-compliance-agent": "500.00.01",
    "persistent-character-world-system": "600.00.01",
    # human-adaptive-communication waits on SA6 class decision (no 700 product)
}

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384
RANKER_VERSION = "hybrid-rrf-1"
RRF_K = 60

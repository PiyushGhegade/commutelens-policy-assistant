"""Dense Chroma search, optionally fused with BM25 by reciprocal rank."""

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.models import Section
from app.store import PolicyStore, Snapshot

STOP = set(
    "a an the is are was were be been being i me my we our you your it its of on in at to for from and or can do does how what when who which please tell about policy company transport commute rule rules all with if have has get am as by this that under would could should will".split()
)


def tokens(text: str) -> list[str]:
    # BM25 uses only token normalisation, no case-specific synonym dictionary.
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


@dataclass(frozen=True)
class Hit:
    section: Section
    score: float


def retrieve(store: PolicyStore, snapshot: Snapshot, question: str, method="hybrid") -> list[Hit]:
    sections = {s.id: s for s in snapshot.policy.sections}
    collection = store.client.get_collection(snapshot.collection, embedding_function=None)
    result = collection.query(
        query_embeddings=store.embed([question]),
        n_results=min(6, len(sections)),
        where={"$and": [{"company": snapshot.company}, {"version": snapshot.policy.version}]},
        include=["metadatas", "distances"],
    )
    # Check metadata again before exposing any content to the LLM.
    dense = []
    similarities = {}
    for sid, metadata, distance in zip(result["ids"][0], result["metadatas"][0], result["distances"][0]):
        if (
            metadata["company"] != snapshot.company
            or metadata["version"] != snapshot.policy.version
            or sid not in sections
        ):
            raise RuntimeError("Retrieval scope violation")
        dense.append(sid)
        similarities[sid] = 1 - distance
    if method == "dense":
        return [Hit(sections[sid], similarities[sid]) for sid in dense[:3]]

    ids = list(sections)
    corpus = [tokens(f"{s.title} {s.text}") for s in sections.values()]
    scores = BM25Okapi(corpus).get_scores(tokens(question))
    lexical = sorted(
        [sid for sid, score in zip(ids, scores) if score > 0], key=lambda sid: -scores[ids.index(sid)]
    )
    fused = {}
    for ranking in (dense, lexical):
        for rank, sid in enumerate(ranking, 1):
            fused[sid] = fused.get(sid, 0) + 1 / (60 + rank)
    ranked = sorted(fused, key=lambda sid: -fused[sid])[:3]
    return [Hit(sections[sid], fused[sid]) for sid in ranked]

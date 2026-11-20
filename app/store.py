"""Immutable Chroma revisions + one atomic SQLite active-revision pointer."""

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

from app.models import Policy


class PolicyConflict(Exception):
    pass


class UnsafeDocument(Exception):
    pass


# Admission defence, not a claim to recognise every possible prompt injection.
INSTRUCTION = re.compile(
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|system)|"
    r"system\s*prompt|developer\s*message|reveal\s+.*(secret|token|key)|"
    r"\b(assistant|chatbot|llm)\s*(must|should|:)|"
    r"<\s*/?\s*(system|assistant)\b|override\s+.*(instruction|policy)",
    re.I,
)


@dataclass(frozen=True)
class Snapshot:
    company: str
    collection: str
    policy: Policy


class HashEmbedding:
    """Deterministic, download-free test double. Never used for the real benchmark."""

    def __call__(self, texts):
        import hashlib
        import math

        vectors = []
        for text in texts:
            vector = [0.0] * 384
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                number = int(hashlib.sha256(word.encode()).hexdigest()[:8], 16)
                vector[number % 384] += 1
            norm = math.sqrt(sum(n * n for n in vector)) or 1
            vectors.append([n / norm for n in vector])
        return vectors


class LocalMiniLM(ONNXMiniLM_L6_V2):
    """The same pretrained model, with bounded CPU threads for a small local demo."""

    @cached_property
    def model(self):
        options = self.ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        options.graph_optimization_level = self.ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        return self.ort.InferenceSession(
            str(Path(self.DOWNLOAD_PATH) / self.EXTRACTED_FOLDER_NAME / "model.onnx"),
            providers=["CPUExecutionProvider"],
            sess_options=options,
        )


class PolicyStore:
    def __init__(self, path: Path, embedding_model="minilm"):
        path.mkdir(parents=True, exist_ok=True)
        self.db_path = path / "registry.sqlite3"
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS active_policy (
                company TEXT PRIMARY KEY, collection TEXT NOT NULL,
                version INTEGER NOT NULL, policy_json TEXT NOT NULL)""")
        self.client = chromadb.PersistentClient(
            path=str(path / "chroma"),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        if embedding_model not in {"minilm", "hash-test"}:
            raise ValueError("Unknown embedding model")
        self.embed = LocalMiniLM() if embedding_model == "minilm" else HashEmbedding()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db_path, timeout=0.05)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def active(self, company: str) -> Snapshot | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM active_policy WHERE company=?", (company,)).fetchone()
        return (
            Snapshot(company, row["collection"], Policy.model_validate_json(row["policy_json"]))
            if row
            else None
        )

    def is_current(self, snapshot: Snapshot) -> bool:
        current = self.active(snapshot.company)
        return current is not None and current.collection == snapshot.collection

    def ingest(self, company: str, policy: Policy) -> Snapshot:
        # Reject an entire suspicious document before touching the live pointer.
        if INSTRUCTION.search(policy.model_dump_json()):
            raise UnsafeDocument("Document contains assistant-directed instructions.")
        current = self.active(company)
        if current and policy.version <= current.policy.version:
            raise PolicyConflict("Publish a version greater than the current version.")
        name = f"policy-{company}-{uuid4().hex}"
        collection = self.client.create_collection(
            name,
            embedding_function=None,
            # Policies contain at most 40 sections. Persist each write rather than
            # leaving a tiny index below Chroma's default 1000-record sync threshold.
            configuration={
                "hnsw": {"space": "cosine", "batch_size": 1, "sync_threshold": 1, "num_threads": 2}
            },
        )
        # A crash here may leave an unreachable staging collection. It never becomes active.
        texts = [f"{s.title}. {s.text}" for s in policy.sections]
        try:
            embeddings = self.embed(texts)
            collection.add(
                ids=[s.id for s in policy.sections],
                documents=texts,
                embeddings=embeddings,
                metadatas=[{"company": company, "version": policy.version} for _ in texts],
            )
            if collection.count() != len(texts):
                raise RuntimeError("Incomplete staging index")
            # A count alone does not prove that the vector index can be read.
            probe = collection.query(
                query_embeddings=embeddings[:1],
                n_results=len(texts),
                where={"$and": [{"company": company}, {"version": policy.version}]},
            )
            if set(probe["ids"][0]) != {s.id for s in policy.sections}:
                raise RuntimeError("Staging index is not readable in full")
            # Concurrent publishers re-check under the writer lock. Versions never go backwards.
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                old = db.execute("SELECT version FROM active_policy WHERE company=?", (company,)).fetchone()
                if old and old["version"] >= policy.version:
                    raise PolicyConflict("A newer or equal version is already active.")
                db.execute(
                    """INSERT INTO active_policy VALUES (?, ?, ?, ?)
                    ON CONFLICT(company) DO UPDATE SET collection=excluded.collection,
                    version=excluded.version, policy_json=excluded.policy_json""",
                    (company, name, policy.version, policy.model_dump_json()),
                )
            return Snapshot(company, name, policy)
        except Exception:
            try:
                self.client.delete_collection(name)
            except Exception:
                pass  # Orphan cleanup is optional; inactive revisions are never queried.
            raise

    def seed(self, folder: Path):
        for file in sorted(folder.glob("*.json")):
            company = file.stem
            if self.active(company) is None:
                self.ingest(company, Policy.model_validate_json(file.read_text(encoding="utf-8")))

    def close(self):
        self.client.close()

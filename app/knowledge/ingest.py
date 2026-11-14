"""Explicit offline publication; unchanged complete documents require no inference."""

from pathlib import Path

from langchain_core.embeddings import Embeddings

from app.knowledge.chunking import prepare_document, read_manifest, token_count
from app.knowledge.repository import KnowledgeRepository


class KnowledgeIngestor:
    def __init__(
        self,
        repository: KnowledgeRepository,
        embeddings: Embeddings,
        profile: str,
        batch_size: int = 1,
    ):
        self.repository = repository
        self.embeddings = embeddings
        self.profile = profile
        self.batch_size = batch_size

    async def ingest(self, root: Path, manifest: Path):
        documents = [
            prepare_document(root, entry, self.profile) for entry in read_manifest(root, manifest)
        ]
        if sum(len(d.chunks) for d in documents) > 1000:
            raise ValueError("Import exceeds 1000 chunks")
        if sum(token_count(c.embedding_text) for d in documents for c in d.chunks) > 100000:
            raise ValueError("Import exceeds 100000 input tokens")
        result = {"published": [], "unchanged": [], "embedding_batches": 0}
        for document in documents:
            if await self.repository.is_complete(document):
                result["unchanged"].append(document.entry.document_id)
                continue
            vectors = []
            for start in range(0, len(document.chunks), self.batch_size):
                batch = document.chunks[start : start + self.batch_size]
                values = await self.embeddings.aembed_documents([c.embedding_text for c in batch])
                vectors.extend(values)
                result["embedding_batches"] += 1
            changed = await self.repository.replace(document, vectors)
            result["published" if changed else "unchanged"].append(document.entry.document_id)
        return result

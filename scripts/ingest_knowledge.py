"""Explicit offline import/remove. Uses existing configured targets; never seeds business data."""

import argparse
from pathlib import Path

from app.core.config import Settings
from app.infrastructure.postgres import open_pool, validate_test_target
from app.knowledge.embedding import create_embeddings
from app.knowledge.ingest import KnowledgeIngestor
from app.knowledge.repository import KnowledgeRepository
from scripts import run_async


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=["test", "development"])
    parser.add_argument("--root", type=Path, default=Path("data/knowledge"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest", type=Path)
    group.add_argument("--remove", help="Explicit single document ID")
    args = parser.parse_args()
    settings = Settings()
    if args.target == "test":
        if settings.test_database_url is None:
            raise ValueError("Test database URL required")
        validate_test_target(settings.test_database_url, settings.database_url)
        settings = settings.model_copy(update={"database_url": settings.test_database_url})
    pool = await open_pool(settings)
    embeddings = None
    try:
        repository = KnowledgeRepository(pool)
        if args.remove:
            await repository.remove(args.remove)
            print("Specified document removed")
        else:
            embeddings = create_embeddings(settings)
            await embeddings.initialize()
            result = await KnowledgeIngestor(
                repository, embeddings, embeddings.profile.key, settings.embedding_batch_size
            ).ingest(args.root, args.manifest)
            print(result)
    finally:
        if embeddings:
            await embeddings.aclose()
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(run_async(main()))

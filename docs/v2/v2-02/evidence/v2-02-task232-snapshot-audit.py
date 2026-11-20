"""Compare the stored pre-run hash with the current snapshot adjusted only for watermark."""

import json
from pathlib import Path

from app.core.config import Settings
from app.infrastructure.postgres import open_pool
from scripts import run_async
from scripts.verify_05_memory_manage import database_snapshot, fingerprints


async def main():
    record = json.loads(
        Path("docs/v2/v2-02/evidence/v2-02-task232-full-regression.json").read_text()
    )
    settings = Settings()
    settings = settings.model_copy(update={"database_url": settings.test_database_url})
    pool = await open_pool(settings)
    try:
        current = await database_snapshot(pool)
    finally:
        await pool.close()
    rows, columns = current["knowledge_index_state"]
    assert len(rows) == 1
    text = rows[0][0]
    after = record["watermark_after"]
    before = record["watermark_before"]
    needle = f'"watermark":{after}'
    assert text.count(needle) == 1
    restored = text.replace(needle, f'"watermark":{before}')
    current["knowledge_index_state"] = ([(restored,)], columns)
    comparison = fingerprints(current)
    matches = {key: comparison[key] == value for key, value in record["protected_before"].items()}
    print(
        json.dumps(
            {
                "all_rows_and_columns_match_with_watermark_restored": all(matches.values()),
                "mismatches": [key for key, match in matches.items() if not match],
                "before_watermark": before,
                "after_watermark": after,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    run_async(main())

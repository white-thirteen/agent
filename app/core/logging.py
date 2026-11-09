"""Standard logging configuration; never log complete settings or secrets."""

import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from app.infrastructure.postgres import SafePoolLogFilter

    for name in ("psycopg.pool", "psycopg"):
        resource_logger = logging.getLogger(name)
        if not any(isinstance(item, SafePoolLogFilter) for item in resource_logger.filters):
            resource_logger.addFilter(SafePoolLogFilter())
    # HTTP debug logs can include provider URLs and transport details.
    for name in ("httpx", "httpcore", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)

"""CLI entry point — `python -m backend init` or `python -m backend serve`."""

import sys
import logging

from backend.config import settings
from backend.database.db import init_db

logger = logging.getLogger(__name__)


def main() -> None:
    """Route CLI subcommands."""
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python -m backend {init|serve}")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        logger.info("Initializing database at %s", settings.DB_PATH)
        init_db(settings.DB_PATH)
        logger.info("Done — %s created", settings.DB_PATH)

    elif command == "serve":
        import uvicorn

        logger.info("Starting VERTEX server (DATA_MODE=%s)", settings.DATA_MODE)
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level=settings.LOG_LEVEL.lower(),
        )

    else:
        print(f"Unknown command: {command}")
        print("Usage: python -m backend {init|serve}")
        sys.exit(1)


if __name__ == "__main__":
    main()

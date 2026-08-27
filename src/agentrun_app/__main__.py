from __future__ import annotations

import uvicorn

from .app import create_app
from .config import Settings
from .logging_config import configure_logging


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        host=settings.bind_host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()


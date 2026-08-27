from __future__ import annotations

from .config import Settings
from .logging_config import configure_logging


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    if settings.agent_name == "policy":
        from .agents.policy import create_policy_app

        return create_policy_app(settings)
    if settings.agent_name == "research":
        from .agents.research import create_research_app

        return create_research_app(settings)
    if settings.agent_name == "provider":
        from .agents.provider import create_provider_app

        return create_provider_app(settings)
    if settings.agent_name == "concierge":
        from .agents.concierge import create_concierge_app

        return create_concierge_app(settings)
    raise AssertionError(f"Unsupported agent: {settings.agent_name}")


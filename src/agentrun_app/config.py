from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


VALID_AGENTS = frozenset({"policy", "research", "provider", "concierge"})


def _clean_base_url(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid public URL: {value!r}")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = int(raw)
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    agent_name: str
    bind_host: str
    port: int
    public_base_url: str | None
    log_level: str
    data_dir: Path
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_anthropic_base_url: str
    policy_a2a_url: str | None
    research_a2a_url: str | None
    provider_a2a_url: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        agent_name = os.getenv("AGENT_NAME", "policy").strip().lower()
        if agent_name not in VALID_AGENTS:
            valid = ", ".join(sorted(VALID_AGENTS))
            raise ValueError(f"AGENT_NAME must be one of: {valid}")

        return cls(
            agent_name=agent_name,
            bind_host=os.getenv("AGENT_BIND_HOST", "0.0.0.0"),
            port=_env_int("AGENT_PORT", 9000),
            public_base_url=_clean_base_url(os.getenv("PUBLIC_BASE_URL")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            data_dir=Path(os.getenv("DATA_DIR", "/app/data")),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_anthropic_base_url=os.getenv(
                "DEEPSEEK_ANTHROPIC_BASE_URL",
                "https://api.deepseek.com/anthropic",
            ).rstrip("/"),
            policy_a2a_url=_clean_base_url(os.getenv("POLICY_A2A_URL")),
            research_a2a_url=_clean_base_url(os.getenv("RESEARCH_A2A_URL")),
            provider_a2a_url=_clean_base_url(os.getenv("PROVIDER_A2A_URL")),
        )

    def missing_required_environment(self) -> list[str]:
        missing: list[str] = []
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if self.agent_name == "concierge":
            for name, value in (
                ("POLICY_A2A_URL", self.policy_a2a_url),
                ("RESEARCH_A2A_URL", self.research_a2a_url),
                ("PROVIDER_A2A_URL", self.provider_a2a_url),
            ):
                if not value:
                    missing.append(name)
        return missing


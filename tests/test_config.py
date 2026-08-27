from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agentrun_app.config import Settings, _clean_base_url  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_public_url_is_normalized(self) -> None:
        self.assertEqual(
            _clean_base_url("https://example.com/a2a/"),
            "https://example.com/a2a",
        )

    def test_invalid_public_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _clean_base_url("example.com/no-scheme")

    def test_concierge_reports_missing_dependencies(self) -> None:
        environment = {
            "AGENT_NAME": "concierge",
            "AGENT_PORT": "9000",
            "DATA_DIR": str(PROJECT_ROOT.parent / "a2a" / "demo" / "data"),
        }
        with patch.dict(os.environ, environment, clear=True):
            missing = Settings.from_env().missing_required_environment()
        self.assertEqual(
            missing,
            [
                "DEEPSEEK_API_KEY",
                "POLICY_A2A_URL",
                "RESEARCH_A2A_URL",
                "PROVIDER_A2A_URL",
            ],
        )

    def test_unknown_agent_is_rejected(self) -> None:
        with patch.dict(os.environ, {"AGENT_NAME": "unknown"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()


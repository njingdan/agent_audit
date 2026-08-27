from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from ..a2a_server import build_a2a_app
from ..config import Settings
from ..telemetry import agent_span


LOGGER = logging.getLogger(__name__)


def _openai_compatible_url(base_url: str) -> str:
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


class ProviderService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        data_path = Path(settings.data_dir) / "doctors.json"
        self._doctors: list[dict] = json.loads(data_path.read_text(encoding="utf-8"))
        self._graph = None

        @tool
        def list_doctors(state: str = "", city: str = "", specialty: str = "") -> list[dict]:
            """按州、城市和专科查找医生；参数大小写不敏感。"""
            state_value = state.strip().lower()
            city_value = city.strip().lower()
            specialty_value = specialty.strip().lower()
            if not any((state_value, city_value, specialty_value)):
                return [{"error": "请至少提供state、city或specialty中的一个查询条件。"}]
            matches = [
                doctor
                for doctor in self._doctors
                if (not state_value or doctor["address"]["state"].lower() == state_value)
                and (not city_value or doctor["address"]["city"].lower() == city_value)
                and (not specialty_value or specialty_value in doctor["specialty"].lower())
            ]
            return matches or [{"message": "未找到匹配的医生。"}]

        self._list_doctors = list_doctors

    def _get_graph(self):
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        if self._graph is None:
            self._graph = create_agent(
                model=ChatOpenAI(
                    model="deepseek-chat",
                    api_key=self.settings.deepseek_api_key,
                    base_url=_openai_compatible_url(self.settings.deepseek_base_url),
                    max_tokens=1000,
                    temperature=0.2,
                ),
                tools=[self._list_doctors],
                name="HealthcareProviderAgent",
                system_prompt=(
                    "你是医疗服务查找助手。必须使用list_doctors工具查找医生，"
                    "只输出工具结果中存在的信息，不得编造。使用中文回答。"
                ),
            )
        return self._graph

    def answer(self, prompt: str) -> str:
        result = self._get_graph().invoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
        messages = result.get("messages", [])
        if not messages:
            return "未获得有效回答。"
        content = messages[-1].content
        return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


class ProviderExecutor(AgentExecutor):
    def __init__(self, service: ProviderService) -> None:
        self.service = service

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        with agent_span("provider", "execute"):
            try:
                result = await asyncio.to_thread(self.service.answer, context.get_user_input())
            except Exception:
                LOGGER.exception("Provider agent execution failed")
                raise
            await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        LOGGER.info("Provider agent cancellation requested")


def create_provider_app(settings: Settings):
    card = AgentCard(
        name="HealthcareProviderAgent",
        description="根据州、城市和专科查找医疗服务提供者。",
        url=settings.public_base_url or "http://localhost:9000/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="find_healthcare_providers",
                name="查找医疗服务提供者",
                description="根据州、城市和专科查找医生。",
                tags=["healthcare", "providers", "doctor"],
                examples=["Austin有精神科医生吗？", "查找Atlanta的心脏科医生。"],
            )
        ],
    )
    return build_a2a_app(
        settings=settings,
        agent_card=card,
        executor=ProviderExecutor(ProviderService(settings)),
    )


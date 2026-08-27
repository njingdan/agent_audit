from __future__ import annotations

import asyncio
import logging

import httpx
from a2a.client import A2ACardResolver
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message
from beeai_framework.adapters.a2a.agents import A2AAgent
from beeai_framework.adapters.openai import OpenAIChatModel
from beeai_framework.agents.requirement import RequirementAgent
from beeai_framework.memory import UnconstrainedMemory
from beeai_framework.tools.handoff import HandoffTool
from beeai_framework.tools.think import ThinkTool

from ..a2a_server import build_a2a_app
from ..config import Settings
from ..telemetry import agent_span


LOGGER = logging.getLogger(__name__)


def _openai_compatible_url(base_url: str) -> str:
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


class ConciergeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._agent: RequirementAgent | None = None
        self._initialization_lock = asyncio.Lock()

    @property
    def initialized(self) -> bool:
        return self._agent is not None

    async def _load_remote_agent_card(
        self,
        http_client: httpx.AsyncClient,
        dependency_name: str,
        url: str,
    ) -> AgentCard:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.a2a_discovery_max_attempts + 1):
            try:
                card = await A2ACardResolver(http_client, url).get_agent_card()
                LOGGER.info(
                    "Loaded downstream Agent Card dependency=%s attempt=%d",
                    dependency_name,
                    attempt,
                )
                return card
            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "Failed to load downstream Agent Card dependency=%s attempt=%d/%d: %s",
                    dependency_name,
                    attempt,
                    self.settings.a2a_discovery_max_attempts,
                    exc,
                )
                if attempt < self.settings.a2a_discovery_max_attempts:
                    await asyncio.sleep(
                        self.settings.a2a_discovery_backoff_seconds * (2 ** (attempt - 1))
                    )

        raise RuntimeError(
            "Unable to load downstream Agent Card "
            f"dependency={dependency_name} after "
            f"{self.settings.a2a_discovery_max_attempts} attempts"
        ) from last_error

    async def _get_agent(self) -> RequirementAgent:
        if self._agent is not None:
            return self._agent
        async with self._initialization_lock:
            if self._agent is not None:
                return self._agent
            missing = self.settings.missing_required_environment()
            if missing:
                raise RuntimeError(f"Missing required environment: {', '.join(missing)}")

            dependencies = (
                ("policy", self.settings.policy_a2a_url),
                ("research", self.settings.research_a2a_url),
                ("provider", self.settings.provider_a2a_url),
            )
            timeout = httpx.Timeout(
                connect=30.0,
                read=self.settings.a2a_discovery_timeout_seconds,
                write=30.0,
                pool=30.0,
            )
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http_client:
                cards = await asyncio.gather(
                    *(
                        self._load_remote_agent_card(http_client, name, url)
                        for name, url in dependencies
                        if url is not None
                    )
                )

            policy_agent, research_agent, provider_agent = (
                A2AAgent(agent_card=card, memory=UnconstrainedMemory()) for card in cards
            )

            self._agent = RequirementAgent(
                name="HealthcareConciergeAgent",
                description="协调保险、健康研究和医生查找Agent。",
                llm=OpenAIChatModel(
                    model_id="deepseek-chat",
                    api_key=self.settings.deepseek_api_key,
                    base_url=_openai_compatible_url(self.settings.deepseek_base_url),
                    allow_parallel_tool_calls=True,
                    tool_choice_support={"auto", "none", "required"},
                ),
                tools=[
                    ThinkTool(),
                    HandoffTool(
                        target=policy_agent,
                        name=policy_agent.name,
                        description=policy_agent.agent_card.description,
                    ),
                    HandoffTool(
                        target=research_agent,
                        name=research_agent.name,
                        description=research_agent.agent_card.description,
                    ),
                    HandoffTool(
                        target=provider_agent,
                        name=provider_agent.name,
                        description=provider_agent.agent_card.description,
                    ),
                ],
                role="Healthcare Concierge",
                instructions=(
                    "根据问题将任务交给保险、健康研究或医生查找Agent。"
                    "收到下游结果后先分析是否完整，再汇总中文回答。"
                    "不得编造下游没有返回的信息，不得提供医疗诊断。"
                ),
            )
            LOGGER.info("Concierge dependencies initialized")
            return self._agent

    async def answer(self, prompt: str) -> str:
        response = await (await self._get_agent()).run(prompt)
        if response.last_message:
            return response.last_message.text
        return "未获得有效回答。"


class ConciergeExecutor(AgentExecutor):
    def __init__(self, service: ConciergeService) -> None:
        self.service = service

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        with agent_span("concierge", "execute"):
            try:
                result = await self.service.answer(context.get_user_input())
            except Exception:
                LOGGER.exception("Concierge agent execution failed")
                raise
            await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        LOGGER.info("Concierge agent cancellation requested")


def create_concierge_app(settings: Settings):
    service = ConciergeService(settings)
    card = AgentCard(
        name="HealthcareConciergeAgent",
        description="协调保险政策、健康研究和医生查找Agent，为用户汇总回答。",
        url=settings.public_base_url or "http://localhost:9000/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="healthcare_concierge",
                name="健康服务协调",
                description="把复合健康问题分派给专业Agent并汇总结果。",
                tags=["healthcare", "orchestration", "a2a"],
                examples=["说明糖尿病症状、保险覆盖，并找Austin附近的医生。"],
            )
        ],
    )
    return build_a2a_app(
        settings=settings,
        agent_card=card,
        executor=ConciergeExecutor(service),
        dependency_probe=lambda: {"ready": True, "initialized": service.initialized},
    )

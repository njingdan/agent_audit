from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message
from openai import OpenAI

from ..a2a_server import build_a2a_app
from ..config import Settings
from ..telemetry import agent_span


LOGGER = logging.getLogger(__name__)


class PolicyService:
    SYSTEM_PROMPT = (
        "你是专业的保险政策顾问。只能依据给定的保险计划文档回答；"
        "文档没有的信息必须明确说明。使用中文，避免提供医疗诊断。"
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: OpenAI | None = None
        policy_path = Path(settings.data_dir) / "policy.txt"
        self._policy_text = policy_path.read_text(encoding="utf-8")

    def _get_client(self) -> OpenAI:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
            )
        return self._client

    def answer(self, prompt: str) -> str:
        response = self._get_client().chat.completions.create(
            model="deepseek-chat",
            max_tokens=1024,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": f"{self.SYSTEM_PROMPT}\n\n--- 保险计划文档 ---\n{self._policy_text}",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or "未获得有效回答。"


class PolicyExecutor(AgentExecutor):
    def __init__(self, service: PolicyService) -> None:
        self.service = service

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        with agent_span("policy", "execute"):
            try:
                result = await asyncio.to_thread(self.service.answer, context.get_user_input())
            except Exception:
                LOGGER.exception("Policy agent execution failed")
                raise
            await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        LOGGER.info("Policy agent cancellation requested")


def create_policy_app(settings: Settings):
    card = AgentCard(
        name="InsurancePolicyCoverageAgent",
        description="依据保险计划文档回答覆盖范围、共付额、免赔额和网络信息。",
        url=settings.public_base_url or "http://localhost:9000/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="insurance_coverage",
                name="保险覆盖查询",
                description="查询健康保险计划的覆盖范围、费用和网络信息。",
                tags=["insurance", "coverage", "policy"],
                examples=["年度体检有共付额吗？", "心理咨询是否在保险范围内？"],
            )
        ],
    )
    return build_a2a_app(
        settings=settings,
        agent_card=card,
        executor=PolicyExecutor(PolicyService(settings)),
    )


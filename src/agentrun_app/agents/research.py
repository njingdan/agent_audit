from __future__ import annotations

import asyncio
import logging
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message
from anthropic import Anthropic

from ..a2a_server import build_a2a_app
from ..config import Settings
from ..telemetry import agent_span


LOGGER = logging.getLogger(__name__)

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "搜索公开网页中的健康信息，返回标题、摘要和来源链接。",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "搜索关键词"}},
        "required": ["query"],
    },
}


def web_search(query: str) -> str:
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))
    if not results:
        return "未找到相关公开资料。"
    return "\n\n".join(
        f"{index}. {item.get('title', '')}\n"
        f"   {item.get('body', '')}\n"
        f"   来源: {item.get('href', 'N/A')}"
        for index, item in enumerate(results, 1)
    )


class ResearchService:
    SYSTEM_PROMPT = (
        "你是健康信息研究助手。优先使用web_search获取公开信息并引用来源。"
        "你不能诊断或替代医生；涉及紧急情况时建议立即就医。使用中文回答。"
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Anthropic | None = None

    def _get_client(self) -> Anthropic:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        if self._client is None:
            self._client = Anthropic(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_anthropic_base_url,
            )
        return self._client

    def answer(self, prompt: str) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        for _ in range(5):
            response = self._get_client().messages.create(
                model="deepseek-v4-flash",
                max_tokens=1024,
                system=self.SYSTEM_PROMPT,
                messages=messages,
                tools=[WEB_SEARCH_TOOL],
            )
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if response.stop_reason == "tool_use" and tool_uses:
                tool_results = []
                for block in tool_uses:
                    result = web_search(**block.input) if block.name == "web_search" else "未知工具"
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            text = [block.text for block in response.content if block.type == "text"]
            return text[0] if text else "未获得有效回答。"
        raise RuntimeError("Research agent exceeded the maximum tool-call rounds")


class ResearchExecutor(AgentExecutor):
    def __init__(self, service: ResearchService) -> None:
        self.service = service

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        with agent_span("research", "execute"):
            try:
                result = await asyncio.to_thread(self.service.answer, context.get_user_input())
            except Exception:
                LOGGER.exception("Research agent execution failed")
                raise
            await event_queue.enqueue_event(new_agent_text_message(result))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        LOGGER.info("Research agent cancellation requested")


def create_research_app(settings: Settings):
    card = AgentCard(
        name="HealthResearchAgent",
        description="搜索公开资料，回答症状、疾病、治疗方法和健康程序相关问题。",
        url=settings.public_base_url or "http://localhost:9000/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="health_research",
                name="健康信息研究",
                description="搜索和汇总有来源的公开健康信息。",
                tags=["health", "research", "medical"],
                examples=["糖尿病有哪些常见症状？", "高血压防治指南有哪些更新？"],
            )
        ],
    )
    return build_a2a_app(
        settings=settings,
        agent_card=card,
        executor=ResearchExecutor(ResearchService(settings)),
    )


from __future__ import annotations

from collections.abc import Callable

from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .config import Settings


def _external_base_url(request: Request, configured: str | None) -> str:
    if configured:
        return configured.rstrip("/")

    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    host = host.split(",", 1)[0].strip()
    prefix = request.headers.get("x-forwarded-prefix", "").split(",", 1)[0].strip()
    if prefix and not prefix.startswith("/"):
        prefix = f"/{prefix}"
    return f"{proto}://{host}{prefix}".rstrip("/")


def _card_payload(card: AgentCard, public_url: str) -> dict:
    if hasattr(card, "model_copy"):
        current = card.model_copy(update={"url": f"{public_url}/"})
        return current.model_dump(mode="json", by_alias=True, exclude_none=True)
    current = card.copy(update={"url": f"{public_url}/"})
    return current.dict(by_alias=True, exclude_none=True)


def build_a2a_app(
    *,
    settings: Settings,
    agent_card: AgentCard,
    executor: AgentExecutor,
    dependency_probe: Callable[[], dict[str, object]] | None = None,
):
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    ).build()

    async def agent_card_route(request: Request) -> JSONResponse:
        base_url = _external_base_url(request, settings.public_base_url)
        return JSONResponse(_card_payload(agent_card, base_url))

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "agent": settings.agent_name,
                "version": agent_card.version,
            }
        )

    async def readiness(_: Request) -> JSONResponse:
        missing = settings.missing_required_environment()
        details = dependency_probe() if dependency_probe else {}
        ready = not missing and details.get("ready", True) is not False
        payload: dict[str, object] = {
            "status": "ready" if ready else "not_ready",
            "agent": settings.agent_name,
            "missing_environment": missing,
            "dependencies": details,
        }
        return JSONResponse(payload, status_code=200 if ready else 503)

    # Insert the dynamic card route before the SDK's static route. This keeps
    # Agent Card URLs correct behind AgentRun's endpoint proxy.
    app.router.routes.insert(
        0,
        Route("/.well-known/agent-card.json", agent_card_route, methods=["GET"]),
    )
    app.router.routes.insert(1, Route("/healthz", health, methods=["GET"]))
    app.router.routes.insert(2, Route("/readyz", readiness, methods=["GET"]))
    return app


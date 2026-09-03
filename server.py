import os
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

PATH_TOKEN = os.getenv("MCP_PATH_TOKEN", "dev-only-token")
BASE_URL = "https://api.browser-use.com/api/v3"

mcp = FastMCP(
    "Browser Use Remote",
    instructions=(
        "Use these tools to control a Browser Use cloud browser. "
        "Never submit irreversible forms, purchases, account deletions, or job applications "
        "without explicit user confirmation immediately before the final submission action. "
        "Do not expose API keys or secrets in outputs."
    ),
    stateless_http=True,
    json_response=True,
)


def _headers() -> dict[str, str]:
    key = os.getenv("BROWSER_USE_API_KEY")
    if not key:
        raise RuntimeError("BROWSER_USE_API_KEY is not configured on the server")
    return {"X-Browser-Use-API-Key": key, "Content-Type": "application/json"}


async def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.request(method, BASE_URL + path, headers=_headers(), **kwargs)
        response.raise_for_status()
        return response.json()


@mcp.tool()
def health() -> str:
    """Return a simple health status for the MCP service."""
    return "ok"


@mcp.tool()
async def run_browser_task(
    task: str,
    model: str = "bu-max",
    start_url: str | None = None,
    max_steps: int = 100,
    keep_alive: bool = True,
    max_cost_usd: float | None = None,
    allowed_domains: list[str] | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Start a Browser Use cloud agent task and return its session ID and live browser URL."""
    payload: dict[str, Any] = {
        "task": task,
        "model": model,
        "keepAlive": keep_alive,
        "maxSteps": max_steps,
    }
    if start_url:
        payload["startUrl"] = start_url
    if max_cost_usd is not None:
        payload["maxCostUsd"] = max_cost_usd
    if allowed_domains:
        payload["allowedDomains"] = allowed_domains
    if profile_id:
        payload["profileId"] = profile_id
    return await _request("POST", "/sessions", json=payload)


@mcp.tool()
async def get_browser_session(session_id: str) -> dict[str, Any]:
    """Get Browser Use session status, progress, output, live URL, and recording URLs."""
    return await _request("GET", f"/sessions/{session_id}")


@mcp.tool()
async def send_browser_task(
    session_id: str,
    task: str,
    model: str | None = None,
    max_steps: int = 100,
) -> dict[str, Any]:
    """Send a follow-up task to an existing Browser Use session."""
    payload: dict[str, Any] = {"task": task, "maxSteps": max_steps}
    if model:
        payload["model"] = model
    return await _request("POST", f"/sessions/{session_id}", json=payload)


@mcp.tool()
async def stop_browser_session(session_id: str, strategy: str = "session") -> dict[str, Any]:
    """Stop the current Browser Use task or destroy its browser session."""
    if strategy not in {"task", "session"}:
        raise ValueError("strategy must be 'task' or 'session'")
    return await _request("POST", f"/sessions/{session_id}/stop", json={"strategy": strategy})


async def health_route(request):
    return JSONResponse({"status": "ok", "service": "browser-use-remote-mcp"})


mcp.settings.streamable_http_path = "/"
app = Starlette(
    routes=[
        Route("/health", health_route),
        Mount(f"/mcp/{PATH_TOKEN}", app=mcp.streamable_http_app()),
    ],
    lifespan=lambda app: mcp.session_manager.run(),
)

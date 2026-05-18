from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass

import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse

from .client import BalatroAgentApiError, BalatroAgentClient
from .server import create_server


@dataclass(frozen=True, slots=True)
class NetworkServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    path: str = "/mcp"
    transport: str = "streamable-http"
    api_base_url: str = "http://127.0.0.1:8080"
    log_level: str = "info"


def create_network_app(config: NetworkServerConfig):
    health_client = BalatroAgentClient(base_url=config.api_base_url, read_timeout=1.5, action_timeout=1.5, max_retries=0)
    server = create_server(client=BalatroAgentClient(base_url=config.api_base_url))
    app = server.http_app(path=config.path, transport=config.transport)

    async def root(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": "balatro-agent-network-mcp",
                "mcp_path": config.path,
                "transport": config.transport,
                "api_base_url": config.api_base_url,
            }
        )

    async def healthz(_: Request) -> JSONResponse:
        payload = {
            "ok": True,
            "service": "balatro-agent-network-mcp",
            "api_base_url": config.api_base_url,
        }
        try:
            payload["balatro_agent"] = health_client.get_health()
            return JSONResponse(payload, status_code=200)
        except BalatroAgentApiError as exc:
            payload["ok"] = False
            payload["error"] = {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "retryable": exc.retryable,
            }
            return JSONResponse(payload, status_code=503)

    app.add_route("/", root, methods=["GET"])
    app.add_route("/healthz", healthz, methods=["GET"])
    return app


async def run_network_server_async(config: NetworkServerConfig) -> None:
    app = create_network_app(config)
    uvicorn_config = uvicorn.Config(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level,
        timeout_graceful_shutdown=0,
        lifespan="on",
    )
    await uvicorn.Server(uvicorn_config).serve()


def parse_args(argv: list[str] | None = None) -> NetworkServerConfig:
    parser = argparse.ArgumentParser(description="Expose Balatro Agent MCP over HTTP.")
    parser.add_argument("--host", default=os.getenv("BALATRO_AGENT_NETWORK_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("BALATRO_AGENT_NETWORK_PORT", "8765")))
    parser.add_argument("--path", default=os.getenv("BALATRO_AGENT_NETWORK_PATH", "/mcp"))
    parser.add_argument("--transport", default=os.getenv("BALATRO_AGENT_NETWORK_TRANSPORT", "streamable-http"))
    parser.add_argument("--api-base-url", default=os.getenv("BALATRO_AGENT_API_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--log-level", default=os.getenv("BALATRO_AGENT_NETWORK_LOG_LEVEL", "info"))
    args = parser.parse_args(argv)
    return NetworkServerConfig(
        host=args.host,
        port=args.port,
        path=args.path,
        transport=args.transport,
        api_base_url=args.api_base_url,
        log_level=args.log_level,
    )


def main() -> None:
    asyncio.run(run_network_server_async(parse_args()))


if __name__ == "__main__":
    main()

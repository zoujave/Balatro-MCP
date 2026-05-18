from __future__ import annotations

import os
from typing import Any, Callable

from fastmcp import FastMCP

from .client import BalatroAgentClient

ToolHandler = Callable[..., dict[str, Any]]


def create_tool_handlers(client: Any) -> dict[str, Callable[..., Any]]:
    def health_check() -> dict[str, Any]:
        return client.get_health()

    def get_game_state() -> dict[str, Any]:
        return client.get_state()

    def get_raw_game_state() -> dict[str, Any]:
        return client.get_state()

    def get_available_actions() -> dict[str, Any]:
        return {"actions": client.get_available_actions()}

    def act(
        action: str,
        *,
        area: str | None = None,
        index: int | None = None,
        card_indices: list[int] | None = None,
        mode: str | None = None,
        seed: str | None = None,
        stake: int | None = None,
        blind: str | None = None,
    ) -> dict[str, Any]:
        return client.execute_action(
            action,
            area=area,
            index=index,
            card_indices=card_indices,
            mode=mode,
            seed=seed,
            stake=stake,
            blind=blind,
            client_context={"source": "mcp", "tool_name": "act"},
        )

    def wait_until_actionable(timeout: float = 30.0, poll_interval: float = 0.25) -> dict[str, Any]:
        return client.wait_until_actionable(timeout=timeout, poll_interval=poll_interval)

    return {
        "health_check": health_check,
        "get_game_state": get_game_state,
        "get_raw_game_state": get_raw_game_state,
        "get_available_actions": get_available_actions,
        "act": act,
        "wait_until_actionable": wait_until_actionable,
    }


def create_server(client: BalatroAgentClient | None = None) -> FastMCP:
    balatro = client or BalatroAgentClient()
    handlers = create_tool_handlers(balatro)
    mcp = FastMCP("Balatro Agent")

    @mcp.tool
    def health_check() -> dict[str, Any]:
        """Check whether the Balatro Agent mod is loaded and reachable."""
        return handlers["health_check"]()

    @mcp.tool
    def get_game_state() -> dict[str, Any]:
        """Read the current Balatro state snapshot."""
        return handlers["get_game_state"]()

    @mcp.tool
    def get_raw_game_state() -> dict[str, Any]:
        """Read the raw state snapshot for debugging or schema inspection."""
        return handlers["get_raw_game_state"]()

    @mcp.tool
    def get_available_actions() -> dict[str, Any]:
        """List legal actions for the current Balatro state."""
        return handlers["get_available_actions"]()

    @mcp.tool
    def act(
        action: str,
        area: str | None = None,
        index: int | None = None,
        card_indices: list[int] | None = None,
        mode: str | None = None,
        seed: str | None = None,
        stake: int | None = None,
        blind: str | None = None,
    ) -> dict[str, Any]:
        """Execute a Balatro action exposed by the local mod."""
        return handlers["act"](
            action,
            area=area,
            index=index,
            card_indices=card_indices,
            mode=mode,
            seed=seed,
            stake=stake,
            blind=blind,
        )

    @mcp.tool
    def wait_until_actionable(timeout: float = 30.0, poll_interval: float = 0.25) -> dict[str, Any]:
        """Poll game state until at least one legal action is available."""
        return handlers["wait_until_actionable"](timeout=timeout, poll_interval=poll_interval)

    return mcp


def main() -> None:
    server = create_server()
    transport = os.getenv("BALATRO_AGENT_MCP_TRANSPORT", "stdio")
    server.run(transport=transport)


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_READ_TIMEOUT = 10.0
DEFAULT_ACTION_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2


@dataclass(slots=True)
class BalatroAgentApiError(RuntimeError):
    status_code: int
    code: str
    message: str
    details: Any = None
    retryable: bool = False

    def __str__(self) -> str:
        parts = [f"{self.code}: {self.message}", f"http={self.status_code}"]
        if self.retryable:
            parts.append("retryable=true")
        if self.details is not None:
            parts.append(f"details={json.dumps(self.details, ensure_ascii=False)}")
        return " | ".join(parts)


class BalatroAgentClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        read_timeout: float | None = None,
        action_timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._base_url = (base_url or os.getenv("BALATRO_AGENT_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._read_timeout = read_timeout or float(os.getenv("BALATRO_AGENT_API_READ_TIMEOUT", str(DEFAULT_READ_TIMEOUT)))
        self._action_timeout = action_timeout or float(
            os.getenv("BALATRO_AGENT_API_ACTION_TIMEOUT", str(DEFAULT_ACTION_TIMEOUT))
        )
        self._max_retries = (
            max_retries if max_retries is not None else int(os.getenv("BALATRO_AGENT_API_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    def get_health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def get_state(self) -> dict[str, Any]:
        return self._request("GET", "/state")

    def get_available_actions(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/actions/available")
        return list(payload.get("actions", []))

    def execute_action(
        self,
        action: str,
        *,
        card_indices: list[int] | None = None,
        index: int | None = None,
        area: str | None = None,
        mode: str | None = None,
        seed: str | None = None,
        stake: int | None = None,
        blind: str | None = None,
        client_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/action",
            payload={
                "action": action,
                "card_indices": card_indices,
                "index": index,
                "area": area,
                "mode": mode,
                "seed": seed,
                "stake": stake,
                "blind": blind,
                "client_context": client_context,
            },
            is_action=True,
        )

    def wait_until_actionable(self, *, timeout: float = 30.0, poll_interval: float = 0.25) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last_state: dict[str, Any] = {}

        while time.monotonic() <= deadline:
            last_state = self.get_state()
            if last_state.get("actionable") or last_state.get("available_actions"):
                return last_state
            time.sleep(max(0.01, poll_interval))

        raise BalatroAgentApiError(
            status_code=0,
            code="timeout",
            message="Timed out waiting for Balatro to become actionable.",
            details={"timeout": timeout, "last_state": last_state},
            retryable=True,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        is_action: bool = False,
    ) -> Any:
        timeout = self._action_timeout if is_action else self._read_timeout
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        last_error: BalatroAgentApiError | None = None
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                time.sleep(0.2 * attempt)

            http_request = request.Request(
                url=f"{self._base_url}{path}",
                method=method,
                data=body,
                headers=headers,
            )

            try:
                with request.urlopen(http_request, timeout=timeout) as response:
                    return self._decode_response(200, response.read())
            except error.HTTPError as exc:
                last_error = self._build_api_error(exc.code, exc.read())
                if not last_error.retryable or attempt >= self._max_retries:
                    raise last_error
            except error.URLError as exc:
                last_error = BalatroAgentApiError(
                    status_code=0,
                    code="connection_error",
                    message=f"Cannot reach Balatro Agent at {self._base_url}.",
                    details={"reason": str(exc.reason), "path": path},
                    retryable=True,
                )
                if attempt >= self._max_retries:
                    raise last_error

        raise last_error or AssertionError("unreachable")

    @staticmethod
    def _decode_response(status_code: int, response_body: bytes) -> Any:
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise BalatroAgentApiError(
                status_code=status_code,
                code="invalid_response",
                message="Server returned invalid JSON.",
            ) from exc

        if not payload.get("ok", False):
            error_payload = payload.get("error", {})
            raise BalatroAgentApiError(
                status_code=status_code,
                code=error_payload.get("code", "unknown_error"),
                message=error_payload.get("message", "Request failed."),
                details=error_payload.get("details"),
                retryable=bool(error_payload.get("retryable", False)),
            )

        return payload.get("data")

    @classmethod
    def _build_api_error(cls, status_code: int, response_body: bytes) -> BalatroAgentApiError:
        try:
            cls._decode_response(status_code, response_body)
        except BalatroAgentApiError as exc:
            return exc

        return BalatroAgentApiError(
            status_code=status_code,
            code="unknown_error",
            message="Server returned an HTTP error without an error envelope.",
        )

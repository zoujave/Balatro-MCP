from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .catalog import GameCatalog

DEFAULTS = {"control_mode": "inherit", "strategy": {"objective": "win", "preserve_glass": True, "min_cash": 25,
            "horizon_rounds": 3}, "logging": {"enabled": True, "include_states": True}, "language": "zh_CN"}


@contextmanager
def journal_lock(path: Path):
    """Serialize large JSONL appends across independent MCP processes."""
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            def lock():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            def unlock():
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def lock(): fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            def unlock(): fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        deadline = time.monotonic() + 2
        while True:
            try:
                lock()
                break
            except OSError:
                if time.monotonic() >= deadline: raise
                time.sleep(.01)
        try: yield
        finally: unlock()


def validate_config(config: dict[str, Any]) -> None:
    if set(config) - set(DEFAULTS): raise ValueError("Unknown configuration option")
    if config.get("control_mode") not in {"inherit", "assist", "auto"}: raise ValueError("control_mode must be inherit, assist or auto")
    strategy = config.get("strategy", {})
    if set(strategy) - set(DEFAULTS["strategy"]): raise ValueError("Unknown strategy option")
    if strategy.get("objective") not in {"win", "endless", "record"}: raise ValueError("objective must be win, endless or record")
    if not isinstance(strategy.get("preserve_glass"), bool): raise ValueError("preserve_glass must be boolean")
    for key in ["min_cash", "horizon_rounds"]:
        value = strategy.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= (10000 if key == "min_cash" else 100):
            raise ValueError(f"Invalid strategy {key}")
    logging = config.get("logging", {})
    if set(logging) - set(DEFAULTS["logging"]) or any(not isinstance(v, bool) for v in logging.values()): raise ValueError("Invalid logging settings")
    if not isinstance(config.get("language"), str) or not config["language"]: raise ValueError("Invalid language")


def compact_state(state: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(state)
    result.pop("decks", None)
    result.pop("actions", None)
    for hand in result.get("run", {}).get("hand_levels", {}).values():
        for key in list(hand):
            if key not in {"level", "chips", "mult", "played", "l_chips", "l_mult"}: hand.pop(key, None)
    deck = result.get("deck", {})
    deck.pop("cards", None)
    observations = result.get("observations", {})
    last = observations.get("last_hand")
    if last:
        observations["last_hand"] = {k: v for k, v in last.items() if k not in {"reference_state", "trace", "cards"}}
    observations.pop("events", None)
    observations.pop("hands", None)
    return result


def state_token(state: dict[str, Any]) -> str:
    if state.get("revision"): return str(state["revision"])
    # Compatibility fallback for old Mods; server-side race protection requires the new Mod.
    value = {k: v for k, v in state.items() if k not in {"timestamp", "assistant", "decks", "actions"}}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


class AssistantRuntime:
    def __init__(self, config_path: Path | None = None, log_dir: Path | None = None, catalog: GameCatalog | None = None):
        root = Path(__file__).resolve().parents[3]
        self.config_path = Path(config_path or os.getenv("BALATRO_MCP_CONFIG") or root / "local/assistant-config.json")
        self.log_dir = Path(log_dir or os.getenv("BALATRO_MCP_LOG_DIR") or root / "local/logs")
        self.config = copy.deepcopy(DEFAULTS)
        self.warnings: list[str] = []
        self.last_state: dict[str, Any] | None = None
        self.seen_events: set[str] = set()
        self.seen_order: deque[str] = deque()
        self.hand_definitions: dict[str, Any] = {}
        self.instance_id = uuid.uuid4().hex
        self.lock = threading.RLock()
        if self.config_path.exists():
            # Invalid opt-in configuration is a startup error, not silently ignored.
            patch = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.configure(patch, persist=False)
        self.catalog = catalog or GameCatalog(language=self.config["language"])
        for item in self.history(1000, "game_event"):
            identity = str(item.get("game_event_id"))
            self.seen_events.add(identity)
            self.seen_order.append(identity)
        self.seen_hands = {x.get("hand_id") for x in self.history(1000, "hand_result")}
        self.hand_order = deque(self.seen_hands)

    def configure(self, patch: dict[str, Any], persist: bool = False) -> dict[str, Any]:
        with self.lock:
            proposed = copy.deepcopy(self.config)
            for key, value in patch.items():
                if key in {"strategy", "logging"} and isinstance(value, dict): proposed[key].update(value)
                else: proposed[key] = value
            validate_config(proposed)
            if persist:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.config_path.with_suffix(".tmp-" + self.instance_id)
                temporary.write_text(json.dumps(proposed, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(temporary, self.config_path)
            self.config = proposed
            return copy.deepcopy(self.config)

    def write(self, kind: str, **fields: Any) -> dict[str, Any]:
        entry = {"schema_version": 1, "id": uuid.uuid4().hex, "timestamp": datetime.now(timezone.utc).isoformat(),
                 "kind": kind, "server_instance": self.instance_id, **fields}
        if not self.config["logging"]["enabled"]: return entry
        try:
            with self.lock:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                path = self.log_dir / ("events-" + datetime.now(timezone.utc).strftime("%Y%m%d") + ".jsonl")
                with journal_lock(path.with_suffix(".lock")):
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError as exc:
            warning = f"Logging unavailable: {exc}"
            if warning not in self.warnings: self.warnings.append(warning)
        return entry

    def history(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        result: deque[dict[str, Any]] = deque(maxlen=limit)
        paths = sorted(self.log_dir.glob("events-*.jsonl")) if self.log_dir.exists() else []
        for path in paths[-7:]:
            try:
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        try: entry = json.loads(line)
                        except json.JSONDecodeError: continue  # Ignore an incomplete concurrent tail.
                        if kind is None or entry.get("kind") == kind: result.append(entry)
            except OSError: continue
        return list(reversed(result))

    def observe(self, state: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            snapshot = copy.deepcopy(state)
            areas = [snapshot.get(name, {}).get("cards", []) for name in ["hand", "jokers", "consumeables", "pack"]]
            areas.extend(snapshot.get("shop", {}).values())
            for cards in areas:
                for card in cards:
                    defaults = self.catalog.card(card.get("key", ""))
                    for key in ["rarity", "blueprint_compat", "set"]:
                        if card.get(key) is None and defaults.get(key) is not None: card[key] = defaults[key]
                    card["ability"] = {**defaults.get("ability", {}), **card.get("ability", {})}
            # Keep immutable scoring definitions after their first read; live levels remain in state.
            for key, value in snapshot.get("run", {}).get("hand_levels", {}).items():
                self.hand_definitions.setdefault(key, {k: v for k, v in value.items() if k in {"s_chips", "s_mult", "l_chips", "l_mult", "order"}})
            if self.last_state is None or state_token(self.last_state) != state_token(snapshot):
                fields = {"run_id": snapshot.get("run_id"), "revision": state_token(snapshot), "screen": snapshot.get("screen"),
                          "changed_sections": [k for k in snapshot if k != "timestamp" and (self.last_state or {}).get(k) != snapshot[k]]}
                if self.config["logging"]["include_states"]: fields["state"] = compact_state(snapshot)
                self.write("state_changed", **fields)
            for event in snapshot.get("observations", {}).get("events", []):
                identity = str(event.get("id"))
                if identity not in self.seen_events:
                    # Dedupe events across MCP restarts as well as repeated polling.
                    self.write("game_event", game_event_id=identity, run_id=snapshot.get("run_id"), event=event)
                    self.seen_events.add(identity)
                    self.seen_order.append(identity)
            while len(self.seen_order) > 2048: self.seen_events.discard(self.seen_order.popleft())
            observations = snapshot.get("observations", {})
            last = observations.get("last_hand") or {}
            hands = [h for h in observations.get("hands", []) if h.get("id") != last.get("id")]
            if last: hands.append(last)
            for hand in hands:
                if hand.get("complete") and hand.get("id") not in self.seen_hands:
                    self.write("hand_result", hand_id=hand.get("id"), run_id=hand.get("run_id") or snapshot.get("run_id"), hand=hand)
                    self.seen_hands.add(hand.get("id"))
                    self.hand_order.append(hand.get("id"))
            while len(self.hand_order) > 2048: self.seen_hands.discard(self.hand_order.popleft())
            self.last_state = snapshot
            snapshot["assistant"] = {"strategy": copy.deepcopy(self.config["strategy"]), "control_mode_override": self.config["control_mode"],
                                     "catalog": self.catalog.status, "warnings": self.warnings,
                                     "cached_hand_definitions": len(self.hand_definitions)}
            return snapshot

    def record_action(self, tool: str, action: str, params: dict[str, Any], before: dict[str, Any], result: Any = None,
                      error: Exception | None = None, elapsed_ms: float = 0) -> dict[str, Any]:
        fields = {"tool": tool, "action": action, "params": params, "run_id": before.get("run_id"),
                  "before_revision": state_token(before), "elapsed_ms": round(elapsed_ms, 2), "success": error is None,
                  "strategy": copy.deepcopy(self.config["strategy"])}
        if error is not None: fields["error"] = {"type": type(error).__name__, "message": str(error)}
        else: fields["result"] = result
        if self.config["logging"]["include_states"]: fields["before"] = compact_state(before)
        return self.write("action", **fields)

    def watch(self, client: Any, after_revision: str | None = None, timeout: float = 25, poll_interval: float = .25) -> dict[str, Any]:
        if not 0 <= timeout <= 60 or not .1 <= poll_interval <= 5: raise ValueError("timeout must be 0..60 seconds and poll_interval .1..5")
        previous = copy.deepcopy(self.last_state)
        state = self.observe(client.get_state())
        token = after_revision or state_token(state)
        deadline = time.monotonic() + timeout
        while state_token(state) == token and time.monotonic() < deadline:
            time.sleep(min(poll_interval, max(0, deadline - time.monotonic())))
            state = self.observe(client.get_state())
        changed = state_token(state) != token
        return {"changed": changed, "revision": state_token(state), "state": compact_state(state),
                "changed_sections": [k for k in state if k not in {"timestamp", "assistant"} and (previous or {}).get(k) != state[k]] if changed else []}

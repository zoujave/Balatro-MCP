"""Read game data afresh at server startup, without executing extracted Lua."""
from __future__ import annotations

import hashlib
import os
import re
import zipfile
from pathlib import Path
from typing import Any


class LuaDataReader:
    """Parser for the literal-table subset used by Balatro localization/config."""

    def __init__(self, text: str, offset: int = 0):
        self.text, self.pos = text, offset

    def skip(self) -> None:
        while True:
            match = re.match(r"\s+|--\[\[.*?\]\]|--[^\n]*", self.text[self.pos:], re.S)
            if not match:
                return
            self.pos += match.end()

    def take(self, value: str) -> None:
        self.skip()
        if not self.text.startswith(value, self.pos):
            raise ValueError(f"Expected {value!r} at {self.pos}")
        self.pos += len(value)

    def value(self) -> Any:
        self.skip()
        char = self.text[self.pos:self.pos + 1]
        if char == "{":
            return self.table()
        if char in {"'", '"'}:
            quote, output = char, []
            self.pos += 1
            while self.pos < len(self.text):
                char = self.text[self.pos]
                self.pos += 1
                if char == quote:
                    return "".join(output)
                if char == "\\":
                    char = self.text[self.pos]
                    self.pos += 1
                    char = {"n": "\n", "r": "\r", "t": "\t"}.get(char, char)
                output.append(char)
            raise ValueError("Unterminated Lua string")
        number = re.match(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", self.text[self.pos:])
        if number:
            self.pos += number.end()
            return float(number[0]) if any(c in number[0] for c in ".eE") else int(number[0])
        word = re.match(r"[A-Za-z_]\w*", self.text[self.pos:])
        if word and word[0] in {"true", "false", "nil"}:
            self.pos += word.end()
            return {"true": True, "false": False, "nil": None}[word[0]]
        raise ValueError(f"Nonliteral Lua data at {self.pos}")

    def table(self) -> Any:
        self.take("{")
        result: dict[Any, Any] = {}
        sequence, named = 1, False
        while True:
            self.skip()
            if self.text[self.pos:self.pos + 1] == "}":
                self.pos += 1
                return result if named else [result[i] for i in range(1, sequence)]
            key = None
            if self.text[self.pos:self.pos + 1] == "[":
                self.take("[")
                key = self.value()
                self.take("]")
                self.take("=")
            else:
                word = re.match(r"([A-Za-z_]\w*)\s*=", self.text[self.pos:])
                if word:
                    key = word[1]
                    self.pos += word.end()
            if key is None:
                key, sequence = sequence, sequence + 1
            else:
                named = True
            result[key] = self.value()
            self.skip()
            if self.text[self.pos:self.pos + 1] in {",", ";"}:
                self.pos += 1
            elif self.text[self.pos:self.pos + 1] != "}":
                raise ValueError(f"Expected table separator at {self.pos}")


class GameCatalog:
    def __init__(self, game_path: str | Path | None = None, language: str = "zh_CN"):
        self.entries: dict[str, dict[str, Any]] = {}
        self.centers: dict[str, dict[str, Any]] = {}
        self.misc: dict[str, Any] = {}
        self.scoring_sources: dict[str, str] | None = None
        self.status: dict[str, Any] = {"loaded": False, "language": language, "warnings": []}
        path = Path(game_path or os.getenv("BALATRO_MCP_GAME_PATH") or r"D:\SteamLibrary\steamapps\common\Balatro\Balatro.exe")
        if path.is_dir():
            path = path / "Balatro.exe"
        self.path = path
        try:
            with zipfile.ZipFile(path) as archive:
                member = f"localization/{language}.lua"
                if member not in archive.namelist():
                    member = "localization/en-us.lua"
                    self.status["language"] = "en-us"
                source = archive.read(member).decode("utf-8-sig")
                start = re.search(r"\breturn\s*\{", source)
                if not start:
                    raise ValueError("Localization has no literal return table")
                localization = LuaDataReader(source, source.index("{", start.start())).value()
                for category, entries in localization.get("descriptions", {}).items():
                    for key, entry in entries.items():
                        self.entries[key] = {"set": category, **entry}
                self.misc = localization.get("misc", {})
                definitions = archive.read("game.lua").decode("utf-8")
                for match in re.finditer(r"\b((?:j|m|c|v|b|p)_[a-z0-9_]+)\s*=\s*\{", definitions):
                    try:
                        center = LuaDataReader(definitions, match.end() - 1).value()
                        if isinstance(center, dict) and "set" in center:
                            self.centers[match[1]] = center
                    except (ValueError, IndexError):
                        continue
                self.status.update(loaded=True, entries=len(self.entries), centers=len(self.centers),
                                   source=member, content_sha256=hashlib.sha256(source.encode()).hexdigest())
        except (OSError, zipfile.BadZipFile, KeyError, ValueError, IndexError, AttributeError) as exc:
            self.status["warnings"].append(f"Game catalog unavailable: {type(exc).__name__}: {exc}")

    def scoring_data(self) -> dict[str, Any]:
        """Read source and definitions into memory once on the first scoring request."""
        if self.scoring_sources is None:
            self.scoring_sources = {}
            try:
                with zipfile.ZipFile(self.path) as archive:
                    for member in ["card.lua", "functions/state_events.lua", "functions/common_events.lua"]:
                        self.scoring_sources[member] = archive.read(member).decode("utf-8")
            except (OSError, zipfile.BadZipFile, KeyError) as exc:
                self.status["warnings"].append(f"Scoring source unavailable: {exc}")
        return {"cached_in_memory": True, "files": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in self.scoring_sources.items()},
                "definitions": len(self.centers), "execution": "Extracted game Lua is never executed by score previews"}

    def card(self, key: str) -> dict[str, Any]:
        center = self.centers.get(key, {})
        config = center.get("config", {})
        if not isinstance(config, dict):
            config = {}
        ability = {"name": center.get("name"), "set": center.get("set"), **config}
        if "Xmult" in ability:
            ability["x_mult"] = ability["Xmult"]
        return {"key": key, "name": center.get("name"), "set": center.get("set"),
                "rarity": center.get("rarity"), "cost": center.get("cost"), "ability": ability,
                "blueprint_compat": center.get("blueprint_compat")}

    def describe(self, key: str, card: dict[str, Any] | None = None, state: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = self.entries.get(key)
        if entry is None:
            return {"key": key, "available": False, "catalog": self.status}
        card, state = card or self.card(key), state or {}
        ability = card.get("ability", {})
        extra = ability.get("extra")
        deck = state.get("deck", {})
        normal = state.get("run", {}).get("probabilities", {}).get("normal", 1)
        variables: list[Any] = []
        if key == "j_blackboard":
            suits = self.misc.get("suits_plural", {})
            variables = [extra, suits.get("Spades", "Spades"), suits.get("Clubs", "Clubs")]
        elif key == "j_erosion" and deck.get("total") is not None:
            starting = deck.get("starting_size", 52)
            variables = [extra, max(0, (starting - deck["total"]) * (extra or 0)), starting]
        elif key in {"j_constellation", "j_campfire", "j_hologram", "j_lucky_cat"}:
            variables = [extra, ability.get("x_mult", ability.get("Xmult", 1))]
        elif key == "j_rocket" and isinstance(extra, dict):
            variables = [extra.get("dollars"), extra.get("increase")]
        elif key == "m_glass":
            variables = [ability.get("x_mult", ability.get("Xmult", 2)), normal, extra or 4]
        elif key == "m_steel":
            variables = [ability.get("h_x_mult", ability.get("h_Xmult", 1.5))]
        elif key in {"m_bonus", "m_stone"}:
            variables = [ability.get("bonus", 30 if key == "m_bonus" else 50)]
        elif key == "m_mult":
            variables = [ability.get("mult", 4)]
        elif key == "j_joker":
            variables = [ability.get("mult", 4)]
        elif isinstance(extra, (int, float)):
            variables = [extra]
        text = entry.get("text", [])
        if isinstance(text, dict):
            text = list(text.values())
        unresolved = set()
        def substitute(match: re.Match[str]) -> str:
            index = int(match[1]) - 1
            if 0 <= index < len(variables) and variables[index] is not None:
                value = variables[index]
                return f"{value:g}" if isinstance(value, (float, int)) else str(value)
            unresolved.add(index + 1)
            return match[0]
        lines = [re.sub(r"#(\d+)#", substitute, re.sub(r"\{[^{}]*\}", "", line)) for line in text]
        return {"key": key, "available": True, "name": entry.get("name"), "set": entry.get("set"),
                "description": lines, "variables": variables, "unresolved_variables": sorted(unresolved),
                "current_ability": ability, "rarity": card.get("rarity"), "language": self.status["language"],
                "source": "game_archive", "template": text}

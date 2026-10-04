"""Compare supported previews against recorded outcomes without connecting to the game."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from balatro_mcp.analysis import preview_hand
from balatro_mcp.catalog import GameCatalog


def replay(path: Path, game_path: str | None = None) -> dict:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    catalog = GameCatalog(game_path)
    comparisons, skipped = [], []
    for index, record in enumerate(records):
        # Supports the original helper's gameplay data; new journals retain game hand events directly.
        if record.get("request", {}).get("tool") != "play_hand" or not index:
            continue
        before, after = copy.deepcopy(records[index - 1].get("state", {})), record.get("state", {})
        if before.get("screen") != "SELECTING_HAND" or before.get("run", {}).get("round") != after.get("run", {}).get("round"):
            skipped.append({"line": index + 1, "reason": "No comparable before/after hand"})
            continue
        for card in before.get("jokers", {}).get("cards", []):
            center = catalog.card(card.get("key", ""))
            if card.get("rarity") is None: card["rarity"] = center.get("rarity")
        actual = after.get("run", {}).get("chips", 0) - before.get("run", {}).get("chips", 0)
        try:
            prediction = preview_hand(before, record["request"].get("args", {}).get("card_indices"))
        except ValueError as exc:
            skipped.append({"line": index + 1, "reason": str(exc)})
            continue
        if prediction.get("status") != "supported" or actual <= 0:
            skipped.append({"line": index + 1, "reason": prediction.get("unsupported_effects") or "Outcome has not settled"})
            continue
        comparisons.append({"line": index + 1, "hand_type": prediction["hand_type"],
                            "predicted": prediction["score"], "actual": actual, "matches": prediction["score"] == actual})
    return {"compared": len(comparisons), "matched": sum(row["matches"] for row in comparisons),
            "comparisons": comparisons, "skipped": skipped, "catalog": catalog.status}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--game-path")
    args = parser.parse_args()
    result = replay(args.log, args.game_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["matched"] != result["compared"] else 0)

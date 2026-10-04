"""Save a read-only game snapshot for reproducing MCP issues."""
from __future__ import annotations
import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    snapshot = {"captured_at": datetime.now().astimezone().isoformat()}
    for name, route in (("health", "/health"), ("state", "/state"), ("actions", "/actions/available")):
        with urlopen(args.api_base_url.rstrip("/") + route, timeout=10) as response:
            snapshot[name] = json.load(response)
    output_dir = Path(__file__).resolve().parents[1] / "local" / "captures"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)

if __name__ == "__main__":
    main()

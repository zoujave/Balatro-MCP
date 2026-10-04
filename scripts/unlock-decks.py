"""Unlock only normal deck flags in a backed-up Balatro profile (Windows)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime
import zipfile
import zlib


def read_save(data: bytes) -> str:
    return (data if data.startswith(b"return") else zlib.decompress(data, -15)).decode("utf-8")


def pack_save(text: str) -> bytes:
    compressor = zlib.compressobj(level=1, wbits=-15)
    return compressor.compress(text.encode("utf-8")) + compressor.flush()


def unlock_save_text(text: str, deck_keys: list[str]) -> tuple[str, list[str]]:
    matches = list(re.finditer(r'\["unlocked"\]\s*=\s*\{([^{}]*)\}', text))
    if len(matches) != 1:
        raise ValueError("Expected exactly one flat unlocked table; refusing to edit this save format")
    match = matches[0]
    block = match.group(1)
    changed = []
    for key in deck_keys:
        if not re.fullmatch(r"b_[a-z0-9_]+", key):
            raise ValueError("Unexpected deck key")
        entry = re.compile(r'\["' + re.escape(key) + r'"\]\s*=\s*(true|false)(?=\s*(?:,|$))')
        existing = list(entry.finditer(block))
        assigned = re.findall(r'\["' + re.escape(key) + r'"\]\s*=', block)
        if len(assigned) != len(existing):
            raise ValueError("Non-boolean deck flag; refusing to edit")
        if len(existing) > 1:
            raise ValueError("Duplicate deck flag; refusing to edit")
        if existing and existing[0].group(1) == "true":
            continue
        if existing:
            flag = existing[0]
            block = block[:flag.start(1)] + "true" + block[flag.end(1):]
        else:
            if block.strip() and not block.rstrip().endswith(","):
                block += ","
            block += '["' + key + '"]=true,'
        changed.append(key)
    result = text[:match.start(1)] + block + text[match.end(1):]
    if read_save(pack_save(result)) != result:
        raise ValueError("Save compression round-trip failed")
    return result, changed


def normal_decks(game_exe: Path) -> list[str]:
    with zipfile.ZipFile(game_exe) as archive:
        source = archive.read("game.lua").decode("utf-8")
    keys = []
    for line in source.splitlines():
        match = re.match(r"\s*(b_\w+)\s*=", line)
        if match and 'set = "Back"' in line and "omit = true" not in line:
            keys.append(match.group(1))
    if len(keys) != 15 or len(set(keys)) != 15:
        raise ValueError("Expected the 15 normal Balatro decks; inspect the installed game version first")
    return keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-exe", type=Path, default=Path(r"D:\SteamLibrary\steamapps\common\Balatro\Balatro.exe"))
    parser.add_argument("--profile", type=int, required=True, choices=(1, 2, 3))
    parser.add_argument("--apply", action="store_true", help="Write the deck flags after backing up the profile. Close Balatro first.")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This helper targets the Windows Balatro save directory")
    save_root = Path(os.environ["APPDATA"]) / "Balatro"
    profile_dir = save_root / str(args.profile)
    path = profile_dir / "meta.jkr"
    before = path.read_bytes()
    original = read_save(before)
    keys = normal_decks(args.game_exe)
    updated, changed = unlock_save_text(original, keys)
    print(json.dumps({"profile": args.profile, "decks_total": len(keys), "flags_to_unlock": changed, "apply": args.apply}, ensure_ascii=False))
    if not args.apply or not changed:
        return
    processes = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Balatro.exe", "/FO", "CSV", "/NH"], capture_output=True, check=True)
    if b"balatro.exe" in processes.stdout.lower():
        parser.error("Balatro is running. Close it normally before editing the save.")
    backup = Path(__file__).resolve().parents[1] / "local" / "backups" / ("deck-unlock-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    backup.mkdir(parents=True)
    shutil.copytree(profile_dir, backup / str(args.profile))
    if (save_root / "settings.jkr").exists():
        shutil.copy2(save_root / "settings.jkr", backup / "settings.jkr")
    if path.read_bytes() != before:
        raise RuntimeError("Save changed during preparation; refusing to overwrite it")
    after = pack_save(updated)
    temporary = path.with_name("meta.jkr.deck-unlock-tmp")
    temporary.write_bytes(after)
    if read_save(temporary.read_bytes()) != updated:
        raise RuntimeError("Written save failed verification")
    temporary.replace(path)
    report = {"profile": args.profile, "changed": changed, "meta_before_sha256": hashlib.sha256(before).hexdigest(), "meta_after_sha256": hashlib.sha256(after).hexdigest()}
    (backup / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Backup:", backup)
    print("Saved only deck unlock flags. Restart Balatro to verify all decks are available.")


if __name__ == "__main__":
    main()

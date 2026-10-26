#!/usr/bin/env python3
"""Install a local checkout into Magpie. No existing home is connected."""
import json
import os
from pathlib import Path
import shutil
import sys

source = Path(__file__).resolve().parent
sys.path.insert(0, str(source/"multicodex"))
from runtime import atomic, read_json, save_json

config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config")))/"magpie"
destination = config/"local-plugins/magpie-multicodex"
destination.mkdir(parents=True, exist_ok=True, mode=0o700)
for name in ("index.mjs", "package.json", "README.md", "README.zh-CN.md", "LICENSE"):
    atomic(destination/name, (source/name).read_text())
for name in ("multicodex", "page", "vendor"):
    for file in (source/name).rglob("*"):
        if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
            atomic(destination/file.relative_to(source), file.read_text())
registry = read_json(config/"plugins.json", {"plugins": []})
if not any(p.get("spec") == str(destination) for p in registry["plugins"]):
    registry["plugins"].append({"spec": str(destination)})
save_json(config/"plugins.json", registry)
print("Installed CXI for Magpie. Open CXI for Magpie in Magpie's sidebar.")

#!/usr/bin/env python3
"""Bundle a checked-out cxi release; keep the upstream license with it."""
import argparse
import hashlib
import json
from pathlib import Path
import re

parser=argparse.ArgumentParser()
parser.add_argument("source",type=Path)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
version=re.search(r"^CXI_VERSION=(\S+)",(args.source/"cxi-core.sh").read_text()).group(1)
target=root/"vendor/cxi";target.mkdir(parents=True,exist_ok=True)
hashes={}
for name in ("cxi-core.sh","cxi.bash","cxi.zsh","LICENSE"):
    data=(args.source/name).read_bytes();(target/name).write_bytes(data)
    hashes[name]=hashlib.sha256(data).hexdigest()
(target/"upstream.json").write_text(json.dumps({"repository":"https://github.com/SevenFo/cxi","version":version,"sha256":hashes},indent=2)+"\n")
print("Bundled cxi "+version)

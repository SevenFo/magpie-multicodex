#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import sys
import tarfile

root = Path(__file__).resolve().parents[1]
package = json.loads((root/"package.json").read_text())
version = package["version"]
if len(sys.argv) > 1 and sys.argv[1] != "v"+version:
    raise SystemExit("Tag does not match package.json")
destination = root/"dist"
destination.mkdir(exist_ok=True)
archive = destination/(package["name"]+"-"+version+".tar.gz")
def public_metadata(info):
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.pax_headers = {}
    return info

with tarfile.open(archive, "w:gz") as tar:
    for name in dict.fromkeys(["package.json", "install.py", *package["files"]]):
        path = root/name
        if path.is_file():
            tar.add(path, arcname=package["name"]+"/"+name, filter=public_metadata)
        elif path.is_dir():
            for file in sorted(path.rglob("*")):
                if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                    tar.add(file, arcname=package["name"]+"/"+str(file.relative_to(root)), filter=public_metadata)
(destination/"SHA256SUMS").write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+"  "+archive.name+"\n")
print("Built MultiCodex "+version)

"""Install the bundled upstream cxi, without a second package download."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from runtime import atomic, regular


def install(package):
    if os.environ.get("MULTICODEX_NO_LAUNCHER") == "1":
        return
    vendor=package/"vendor/cxi"
    metadata=json.loads((vendor/"upstream.json").read_text())
    prefix=Path(os.environ.get("XDG_DATA_HOME",str(Path.home()/".local/share")))/"cxi"
    if not prefix.is_absolute() or prefix.is_symlink():raise ValueError("Invalid cxi installation directory")
    release=prefix/"releases"/metadata["version"]
    for name,digest in metadata["sha256"].items():
        data=(vendor/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError("Bundled cxi checksum mismatch")
        atomic(release/name,data.decode())
    for shell in ("bash","zsh"):
        atomic(prefix/("cxi."+shell),"source "+shlex.quote(str(release/("cxi."+shell)))+"\n")
    binary=Path.home()/".local/bin/cxi"
    regular(binary)
    if not binary.exists() or "# cxi-managed" in binary.read_text():
        atomic(binary,'#!/bin/bash\n# cxi-managed\nsource '+shlex.quote(str(prefix/"cxi.bash"))+' || exit $?\ncxi "$@"\n',0o700)
    for shell in ("bash","zsh"):
        rc=(Path(os.environ.get("ZDOTDIR",str(Path.home())))/".zshrc") if shell=="zsh" else Path.home()/".bashrc"
        if rc.is_symlink() or (rc.exists() and not rc.is_file()):continue
        line="source "+shlex.quote(str(prefix/("cxi."+shell)))
        text=rc.read_text() if rc.exists() else ""
        if line in text.splitlines():continue
        if rc.exists():
            backup=prefix/"shell-backups"/(rc.name+"-"+str(time.time_ns()))
            atomic(backup,text)
        atomic(rc,text+("" if not text or text.endswith("\n") else "\n")+line+"\n")


def alias_for(entry):
    name=entry["name"]
    reserved=set("default new add ls list run login path env rm delete remote help version".split())
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}",name) and name not in reserved:return name
    return "home-"+entry["id"].rsplit("-",1)[-1][:10]


def register_alias(package,entry):
    root=Path(os.environ.get("CXI_ROOT",str(Path.home()/".codex-instances")))
    if os.environ.get("MULTICODEX_NO_LAUNCHER")=="1" and not os.environ.get("CXI_ROOT"):
        return alias_for(entry)
    alias=alias_for(entry)
    command='source "$1" || exit $?; cxi add "$2" "$3"'
    result=subprocess.run(["bash","--noprofile","--norc","-c",command,"multicodex",str(package/"vendor/cxi/cxi.bash"),alias,entry["home"]],
        env={**os.environ,"CXI_ROOT":str(root)},capture_output=True,text=True,timeout=10)
    if result.returncode:raise ValueError(result.stderr.strip() or "Could not register cxi name")
    return alias


def remove_alias(entry):
    root=Path(os.environ.get("CXI_ROOT",str(Path.home()/".codex-instances")))
    path=root/".aliases"/entry.get("alias",alias_for(entry))
    if path.is_file() and not path.is_symlink() and path.read_text().strip()==entry["home"]:path.unlink()

#!/usr/bin/env python3
"""MultiCodex backend and optional CLI. State lives in Magpie's config dir."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request

from runtime import atomic, read_json, regular, save_json
from cxi_bundle import install as install_cxi, register_alias, remove_alias

PACKAGE = Path(__file__).resolve().parents[1]
BEGIN, END = "# >>> multicodex >>>", "# <<< multicodex <<<"


def config_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config")))/"magpie"


def clean_environment(text):
    for start, end in ((BEGIN, END), ("# >>> magpie-cxi instance adapter >>>", "# <<< magpie-cxi instance adapter <<<")):
        if text.count(start) != text.count(end) or text.count(start) > 1:
            raise ValueError("Malformed instance launcher block")
        if start in text:
            a, b = text.index(start), text.index(end)+len(end)
            if b < len(text) and text[b] == "\n":
                b += 1
            text = text[:a]+text[b:]
    return text


def home_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or any(c in str(path) for c in "\n\r\0"):
        raise ValueError("CODEX_HOME must be an absolute path")
    path = path.resolve()
    if path in (Path("/"), Path.home().resolve(), (Path.home()/".codex").resolve()):
        raise ValueError("The default Codex home is kept separate; choose another directory")
    if path.exists() and not path.is_dir():
        raise ValueError("CODEX_HOME is not a directory")
    return path


def display_name(value):
    name = str(value).strip()
    if not name or len(name) > 60 or any(ord(c) < 32 for c in name):
        raise ValueError("Use a name between 1 and 60 characters")
    return name


class Controller:
    def __init__(self, config=None, package=None):
        self.config = Path(config or config_dir()).resolve()
        self.package = Path(package or PACKAGE).resolve()
        self.db_path = self.config/"multicodex/state.json"
        self.registry_path = self.config/"plugins.json"
        self.db = read_json(self.db_path, {"version": 1, "instances": [], "receipts": {}})

    def save(self):
        save_json(self.db_path, self.db)

    def registry(self):
        return read_json(self.registry_path, {"plugins": []})

    def own_entry(self, registry):
        candidates = [p for p in registry["plugins"] if not p.get("off") and
            (p.get("spec") == str(self.package) or "magpie-multicodex" in p.get("spec", ""))]
        exact = next((p for p in candidates if p["spec"] == str(self.package)), None)
        if exact:
            return exact
        if len(candidates) != 1:
            raise ValueError("Install one active MultiCodex plugin")
        installed = Path(candidates[0]["spec"])
        if installed.is_absolute() and installed.resolve() != self.package:
            raise ValueError("This MultiCodex watcher was replaced by another package")
        return candidates[0]

    def adopt(self):
        if self.db_path.exists():
            return
        # Adopt a previous generic cxi adapter, preserving its agent identity,
        # selected model and per-home Magpie stash. No provider is imported.
        for plugin in self.registry()["plugins"]:
            target = Path(plugin["spec"])
            if not target.is_absolute() or "magpie-cxi" not in str(target):
                continue
            metadata = read_json(target/"instance.json", {})
            if not metadata.get("instance") or not (target/"agent.mjs").exists():
                continue
            match = re.search(r"export const agent = (\{.*\});", (target/"agent.mjs").read_text())
            if not match:
                continue
            desc = json.loads(match.group(1))
            home = home_path(metadata["instance"])
            state = read_json(Path(desc["config"]), {})
            entry = {"id": desc["id"], "name": home.name, "home": str(home),
                "state": desc["config"], "adapter": str(target), "lastModel": state.get("model", "")}
            self.db["instances"].append(entry)
            self.write_adapter(entry)
        self.save()

    def install_launcher(self):
        install_cxi(self.package)

    def write_adapter(self, entry):
        home, target, state = Path(entry["home"]), Path(entry["adapter"]), Path(entry["state"])
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        environment = home/"cxi.env"
        regular(environment)
        prior = clean_environment(environment.read_text() if environment.exists() else "")
        entry["alias"] = register_alias(self.package, entry)
        runtime = self.config/"multicodex/runtime"
        for name in ("runtime.py", "hook.sh"):
            atomic(runtime/name, (self.package/"multicodex"/name).read_text())
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        def relocatable(path):
            try:
                return "~/" + path.relative_to(Path.home()).as_posix()
            except ValueError:
                # Magpie declines previews for folders outside the user's home.
                return str(path)
        descriptor = {"id": entry["id"], "name": "Codex · "+entry["name"], "bin": "codex",
            "config": relocatable(state), "format": "json", "model": "model", "dir": relocatable(home),
            "notice": "Restart this instance to use the new selection."}
        source = "export const agent = "+json.dumps(descriptor, ensure_ascii=False)+";\n"
        source += 'export function connect({gateway}) { return {schema:1,baseURL:gateway.url.replace(/\\/+$/, "")+"/backend-api/codex",apiKey:gateway.key}; }\n'
        atomic(target/"agent.mjs", source)
        save_json(target/"package.json", {"name": "multicodex-agent-"+entry["id"], "version": "0.2.0", "type": "module",
            "description": "MultiCodex adapter · "+entry["name"], "magpie": {"agent": "./agent.mjs"}})
        if not state.exists():
            save_json(state, {})
        block = (BEGIN+"\nMULTICODEX_STATE="+shlex.quote(str(state))+"\nMULTICODEX_BRIDGE="+
            shlex.quote(str(runtime/"runtime.py"))+"\n. "+
            shlex.quote(str(runtime/"hook.sh"))+" || return $?\n"+END+"\n")
        atomic(environment, prior+("" if not prior or prior.endswith("\n") else "\n")+block)

    def find(self, identifier):
        for entry in self.db["instances"]:
            if identifier in (entry["id"], entry["name"]):
                return entry
        raise ValueError("Instance not found")

    def magpie(self, *args):
        binary = os.environ.get("MULTICODEX_MAGPIE_BIN") or shutil.which("magpie")
        if not binary and (Path.home()/".local/bin/magpie").exists():
            binary = str(Path.home()/".local/bin/magpie")
        if not binary:
            raise ValueError("magpie is not installed or not on PATH")
        result = subprocess.run([binary, *args], env={**os.environ, "XDG_CONFIG_HOME": str(self.config.parent)},
            capture_output=True, text=True, timeout=40)
        if result.returncode:
            raise ValueError("Magpie could not apply this selection: "+result.stderr.strip()[-400:])

    def gateway(self):
        for entry in self.db["instances"]:
            state = read_json(Path(entry["state"]), {})
            if state.get("baseURL", "").endswith("/backend-api/codex"):
                return state["baseURL"][:-len("/backend-api/codex")], state.get("apiKey", "magpie")
        addr = os.environ.get("MAGPIE_ADDR", "127.0.0.1:3425")
        return "http://"+addr, "magpie"

    def models(self):
        base, key = self.gateway()
        request = urllib.request.Request(base+"/v1/codex/models", headers={"Authorization": "Bearer "+key, "User-Agent": "MultiCodex"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
        return [{"id": m["slug"], "name": m.get("display_name", m["slug"])} for m in data.get("models", []) if m.get("slug") and m.get("visibility") != "hide"]

    def snapshot(self):
        instances = []
        for entry in self.db["instances"]:
            state = read_json(Path(entry["state"]), {})
            instances.append({"id": entry["id"], "name": entry["name"], "home": entry["home"],
                "enabled": bool(state.get("model") and state.get("baseURL") and state.get("apiKey")),
                "model": state.get("model", ""), "lastModel": entry.get("lastModel", ""),
                "launch": "cxi "+shlex.quote(entry.get("alias", entry["name"]))})
        try:
            models, error = self.models(), ""
        except Exception:
            models, error = [], "Magpie's model list is unavailable. Start the gateway and refresh."
        return {"instances": instances, "models": models, "modelError": error,
            "defaultHome": str(Path.home()/".codex")}

    def apply(self, request):
        action, args = request.get("action"), request.get("args", {})
        if not isinstance(args, dict):
            raise ValueError("Invalid request arguments")
        if action == "refresh":
            return "Refreshed"
        if action == "add":
            home, name = home_path(args.get("home", "")), display_name(args.get("name", ""))
            if any(e["home"] == str(home) for e in self.db["instances"]):
                raise ValueError("This CODEX_HOME is already registered")
            if any(e["name"] == name for e in self.db["instances"]):
                raise ValueError("Choose a different instance name")
            if not home.exists() and not args.get("create"):
                raise ValueError("The directory does not exist; enable Create directory to make it")
            aid = "multicodex-"+hashlib.sha256(str(home).encode()).hexdigest()[:16]
            state = home/"multicodex.json"
            if state.exists():
                raise ValueError("An unmanaged multicodex.json already exists in this directory")
            entry = {"id": aid, "name": name, "home": str(home), "state": str(state),
                "adapter": str(self.config/"local-plugins/multicodex-agents"/aid), "lastModel": ""}
            self.write_adapter(entry)
            registry = self.registry()
            registry["plugins"].append({"spec": entry["adapter"]})
            save_json(self.registry_path, registry)
            self.db["instances"].append(entry)
            return "Added "+name
        entry = self.find(args.get("id"))
        if action == "rename":
            name = display_name(args.get("name", ""))
            if any(e["id"] != entry["id"] and e["name"] == name for e in self.db["instances"]):
                raise ValueError("Choose a different instance name")
            old_alias = entry.get("alias")
            entry["name"] = name
            self.write_adapter(entry)
            if old_alias and old_alias != entry["alias"]:
                remove_alias({**entry, "alias": old_alias})
            return "Renamed instance"
        if action == "model":
            model = args.get("model", "")
            if not any(m["id"] == model for m in self.models()):
                raise ValueError("Choose a model from this Magpie's list")
            self.magpie(entry["id"], "magpie/"+model)
            entry["lastModel"] = model
            return "Model updated"
        if action == "toggle":
            if args.get("enabled"):
                if not entry.get("lastModel"):
                    raise ValueError("Choose a model first")
                self.magpie(entry["id"], "magpie/"+entry["lastModel"])
            else:
                self.magpie(entry["id"], "default")
            return "Updated instance"
        if action == "remove":
            self.magpie(entry["id"], "default")
            environment = Path(entry["home"])/"cxi.env"
            if environment.exists():
                atomic(environment, clean_environment(environment.read_text()))
            remove_alias(entry)
            registry = self.registry()
            registry["plugins"] = [p for p in registry["plugins"] if p.get("spec") != entry["adapter"]]
            save_json(self.registry_path, registry)
            self.db["instances"].remove(entry)
            return "Removed registration; files and sessions are kept"
        raise ValueError("Unsupported action")

    def process(self, refresh=False):
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = self.db_path.parent/"controller.lock"
        regular(lock)
        with lock.open("a") as file:
            os.chmod(lock, 0o600)
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            self.db = read_json(self.db_path, self.db)
            self.adopt()
            self.install_launcher()
            registry = self.registry()
            own = self.own_entry(registry)
            options = own.get("options", {})
            request = options.get("request")
            if request is None and options.get("state") and not refresh:
                return
            # The main Magpie agent card can change the adapter independently
            # of this page. Re-enable must use its latest connected selection.
            for entry in self.db["instances"]:
                state = read_json(Path(entry["state"]), {})
                if state.get("model") and state.get("baseURL") and state.get("apiKey"):
                    entry["lastModel"] = state["model"]
            self.save()
            if request is not None and (not isinstance(request, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", str(request.get("id", "")))):
                raise ValueError("Invalid request identifier")
            rid = request["id"] if request else "initial"
            result = self.db["receipts"].get(rid)
            if not result:
                try:
                    message = self.apply(request) if request else "Ready"
                    result = {"id": rid, "ok": True, "message": message}
                except Exception as error:
                    result = {"id": rid, "ok": False, "message": str(error)[:500]}
                self.db["receipts"][rid] = result
                self.db["receipts"] = dict(list(self.db["receipts"].items())[-40:])
                self.save()
            state = self.snapshot()
            registry = self.registry()
            own = self.own_entry(registry)
            current = own.get("options", {}).get("request")
            if current and current.get("id") != rid:
                return
            own["options"] = {"schema": 1, "state": state, "result": result}
            save_json(self.registry_path, registry)

    def watch(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = self.db_path.parent/"watcher.lock"
        regular(lock)
        with lock.open("a") as file:
            os.chmod(lock, 0o600)
            for _ in range(20):
                try:
                    fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError: time.sleep(.1)
            else: return
            source = self.package/"multicodex/controller.py"
            version = source.stat().st_mtime_ns
            previous = None
            while source.exists() and source.stat().st_mtime_ns == version:
                try:
                    files = [self.registry_path] + [Path(entry["state"]) for entry in read_json(self.db_path, self.db)["instances"]]
                    stamp = tuple((str(path), path.stat().st_mtime_ns if path.exists() else None) for path in files)
                    if stamp != previous:
                        self.own_entry(self.registry())
                        self.process(refresh=True)
                        previous = tuple((str(path), path.stat().st_mtime_ns if path.exists() else None) for path in files)
                except (FileNotFoundError, ValueError): return
                time.sleep(.3)


def main():
    # Disconnect previews link plugin folders into a temporary HOME. Never
    # run a state-mutating manager against those linked runtime directories.
    if os.environ.get("MAGPIE_DRY_PROVIDERS"):
        return
    parser = argparse.ArgumentParser(description="Independent Codex homes in Magpie")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--package", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("process")
    commands.add_parser("watch")
    commands.add_parser("list")
    args = parser.parse_args()
    controller = Controller(args.config, args.package)
    if args.command == "process":
        controller.process()
    elif args.command == "watch":
        controller.watch()
    elif args.command == "list":
        print(json.dumps(controller.snapshot()["instances"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("MultiCodex: "+str(error), file=sys.stderr)
        sys.exit(1)

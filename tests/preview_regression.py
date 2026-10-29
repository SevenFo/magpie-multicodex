"""Bounded Magpie preview regression using private fixture homes, no inference."""
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "multicodex"))
from controller import Controller
from runtime import save_json
from unittest.mock import patch


def run():
    binary = shutil.which("magpie")
    with tempfile.TemporaryDirectory(prefix="multicodex-preview-test-") as temp:
        user = Path(temp).resolve() / "home"
        config = user / ".config/magpie"
        save_json(config / "providers.json", {"providers": [{"id": "example", "key": "fixture",
                  "chat": "http://127.0.0.1:1/v1", "models": ["fast"]}]})
        save_json(config / "plugins.json", {"plugins": [{"spec": str(SOURCE)}]})
        (config / "plugins.yml").write_text("preset: essentials\nsettled: 1\n")
        manager = Controller(config, SOURCE)
        home = user / ".codex-instances/work"
        with patch("pathlib.Path.home", return_value=user), patch.dict(os.environ,
                {"MULTICODEX_NO_LAUNCHER": "1", "CXI_ROOT": str(user/".codex-instances")}):
            manager.apply({"action": "add", "args": {"name": "work", "home": str(home), "create": True}})
            manager.save()
        entry = manager.find("work")
        state = Path(entry["state"])
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        key = secrets.token_hex(24)
        base = "http://127.0.0.1:" + str(port)
        env = {**os.environ, "HOME": str(user), "XDG_CONFIG_HOME": str(config.parent),
               "XDG_CACHE_HOME": str(user/".cache"), "CODEX_HOME": str(user/".codex"),
               "CLAUDE_CONFIG_DIR": str(user/".claude"), "MAGPIE_NO_ACCOUNTS": "1",
               "MULTICODEX_NO_LAUNCHER": "1", "MAGPIE_WEB_KEY": key}
        # The adapter is exercised by Magpie; no manager watcher is needed.
        registry = json.loads((config/"plugins.json").read_text())
        registry["plugins"] = [p for p in registry["plugins"] if p["spec"] != str(SOURCE)]
        save_json(config/"plugins.json", registry)
        proc = subprocess.Popen([binary, "web", "--no-open", "--addr", "127.0.0.1:"+str(port)],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                if proc.poll() is not None:
                    raise RuntimeError("Fixture Magpie exited")
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=.1).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise TimeoutError("Fixture Magpie did not start")
            client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            client.open(base+"/?k="+key, timeout=10).close()
            body = json.dumps({"agent": entry["id"], "field": "model", "value": "magpie/example/fast"}).encode()
            client.open(urllib.request.Request(base+"/api/set", data=body,
                        headers={"Content-Type": "application/json"}), timeout=15).close()
            expected = json.loads(state.read_text())
            assert expected["model"] == "example/fast"
            for _ in range(3):
                result = json.load(client.open(base+"/api/agents/preview/"+entry["id"], timeout=25))
                assert not result.get("error"), result
                assert json.loads(state.read_text()) == expected, "Preview changed the real fixture config"
                (home/".cxi_last_used").touch()
            print("PASS: 3 disconnect previews and start-marker changes leave real fixture connected; zero inference")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    run()

import contextlib
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE/"multicodex"))
from controller import Controller, home_path, clean_environment
from runtime import launch_data, read_json, save_json
from cxi_bundle import install as install_cxi


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="multicodex-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.c = Controller(self.root/"config/magpie", SOURCE)
        self.c.models = lambda: [{"id": "example/fast", "name": "Fast"}, {"id": "example/deep", "name": "Deep"}]
        self.calls = []
        def fake_magpie(aid, value):
            self.calls.append((aid, value))
            entry = self.c.find(aid)
            save_json(Path(entry["state"]), {} if value == "default" else {
                "model": value.removeprefix("magpie/"), "schema": 1,
                "baseURL": "http://127.0.0.1:3425/backend-api/codex", "apiKey": "fixture-key"})
        self.c.magpie = fake_magpie
        save_json(self.c.registry_path, {"plugins": [{"spec": str(SOURCE)}, {"spec": "unrelated-fixture"}]})
        self.env = patch.dict(os.environ, {"MULTICODEX_NO_LAUNCHER": "1", "CXI_ROOT": str(self.root/"cxi")})
        self.env.start(); self.addCleanup(self.env.stop)

    def add(self, name):
        self.c.apply({"action": "add", "args": {"name": name, "home": str(self.root/"homes"/name), "create": True}})
        return self.c.find(name)

    def test_two_homes_select_and_disable_independently(self):
        a, b = self.add("Work"), self.add("Personal")
        self.c.apply({"action": "model", "args": {"id": a["id"], "model": "example/fast"}})
        self.assertEqual(read_json(Path(b["state"])), {})
        self.c.apply({"action": "model", "args": {"id": b["id"], "model": "example/deep"}})
        self.c.apply({"action": "toggle", "args": {"id": a["id"], "enabled": False}})
        self.assertEqual(read_json(Path(a["state"])), {})
        self.assertEqual(read_json(Path(b["state"]))["model"], "example/deep")
        self.assertNotIn("fixture-key", json.dumps(self.c.snapshot()))

    def test_default_home_and_duplicate_paths_are_rejected(self):
        for value in (str(Path.home()/".codex"), str(Path.home()), "/", "relative/path"):
            with self.assertRaises(ValueError): home_path(value)
        a = self.add("Work")
        with self.assertRaises(ValueError):
            self.c.apply({"action": "add", "args": {"name": "Other", "home": a["home"]}})

    def test_existing_config_auth_and_user_environment_are_kept(self):
        path = self.root/"existing"; path.mkdir()
        (path/"config.toml").write_text('# user config\nmodel="original"\n')
        (path/"auth.json").write_text('{"fixture":"keep"}')
        (path/"cxi.env").write_text('export EXAMPLE_SETTING="kept"\n')
        self.c.apply({"action": "add", "args": {"name": "Existing", "home": str(path)}})
        self.assertEqual((path/"config.toml").read_text(), '# user config\nmodel="original"\n')
        self.assertEqual((path/"auth.json").read_text(), '{"fixture":"keep"}')
        self.assertTrue((path/"cxi.env").read_text().startswith('export EXAMPLE_SETTING="kept"\n'))
        self.c.apply({"action": "remove", "args": {"id": self.c.find("Existing")["id"]}})
        self.assertEqual((path/"cxi.env").read_text(), 'export EXAMPLE_SETTING="kept"\n')
        self.assertEqual(len(self.c.registry()["plugins"]), 2)

    def test_request_receipt_prevents_duplicate_mutations(self):
        request = {"id": "fixture_request_01", "action": "add", "args": {"name": "One", "home": str(self.root/"one"), "create": True}}
        registry = self.c.registry();registry["plugins"][0]["options"] = {"request": request}
        save_json(self.c.registry_path, registry)
        self.c.process()
        options = self.c.own_entry(self.c.registry())["options"]
        self.assertTrue(options["result"]["ok"])
        self.assertEqual(len(options["state"]["instances"]), 1)
        registry = self.c.registry();self.c.own_entry(registry)["options"] = {"request": request}
        save_json(self.c.registry_path, registry)
        self.c.process()
        self.assertEqual(len(self.c.db["instances"]), 1)

    def test_rename_changes_the_native_agent_label(self):
        a = self.add("Work")
        self.c.apply({"action": "rename", "args": {"id": a["id"], "name": "Writing"}})
        self.assertIn('Codex · Writing', (Path(a["adapter"])/"agent.mjs").read_text())
        self.assertEqual(self.c.find("Writing")["id"], a["id"])

    def test_invalid_model_and_malformed_launcher_do_not_execute(self):
        a = self.add("Work")
        with self.assertRaises(ValueError):
            self.c.apply({"action": "model", "args": {"id": a["id"], "model": 'unknown/"bad"'}})
        self.assertEqual(self.calls, [])
        with self.assertRaises(ValueError): clean_environment("# >>> multicodex >>>\n")

    def test_runtime_uses_magpie_catalogue_and_keeps_key_out_of_arguments(self):
        a = self.add("Work")
        self.c.apply({"action": "model", "args": {"id": a["id"], "model": "example/fast"}})
        key, args = launch_data(Path(a["state"]), lambda base, key: {"models": [{"slug": "example/fast"}]})
        self.assertEqual(key, "fixture-key")
        self.assertNotIn(key, " ".join(args))
        self.assertIn('model="example/fast"', args)
        self.assertIn('MULTICODEX_API_KEY', " ".join(args))

    def test_external_agent_selection_refreshes_page_and_reenable_model(self):
        entry = self.add("Work")
        self.c.apply({"action": "model", "args": {"id": entry["id"], "model": "example/fast"}})
        self.c.save()
        registry = self.c.registry()
        self.c.own_entry(registry)["options"] = {"schema": 1, "state": self.c.snapshot()}
        save_json(self.c.registry_path, registry)
        save_json(Path(entry["state"]), {"schema": 1, "model": "example/deep",
            "baseURL": "http://127.0.0.1:3425/backend-api/codex", "apiKey": "fixture-key"})
        self.c.process(refresh=True)
        options = self.c.own_entry(self.c.registry())["options"]
        self.assertEqual(options["state"]["instances"][0]["model"], "example/deep")
        self.assertEqual(self.c.find(entry["id"])["lastModel"], "example/deep")
        self.c.apply({"action": "toggle", "args": {"id": entry["id"], "enabled": False}})
        self.c.apply({"action": "toggle", "args": {"id": entry["id"], "enabled": True}})
        self.assertEqual(read_json(Path(entry["state"]))["model"], "example/deep")

    def test_managed_hook_preserves_args_and_normal_start_marker(self):
        binaries = self.root / "bin"
        binaries.mkdir()
        fake = binaries / "codex"
        fake.write_text('#!/usr/bin/env python3\nimport json,sys,os\nprint(json.dumps({"args":sys.argv[1:],"key":os.environ.get("MULTICODEX_API_KEY")}))\n')
        fake.chmod(0o700)
        bridge = self.root / "fixture_bridge.py"
        bridge.write_text('import sys\nw=["ready","fixture-key","-c",\'model="example/fast"\',"-c",\'model_provider="magpie_cxi"\',"-c",\'model_providers.magpie_cxi={}\',"-c",\'model_catalog_json="fixture"\']\nsys.stdout.buffer.write(b"\\0".join(x.encode() for x in w)+b"\\0")\n')
        entry = self.add("Work")
        environment = Path(entry["home"]) / "cxi.env"
        environment.write_text('MULTICODEX_STATE="fixture"\nMULTICODEX_BRIDGE='+str(bridge)+'\n. '+str(SOURCE / 'multicodex/hook.sh')+' || return $?\n')
        for shell in ["bash", "zsh"]:
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                suffix = "zsh" if shell == "zsh" else "bash"
                invocation = '. '+str(SOURCE / ('vendor/cxi/cxi.'+suffix))+'; cxi '+entry["alias"]+' "prompt with spaces"'
                result = subprocess.run([shell, "-c", invocation], env={**os.environ,
                    "PATH": str(binaries)+os.pathsep+os.environ["PATH"]}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertIn('model="example/fast"', data["args"])
                self.assertEqual(data["args"][-1], "prompt with spaces")
                self.assertEqual(data["key"], "fixture-key")
                self.assertTrue((Path(entry["home"])/".cxi_last_used").exists())

    def test_adapter_paths_follow_home_in_disconnect_preview(self):
        user_home = self.root / "user"
        instance = user_home / ".codex-instances/work"
        with patch("pathlib.Path.home", return_value=user_home):
            self.c.apply({"action": "add", "args": {"name": "Work", "home": str(instance), "create": True}})
        text = (Path(self.c.find("Work")["adapter"])/"agent.mjs").read_text()
        descriptor = json.loads(text.split("export const agent = ", 1)[1].split(";", 1)[0])
        self.assertEqual(descriptor["config"], "~/.codex-instances/work/multicodex.json")
        self.assertEqual(descriptor["dir"], "~/.codex-instances/work")
        self.assertNotIn(str(user_home), text)

    def test_replaced_local_package_cannot_keep_its_old_watcher(self):
        registry = {"plugins": [{"spec": str(self.root/"new-magpie-multicodex")}]}
        with self.assertRaisesRegex(ValueError, "replaced"):
            self.c.own_entry(registry)

    def test_bundled_cxi_matches_its_pinned_upstream_files(self):
        metadata=read_json(SOURCE/"vendor/cxi/upstream.json")
        self.assertEqual(metadata["repository"], "https://github.com/SevenFo/cxi")
        for name, digest in metadata["sha256"].items():
            self.assertEqual(hashlib.sha256((SOURCE/"vendor/cxi"/name).read_bytes()).hexdigest(), digest)

    def test_bundled_install_preserves_shell_settings_and_is_repeatable(self):
        home=self.root/"user";home.mkdir()
        (home/".zshrc").write_text('# existing settings\n')
        with patch("pathlib.Path.home", return_value=home), patch.dict(os.environ, {
            "MULTICODEX_NO_LAUNCHER":"0", "XDG_DATA_HOME":str(home/".local/share"), "ZDOTDIR":str(home)}):
            install_cxi(SOURCE);install_cxi(SOURCE)
        self.assertTrue((home/".local/bin/cxi").exists())
        text=(home/".zshrc").read_text()
        self.assertTrue(text.startswith('# existing settings\n'))
        self.assertEqual(text.count('source '),1)
        self.assertEqual(len(list((home/".local/share/cxi/shell-backups").glob('.zshrc-*'))),1)


if __name__ == "__main__": unittest.main()

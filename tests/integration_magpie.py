"""Optional integration test against Magpie, with disposable homes and models."""
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
sys.path.insert(0, str(SOURCE/"multicodex"))
from runtime import save_json, read_json


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_port(number, process):
    for _ in range(300):
        if process.poll() is not None:raise RuntimeError("Fixture server exited")
        try:
            with socket.create_connection(("127.0.0.1", number), timeout=.1):return
        except OSError:time.sleep(.1)
    raise RuntimeError("Fixture server did not start")


def run():
    binary = shutil.which("magpie") or str(Path.home()/".local/bin/magpie")
    with tempfile.TemporaryDirectory(prefix="multicodex-integration-") as temp:
        root = Path(temp).resolve(); config = root/"config/magpie"
        gateway, web = port(), port(); key = secrets.token_hex(24)
        save_json(config/"plugins.json", {"plugins": [{"spec": str(SOURCE)}]})
        save_json(config/"providers.json", {"providers": [
            {"id": "example", "name": "Example", "chat": "http://127.0.0.1:1/v1", "key": "fixture", "models": ["fast", "deep"], "contexts": {"*": 100000}},
            {"id": "codex", "off": True}, {"id": "claude", "off": True}, {"id": "copilot", "off": True}]})
        save_json(config/"settings.json", {"lang": "en"})
        (config/"plugins.yml").write_text("preset: all\nsettled: 1\nplugins:\n  - id: library\n    enabled: false\n")
        (root/"default-codex").mkdir()
        env = {**os.environ, "XDG_CONFIG_HOME": str(config.parent), "CODEX_HOME": str(root/"default-codex"),
            "CLAUDE_CONFIG_DIR": str(root/"default-claude"), "MAGPIE_NO_ACCOUNTS": "1", "MULTICODEX_NO_LAUNCHER": "1",
            "CXI_ROOT": str(root/"cxi"),
            "MAGPIE_ADDR": f"127.0.0.1:{gateway}", "MAGPIE_WEB_KEY": key, "MULTICODEX_MAGPIE_BIN": binary}
        processes=[]
        try:
            serve=subprocess.Popen([binary,"serve"],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE);processes.append(serve)
            wait_port(gateway,serve)
            ui=subprocess.Popen([binary,"web","--no-open","--addr",f"127.0.0.1:{web}"],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE);processes.append(ui)
            wait_port(web,ui)
            base=f"http://127.0.0.1:{web}"
            client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            client.open(base+"/?k="+key,timeout=20).close()
            def get(path):return json.load(client.open(base+path,timeout=30))
            def options():
                body={"spec":str(SOURCE)}
                return json.load(client.open(urllib.request.Request(base+"/api/plugin-pages/options",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"}),timeout=20))
            def submit(action,args=None):
                time.sleep(1.2)
                rid=secrets.token_hex(12)
                body={"spec":str(SOURCE),"options":{"schema":1,"request":{"id":rid,"action":action,"args":args or {}}}}
                client.open(urllib.request.Request(base+"/api/plugin-pages/options",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"}),timeout=20).close()
                for i in range(160):
                    if i%4==0:get("/api/plugins")
                    current=options()
                    if current.get("result",{}).get("id")==rid:
                        assert current["result"]["ok"],current["result"]
                        return current["state"]
                    time.sleep(.25)
                raise AssertionError("Plugin backend did not process "+action)
            get("/api/plugins")
            state=submit("refresh")
            assert any(m["id"]=="example/fast" for m in state["models"]),state
            state=submit("add",{"name":"Work","home":str(root/"homes/work"),"create":True})
            work=state["instances"][0]
            state=submit("add",{"name":"Personal","home":str(root/"homes/personal"),"create":True})
            personal=next(e for e in state["instances"] if e["name"]=="Personal")
            state=submit("model",{"id":work["id"],"model":"example/fast"})
            assert next(e for e in state["instances"] if e["id"]==work["id"])["enabled"]
            assert not next(e for e in state["instances"] if e["id"]==personal["id"])["enabled"]
            state=submit("model",{"id":personal["id"],"model":"example/deep"})
            state=submit("toggle",{"id":work["id"],"enabled":False})
            assert next(e for e in state["instances"] if e["id"]==personal["id"])["enabled"]
            state=submit("rename",{"id":work["id"],"name":"Writing"})
            state=submit("remove",{"id":work["id"]})
            assert len(state["instances"])==1
            assert (root/"homes/work").exists()
            pages=get("/api/plugin-pages")
            assert any(p["title"]=="CXI for Magpie" for p in pages)
            print("PASS: real Magpie page requests add, rename, switch, disable and remove separate homes",flush=True)
            if "--browser" in sys.argv:
                program='''async page => {
                  await page.keyboard.press("Escape");
                  if(await page.locator("#modal").isVisible()) {
                    const close=page.locator("#modal").getByRole("button",{name:/^(Close|Cancel|关闭|取消)$/}).first();
                    if(await close.count())await close.click({force:true});
                    else await page.evaluate(()=>closeModal());
                    await page.waitForTimeout(500);
                  }
                  await page.locator('button[data-plugin-page]').filter({hasText:"CXI for Magpie"}).click({force:true});
                  await page.keyboard.press("Escape");
                  const frame=page.frameLocator('iframe.plugin-frame:not(.plugin-panel-frame)[title="CXI for Magpie"]');
                  await frame.getByRole("heading",{name:"CXI for Magpie",exact:true}).waitFor();
                  await frame.getByRole("button",{name:"Add instance",exact:true}).click();
                  await frame.locator("#instance-name").fill("Browser");
                  await frame.locator("#instance-home").fill(HOME);
                  await frame.locator("#instance-create").check();
                  await frame.getByRole("button",{name:"Save",exact:true}).click();
                  await frame.getByRole("heading",{name:"Browser",exact:true}).waitFor({timeout:60000});
                  await frame.getByRole("combobox",{name:"Browser · Model",exact:true}).selectOption("example/fast");
                  await frame.getByRole("switch",{name:"Browser · Magpie on",exact:true}).waitFor();
                  await page.waitForTimeout(3000);
                  const checked=await frame.getByRole("switch",{name:"Browser · Magpie on",exact:true}).getAttribute("aria-checked");
                  if(checked!=="true")throw Error("Browser model selection did not apply");
                  await page.screenshot({path:SCREENSHOT,fullPage:true});
                  console.log("PASS: browser adds and connects a home through the sandboxed page");
                }'''.replace("HOME",json.dumps(str(root/"homes/browser"))).replace("SCREENSHOT",json.dumps(str(root/"multicodex.png")))
                script=root/"browser.js";script.write_text(program)
                session="multicodex-"+secrets.token_hex(4)
                def browser(*args):
                    r=subprocess.run(["playwright-cli","-s="+session,*args],capture_output=True,text=True,timeout=120,cwd=root)
                    output=(r.stdout+r.stderr).replace(key,"<local-session>")
                    if r.returncode:raise RuntimeError(output[-2500:])
                    if "### Error" in output:raise RuntimeError(output[-2500:])
                    return output
                try:
                    browser("open",base+"/?k="+key)
                    print(browser("run-code","--filename="+str(script))[-1600:],flush=True)
                    if os.environ.get("MULTICODEX_SCREENSHOT"):
                        shutil.copy2(root/"multicodex.png",os.environ["MULTICODEX_SCREENSHOT"])
                finally:browser("close")
        finally:
            for process in reversed(processes):
                process.terminate()
                try:process.communicate(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.communicate()


if __name__=="__main__":run()

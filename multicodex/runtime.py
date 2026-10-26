"""Private instance launch data shared by the CLI and cxi compatibility hook."""
import json, os, re, stat, sys, tempfile, urllib.parse, urllib.request
from pathlib import Path
VALID_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\[\]-]{0,255}\Z")

def regular(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Expected a regular file: {path}")

def read_json(path, default=None):
    regular(path)
    return json.loads(path.read_text()) if path.exists() else default

def atomic(path, text, mode=0o600):
    regular(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".magpie-cxi-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def save_json(path, data):
    atomic(path, json.dumps(data, ensure_ascii=False, indent=2)+"\n")

def launch_data(path, fetch_catalog=None):
    state = read_json(path, {})
    if not isinstance(state, dict):
        raise ValueError("Invalid instance state")
    if not state or not state.get("model"):
        return None
    model, base, key = (state.get(k) for k in ("model", "baseURL", "apiKey"))
    if state.get("schema") != 1 or not isinstance(model, str) or not VALID_MODEL.fullmatch(model):
        raise ValueError("Invalid model or adapter schema")
    if not isinstance(key, str) or not key or any(c in key for c in "\r\n\0"):
        raise ValueError("Invalid gateway credential")
    if not isinstance(base, str):
        raise ValueError("Missing gateway URL")
    url = urllib.parse.urlsplit(base)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Invalid gateway URL")
    if not url.path.endswith("/backend-api/codex"):
        raise ValueError("Expected the Magpie Codex gateway endpoint")
    regular(path)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        # Magpie's atomic JSON writer uses 0644; restrict the private state
        # before reading its credential into a child process.
        path.chmod(0o600)
    base = base.rstrip("/")
    if fetch_catalog:
        catalogue = fetch_catalog(base, key)
    else:
        # /backend-api/codex/models is the ChatGPT passthrough, which needs
        # a ChatGPT token. This dedicated endpoint is Magpie's own catalogue.
        catalog_url = base[:-len("/backend-api/codex")]+"/v1/codex/models"
        request = urllib.request.Request(catalog_url, headers={"Authorization": "Bearer "+key, "User-Agent": "multicodex/0.2"})
        # Never forward a gateway key through an HTTP redirect.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        client = urllib.request.build_opener(NoRedirect())
        with client.open(request, timeout=15) as response:
            catalogue = json.load(response)
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get("models"), list):
        raise ValueError("Gateway returned no Codex model catalogue")
    if not any(m.get("slug") == model for m in catalogue["models"] if isinstance(m, dict)):
        raise ValueError("Selected model is absent from this gateway's Codex catalogue")
    catalogue_path = path.with_name("multicodex-models.json")
    save_json(catalogue_path, catalogue)
    provider = ('{name = "Magpie cxi", base_url = '+json.dumps(base)+', wire_api = "responses", '
        'env_key = "MULTICODEX_API_KEY", requires_openai_auth = false}')
    args = ["-c", "model="+json.dumps(model), "-c", 'model_provider="magpie_cxi"',
        "-c", "model_providers.magpie_cxi="+provider, "-c", "model_catalog_json="+json.dumps(str(catalogue_path))]
    return key, args

if __name__ == "__main__":
    try:
        if len(sys.argv) != 3 or sys.argv[1] != "args":
            raise ValueError("Internal launch bridge expects args and a state path")
        data = launch_data(Path(sys.argv[2]))
        words = ["off"] if data is None else ["ready", data[0], *data[1]]
        sys.stdout.buffer.write(b"\0".join(w.encode() for w in words)+b"\0")
    except Exception as error:
        print("MultiCodex: "+str(error), file=sys.stderr)
        sys.exit(1)

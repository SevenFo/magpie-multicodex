import { fileURLToPath } from "node:url";
import path from "node:path";
import os from "node:os";

// The page can only edit its own options. A typed request is handled by the
// installed backend, with a file lock and receipt to prevent duplicate work.
// No provider, credentials or model requests are intercepted by this plugin.
export const MultiCodex = async () => {
  if (process.env.MAGPIE_DRY_PROVIDERS) return {};
  const root = path.dirname(fileURLToPath(import.meta.url));
  const config = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config"), "magpie");
  // Page option changes retire the Bun host. Keep the small file watcher
  // outside that host so page-only use never waits for a provider request.
  const child = Bun.spawn(["python3", path.join(root, "multicodex", "controller.py"), "--config", config, "--package", root, "watch"],
    { stdin: "ignore", stdout: "ignore", stderr: "ignore", env: process.env });
  child.exited.catch(() => {});
  return {};
};

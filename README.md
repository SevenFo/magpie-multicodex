# CXI for Magpie

Manage multiple Codex configurations from one page in Magpie. Give each instance a name and a `CODEX_HOME`, then choose its model independently.

[中文说明](README.zh-CN.md)

## Install

Requires Magpie, Codex CLI and Python 3.9+ on macOS or Linux. cxi is bundled with the plugin.

```sh
magpie plugin add github:SevenFo/magpie-multicodex
```

Open **CXI for Magpie** in Magpie's sidebar. Open a new terminal after installation. Add a directory such as `~/codex/work`, choose a model, then start it:

```sh
cxi work
```

Each instance keeps its own settings, login and sessions. Your default Codex keeps its existing configuration. Restart an instance to apply a new selection; running background daemons are not restarted automatically.

The included [cxi](https://github.com/SevenFo/cxi) can also be installed on its own without Magpie. Removing an instance from this page keeps its files and sessions.

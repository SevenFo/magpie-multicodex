# CXI for Magpie

在 Magpie 里统一管理多个 Codex 配置。每个实例有自己的名称和 `CODEX_HOME`，可以分别选择模型。

## 安装

需要 macOS 或 Linux，以及 Magpie、Codex CLI、Python 3.9+。插件已内置 cxi，无需另装。

```sh
magpie plugin add github:SevenFo/magpie-multicodex
```

安装后重开终端。打开 Magpie 侧栏的 **CXI for Magpie**，添加一个目录，例如 `~/codex/work`，选择模型后启动：

```sh
cxi work
```

各实例的配置、登录和会话各自保存。主 Codex 继续使用原有配置。切换模型后重新启动实例即可，已运行的后台 daemon 不会自动重启。

内置的 [cxi](https://github.com/SevenFo/cxi) 也可以单独安装，适合不使用 Magpie 时。从页面移除实例只取消管理，不删除文件和会话。

magpie.ready.then(async () => {
  const options = await magpie.options.get();
  const count = options.state?.instances?.length || 0;
  const zh = magpie.theme?.lang?.startsWith("zh");
  document.getElementById("summary").textContent = zh
    ? `已管理 ${count} 个独立 Codex 实例。在侧栏 CXI for Magpie 中添加目录和选择模型。`
    : `${count} independent Codex homes. Open CXI for Magpie in the sidebar to manage them.`;
}).catch(() => { document.getElementById("summary").textContent = "Open CXI for Magpie in the sidebar."; });

# 边玩边优化 Balatro MCP

开发安装将 %AppData%\Balatro\Mods\BalatroMCP 链接到本仓库 mods\BalatroMCP。
Lua 修改后重启游戏即可生效；Python 包以 editable 方式安装，修改后重启 MCP 连接或服务即可生效。

## 初次安装

先按上游 README 安装 Lovely 和 Steamodded，再在仓库根目录运行：

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e .\mcp_server
    .\scripts\install-dev.ps1

开发安装脚本拒绝覆盖已有 Mod 文件夹。替换前请将其备份到 Mods 目录外，避免加载两份 Mod。
Lovely 0.10+ 使用游戏目录中的 winmm.dll。

## 游玩和排查

正常从 Steam 启动 Balatro，然后运行：

    Invoke-RestMethod http://127.0.0.1:8080/health
    .\.venv\Scripts\python.exe .\scripts\capture-state.py
    .\.venv\Scripts\python.exe -m pytest tests mcp_server/tests -q

状态快照写入 git 忽略的 local\captures，记录牌面、可用动作和版本，用来复现问题。
存档备份保存在 git 忽略的 local 目录。

## MCP 连接

推荐 stdio，由客户端管理服务进程：

    codex mcp add balatro --env BALATRO_MCP_API_BASE_URL=http://127.0.0.1:8080 -- "$PWD\.venv\Scripts\balatro-mcp-server.exe"

也可手动启动 HTTP 服务：

    .\scripts\start-mcp-network.ps1

MCP 地址为 http://127.0.0.1:8765/mcp，健康检查为 /healthz。游戏 API 和 MCP 默认都绑定本机回环地址。

## 日常开发

- Lua：mods\BalatroMCP\balatro_mcp 下的 state.lua、actions.lua、http_server.lua。
- MCP：mcp_server\src\balatro_mcp 下的 server.py、client.py。
- 先记录牌面和期望动作，再修改代码、运行测试、进行实际游戏验证。
- upstream 指向上游，在自己的 codex/ 开发分支提交改动。
- 游戏文件、存档和本机状态快照不提交到 GitHub。

## 牌组测试配置

MCP 的游戏状态现在包含 decks，列出普通牌组的 key、unlocked 和解锁条件。
如需用现有存档测试全部 15 个原版牌组，可先预览修改范围：

    .\.venv\Scripts\python.exe .\scripts\unlock-decks.py --profile 2

正常关闭游戏后，加上 --apply 才会写入。脚本先备份整个指定配置及 settings.jkr，
只修改 meta.jkr 中普通牌组的 unlocked 标记，保留其他收集进度、通关记录和赌注进度。
备份和校验记录位于 local\backups。恢复时先关闭游戏，再从对应备份恢复 meta.jkr。

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

## 新增游玩辅助能力（0.2）

MCP 新增 14 个工具，原有 22 个工具保留。升级 Lua 后重启游戏，升级 Python 后重启 MCP 连接。
本次不新增存档或恢复操作；正在游玩时无需为加载功能强制重启。

| 工具 | 用途 |
|---|---|
| get_deck_summary | 当前扑克牌组张数、初始张数、抽牌堆/弃牌堆数量、花色/点数/增强/蜡封/版本分布；include_cards 可读组成，不提供抽牌顺序 |
| describe_card | 按 key 或 area/index 读取本机游戏的中文效果、变量和当前 ability；不能确定的占位变量会明确列出 |
| get_scoring_model | 游戏计分源文件第一次使用时读入内存；读取缓存的牌型成长定义及模型范围 |
| get_hand_history | 读取每手原生实得分数和计分更新/小丑回调明细，UI 清空后仍保留，人工出牌同样采集 |
| preview_hand / compare_plays | 预估、比较选定手牌；partial/unsupported 不返回精确 score，也不据此推荐出牌 |
| compare_joker_swap | 比较商店替换、小丑顺序、买卖净成本、固定收入损失和成长重置 |
| compare_consumable | 比较普通行星的使用与出售，区分星座永久成长和篝火到首领结束的成长 |
| configure_assistant / get_assistant_config | 可选目标、玻璃保护、现金底线、比较跨度、日志设置；persist=true 才写入配置 |
| set_control_mode | 显式切换 assist（人工操作）与 auto（允许 MCP 操作） |
| reorder_cards | 使用完整稳定 uid 列表调整 hand/jokers 顺序，拒绝重复/缺失、正在拖动和移动固定小丑 |
| watch_state | 等待最多 60 秒的状态 revision 变化，返回精简状态和改变的部分 |
| get_log_history | 跨 MCP 进程读取操作、失败、状态变化、人工回调、计分和比较日志 |

### 游戏资料和预估范围

每次 MCP 启动读取 BALATRO_MCP_GAME_PATH 指定的游戏包；可以是 Balatro.exe 或它所在目录。
默认沿用本机 D:\SteamLibrary\steamapps\common\Balatro\Balatro.exe。本地化和卡牌配置保存在内存，
首次请求计分资料时再将 card.lua、state_events.lua、common_events.lua 读入内存。
解包后的游戏文件不执行、不写进仓库。游戏更新后重启 MCP 可同步资料。

预估使用独立的只读模型，不改变 RNG、卡牌、奖励或游戏进度。目前覆盖基础牌型、增强、
红蜡封、钢牌、玻璃、Hack、Mime、Blackboard、Baseball、Blueprint/Brainstorm、Constellation、
Campfire、Supernova，以及其他已实现的确定性效果；未知小丑、随机幸运效果、部分首领和挑战规则会返回明确的缺口。
实局计分记录用于校准模型；源码更新不等于独立模型自动适配所有机制变化。

商店没有手牌时，比较工具使用最近一手的牌面，并替换为当前的小丑、资金和牌型等级。
返回 basis=last_hand_with_current_inventory，表示参考情境，不能代表下一轮抽到的手牌。
没有参考手牌时会提示先读取或完成一手。玻璃碎裂概率不因计分重触发次数增加。

### 可选配置和共同游玩

不需要配置文件即可使用。可参考 assistant-config.example.json，复制到 local/assistant-config.json，
或通过 BALATRO_MCP_CONFIG 指定其他 JSON 路径。configure_assistant 的默认修改只在当前进程有效。
语言修改需要重启 MCP。日志默认写入 local/logs/events-日期.jsonl，可用 BALATRO_MCP_LOG_DIR 修改目录。
日志包含牌局数据，在 git 忽略目录；只轮询时记录变化，不重复写入相同状态。

新 Mod 启动后默认 assist，所有会操作游戏的请求都在游戏端被拒绝。读取和比较工具继续可用。
要自动游玩，显式调用 set_control_mode(mode="auto")；交还操作调用 mode="assist"。
配置 control_mode 可以额外限制当前 MCP，不能覆盖游戏端的辅助模式；重启游戏后需重新显式交接控制权。
手动操作继续走原生游戏流程。观察器保留最近 256 个游戏事件、50 手分数摘要和最近一手的完整计分上下文；
MCP 读取时追加到持久日志，同一手不会因轮询或 MCP 重启重复记录。多个 MCP 进程共用日志时会锁定追加写入。
未连接期间超过缓存上限的旧事件无法追溯，轮询间完成的较早手只保留分数摘要。

状态 revision 包含 Mod 实例标识，随有意义的状态变化而更新。修改操作默认使用最近读取的 revision，
也可向 act/play_hand/discard_selected/reorder_cards 传 expected_revision；游戏端再次检查，
发现人工变化会返回 stale_state。相同 request_id 的网络重试不会再次执行动作。

### 验证与持续优化

    .\.venv\Scripts\python.exe -m pip install -e .\mcp_server[test]
    .\.venv\Scripts\python.exe -m pytest tests mcp_server/tests -q
    .\.venv\Scripts\python.exe scripts/replay-logs.py local/play-history.jsonl

行为测试使用 Lua 5.1 模拟原生回调，覆盖人工计分、辅助模式、状态过期、位置调整和 HTTP 部分写入；
未安装可选 lupa 时 Lua 行为测试会跳过。回放脚本只读取日志和游戏资料，不连接或操作真实游戏。

## 牌组测试配置

MCP 的游戏状态现在包含 decks，列出普通牌组的 key、unlocked 和解锁条件。
如需用现有存档测试全部 15 个原版牌组，可先预览修改范围：

    .\.venv\Scripts\python.exe .\scripts\unlock-decks.py --profile 2

正常关闭游戏后，加上 --apply 才会写入。脚本先备份整个指定配置及 settings.jkr，
只修改 meta.jkr 中普通牌组的 unlocked 标记，保留其他收集进度、通关记录和赌注进度。
备份和校验记录位于 local\backups。恢复时先关闭游戏，再从对应备份恢复 meta.jkr。

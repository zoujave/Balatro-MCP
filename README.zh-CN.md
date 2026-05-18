# Balatro Agent

English README: [README.md](./README.md)

`Balatro Agent` 是一个给《Balatro》用的游戏 Mod + MCP Server 组合，整体结构仿照 `CharTyr/STS2-Agent`：

- `mods/BalatroAgent`：Steamodded Mod，把游戏状态和可执行操作暴露成本地 HTTP API
- `mcp_server`：把这套本地 API 包装成 MCP Server，方便接入支持 MCP 的 AI 客户端

## 快速开始

### 1. 安装 Mod 依赖

Balatro Agent 依赖 Balatro 的常见 Mod 环境：

1. 安装 Lovely
2. 安装 Steamodded/smods
3. 把 `mods/BalatroAgent` 安装到 Balatro 的 Mods 目录

本机默认 Balatro 目录是：

```text
D:\SteamLibrary\steamapps\common\Balatro
```

可以直接运行安装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\install-local.ps1" -BalatroPath "D:\SteamLibrary\steamapps\common\Balatro"
```

最终目录结构应类似：

```text
%AppData%\Balatro\Mods\
  smods\
  BalatroAgent\
    BalatroAgent.json
    BalatroAgent.lua
    balatro_agent\
```

### 2. 启动游戏并确认 Mod 生效

正常启动 Balatro，让 Lovely、Steamodded 和 Balatro Agent 随游戏一起加载。

然后打开：

```text
http://127.0.0.1:8080/health
```

如果返回里的 `data.service` 是 `balatro-agent`，说明 Mod 已经跑起来了。

如果 8080 已经被其他本地服务占用，可以用环境变量换端口：

```powershell
$env:BALATRO_AGENT_PORT = "18080"
```

然后检查：

```text
http://127.0.0.1:18080/health
```

### 3. 启动 MCP Server

先准备运行环境：

1. 安装 `Python 3.11+`
2. 安装 `uv`

Windows 安装 `uv`：

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

然后启动默认推荐的 `stdio` MCP：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\start-mcp-stdio.ps1"
```

如果你的 Balatro Agent 使用了非默认端口：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\start-mcp-stdio.ps1" -ApiBaseUrl "http://127.0.0.1:18080"
```

### 4. 连接 MCP 客户端

如果客户端支持命令式 MCP 启动，把工作目录指向 `mcp_server/`，命令填：

```text
uv run balatro-agent-mcp-server
```

如果客户端更适合连接 HTTP 版 MCP，可以启动网络版：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\start-mcp-network.ps1"
```

默认 MCP 地址：

```text
http://127.0.0.1:8765/mcp
```

## 当前能做什么

当前 `main` 分支提供的是一套可验证、可实际进入游戏执行的基础 Agent 接口：

- 读取当前游戏状态
- 获取当前可执行动作
- 启动新局
- 选择或跳过 Blind
- 选择手牌
- 出牌、弃牌、手牌排序
- 结算奖励并进入商店
- 商店购买、重掷、离开商店
- 使用或出售 Joker / 消耗牌
- 打开、选择或跳过 Booster 包
- 返回主菜单
- 通过 `stdio` 或 HTTP 方式暴露 MCP

HTTP API：

- `GET /health`
- `GET /state`
- `GET /actions/available`
- `POST /action`

MCP 工具：

- `health_check`
- `get_game_state`
- `get_raw_game_state`
- `get_available_actions`
- `act`
- `wait_until_actionable`

## 动作示例

通用 MCP 工具 `act` 接受动作名和可选参数：

```json
{"action": "start_run", "stake": 1}
{"action": "select_blind"}
{"action": "play_hand", "card_indices": [1, 2, 3, 4, 5]}
{"action": "discard", "card_indices": [6, 7]}
{"action": "buy", "area": "shop_jokers", "index": 1}
{"action": "use", "area": "consumeables", "index": 1, "card_indices": [1]}
```

## 验证

静态和 MCP 测试：

```powershell
pytest tests/test_lua_static.py -q
cd mcp_server
uv run pytest -q
```

本地结构验证：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\validate-local.ps1" -SkipGameLaunch
```

启动游戏并做 health smoke：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\validate-local.ps1" -LaunchGame
```

如果使用 18080 端口：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\validate-local.ps1" -LaunchGame -Port 18080
```

## 常见问题

### `http://127.0.0.1:8080/health` 打不开

优先检查：

1. Balatro 是否正在运行
2. Lovely 是否安装到 Balatro 游戏目录
3. Steamodded/smods 是否在 `%AppData%\Balatro\Mods`
4. `BalatroAgent` 是否在 `%AppData%\Balatro\Mods\BalatroAgent`
5. 8080 端口是否被其他程序占用

如果端口被占用，用：

```powershell
$env:BALATRO_AGENT_PORT = "18080"
```

### MCP 能启动，但读不到游戏状态

通常说明 MCP Server 已经启动，但游戏里的 Mod 没连上。先确认：

1. 游戏正在运行
2. `/health` 返回的 `data.service` 是 `balatro-agent`
3. MCP 连接的地址和 Mod 监听端口一致

如果你把 Mod 改到了 18080，启动 MCP 时也要传：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\start-mcp-stdio.ps1" -ApiBaseUrl "http://127.0.0.1:18080"
```

### 要不要开启调试动作

正常使用不需要。

当前版本只暴露围绕 Balatro 正常流程的动作，尽量避免直接执行任意 Lua 或控制台命令。后续如果加入开发期调试工具，也应默认关闭。

## 仓库结构

- `mods/BalatroAgent/`：Balatro Steamodded Mod
- `mcp_server/`：MCP Server 源码
- `scripts/`：安装、启动、验证、打包脚本
- `tests/`：静态和结构测试

`docs/` 只作为本地工作计划/设计记录使用，默认不会进入仓库。

## License

目前尚未声明开源许可证。发布前请根据实际开源策略补充 `LICENSE`。

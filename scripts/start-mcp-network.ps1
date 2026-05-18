param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8080",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765,
    [string]$Path = "/mcp"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$mcpDir = Join-Path $repoRoot "mcp_server"

$env:BALATRO_AGENT_API_BASE_URL = $ApiBaseUrl
Set-Location $mcpDir
uv run balatro-agent-network-mcp-server --host $HostName --port $Port --path $Path --api-base-url $ApiBaseUrl

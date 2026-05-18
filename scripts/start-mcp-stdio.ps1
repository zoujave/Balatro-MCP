param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$mcpDir = Join-Path $repoRoot "mcp_server"

$env:BALATRO_MCP_API_BASE_URL = $ApiBaseUrl
Set-Location $mcpDir
uv run balatro-mcp-server

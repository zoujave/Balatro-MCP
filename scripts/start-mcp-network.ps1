param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8080",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765,
    [string]$Path = "/mcp"
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$mcpDir = Join-Path $repoRoot "mcp_server"
$env:BALATRO_MCP_API_BASE_URL = $ApiBaseUrl
$localServer = Join-Path $repoRoot ".venv\Scripts\balatro-network-mcp-server.exe"
if (Test-Path -LiteralPath $localServer) {
    & $localServer --host $HostName --port $Port --path $Path --api-base-url $ApiBaseUrl
} elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    Push-Location $mcpDir
    try { uv run balatro-network-mcp-server --host $HostName --port $Port --path $Path --api-base-url $ApiBaseUrl } finally { Pop-Location }
} else { throw "Install the editable package in the repository .venv, or install uv. See README.dev.md." }
exit $LASTEXITCODE

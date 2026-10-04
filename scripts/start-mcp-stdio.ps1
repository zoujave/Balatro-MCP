param([string]$ApiBaseUrl = "http://127.0.0.1:8080")
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$mcpDir = Join-Path $repoRoot "mcp_server"
$env:BALATRO_MCP_API_BASE_URL = $ApiBaseUrl
$localServer = Join-Path $repoRoot ".venv\Scripts\balatro-mcp-server.exe"
if (Test-Path -LiteralPath $localServer) {
    & $localServer
} elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    Push-Location $mcpDir
    try { uv run balatro-mcp-server } finally { Pop-Location }
} else { throw "Install the editable package in the repository .venv, or install uv. See README.dev.md." }
exit $LASTEXITCODE

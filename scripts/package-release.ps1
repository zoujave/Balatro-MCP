param(
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$distDir = Join-Path $repoRoot $OutputDir
$packageRoot = Join-Path $distDir "Balatro-MCP"
$zipPath = Join-Path $distDir "Balatro-MCP.zip"

if (Test-Path -LiteralPath $packageRoot) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

Copy-Item -LiteralPath (Join-Path $repoRoot "mods\BalatroAgent") -Destination (Join-Path $packageRoot "BalatroAgent") -Recurse
$mcpTarget = Join-Path $packageRoot "mcp_server"
New-Item -ItemType Directory -Force -Path $mcpTarget | Out-Null
robocopy (Join-Path $repoRoot "mcp_server") $mcpTarget /E /XD .venv __pycache__ .pytest_cache /XF *.pyc | Out-Null
if ($LASTEXITCODE -gt 7) {
    throw "robocopy failed while staging mcp_server with exit code $LASTEXITCODE"
}
Copy-Item -LiteralPath (Join-Path $repoRoot "scripts") -Destination (Join-Path $packageRoot "scripts") -Recurse
Copy-Item -LiteralPath (Join-Path $repoRoot "README.md") -Destination (Join-Path $packageRoot "README.md")

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath
Write-Host "Created $zipPath"

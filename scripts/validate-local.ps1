param(
    [string]$BalatroPath = "D:\SteamLibrary\steamapps\common\Balatro",
    [int]$Port = 8080,
    [switch]$SkipGameLaunch,
    [switch]$LaunchGame,
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$appData = [Environment]::GetFolderPath("ApplicationData")
$modsDir = Join-Path (Join-Path $appData "Balatro") "Mods"
$targetMod = Join-Path $modsDir "BalatroMCP"
$healthUrl = "http://127.0.0.1:$Port/health"
$defaultHealthUrl = "http://127.0.0.1:8080/health"

function Assert-Path {
    param([string]$Path, [string]$Message)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw $Message
    }
}

function Test-Health {
    param([int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 2
            if ($response.ok -eq $true -and $response.data.service -eq "balatro-mcp") {
                Write-Host "Balatro MCP health OK: $($response.data.service)"
                return $true
            } elseif ($response.ok -eq $true) {
                Write-Host "Ignoring non Balatro MCP service on port ${Port}: $($response.data.service)"
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

Assert-Path -Path $repoRoot -Message "Repository root not found."
Assert-Path -Path (Join-Path $repoRoot "mods\BalatroMCP\BalatroMCP.json") -Message "BalatroMCP manifest missing."
Assert-Path -Path (Join-Path $repoRoot "mcp_server\pyproject.toml") -Message "MCP pyproject missing."
Assert-Path -Path $BalatroPath -Message "Balatro path not found: $BalatroPath"
Assert-Path -Path (Join-Path $BalatroPath "Balatro.exe") -Message "Balatro.exe not found."

if (Test-Path -LiteralPath $targetMod) {
    Write-Host "Installed mod found: $targetMod"
} else {
    Write-Warning "Installed mod not found in AppData Mods: $targetMod"
}

if ($SkipGameLaunch) {
    Write-Host "SkipGameLaunch set; optional probe uses $healthUrl. Default endpoint is $defaultHealthUrl."
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 1
        if ($response.ok -eq $true -and $response.data.service -eq "balatro-mcp") {
            Write-Host "Balatro MCP health OK: $($response.data.service)"
        } elseif ($response.ok -eq $true) {
            Write-Host "Health endpoint responded but is not balatro-mcp: $($response.data.service)"
        }
    } catch {
        Write-Host "Health endpoint not reachable during skipped launch validation."
    }
    exit 0
}

if ($LaunchGame) {
    $exe = Join-Path $BalatroPath "Balatro.exe"
    Write-Host "Launching Balatro from $exe"
    $env:BALATRO_MCP_PORT = "$Port"
    Start-Process -FilePath $exe -WorkingDirectory $BalatroPath | Out-Null
}

if (-not (Test-Health -TimeoutSeconds $TimeoutSeconds)) {
    throw "Health endpoint did not become ready: $healthUrl"
}

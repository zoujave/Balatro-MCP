param([string]$BalatroPath = "D:\SteamLibrary\steamapps\common\Balatro")
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceMod = (Resolve-Path -LiteralPath (Join-Path $repoRoot "mods\BalatroMCP")).Path
$modsDir = Join-Path ([Environment]::GetFolderPath("ApplicationData")) "Balatro\Mods"
$targetMod = Join-Path $modsDir "BalatroMCP"
if (-not (Test-Path -LiteralPath (Join-Path $BalatroPath "Balatro.exe"))) { throw "Balatro.exe missing in $BalatroPath" }
if (-not (Test-Path -LiteralPath (Join-Path $sourceMod "BalatroMCP.json"))) { throw "Mod manifest missing" }
New-Item -ItemType Directory -Force -Path $modsDir | Out-Null
if (Test-Path -LiteralPath $targetMod) {
    $existing = Get-Item -LiteralPath $targetMod -Force
    if ($existing.LinkType -eq "Junction" -and [string]$existing.Target -eq $sourceMod) {
        Write-Host "Development junction already installed: $targetMod -> $sourceMod"
        exit 0
    }
    throw "Existing mod found at $targetMod. Back it up outside Mods before installing a development junction."
}
New-Item -ItemType Junction -Path $targetMod -Target $sourceMod | Out-Null
Write-Host "Development junction installed: $targetMod -> $sourceMod"
Write-Host "Restart Balatro after editing Lua files."

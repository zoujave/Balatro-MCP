param(
    [string]$BalatroPath = "D:\SteamLibrary\steamapps\common\Balatro",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourceMod = Join-Path $repoRoot "mods\BalatroMCP"
$appData = [Environment]::GetFolderPath("ApplicationData")
$balatroAppData = Join-Path $appData "Balatro"
$modsDir = Join-Path $balatroAppData "Mods"
$targetMod = Join-Path $modsDir "BalatroMCP"
$legacyMod = Join-Path $modsDir "BalatroAgent"

if (-not (Test-Path -LiteralPath $BalatroPath)) {
    throw "Balatro path not found: $BalatroPath"
}

$balatroExe = Join-Path $BalatroPath "Balatro.exe"
if (-not (Test-Path -LiteralPath $balatroExe)) {
    throw "Balatro.exe not found in: $BalatroPath"
}

if (-not (Test-Path -LiteralPath $sourceMod)) {
    throw "Source mod folder not found: $sourceMod"
}

New-Item -ItemType Directory -Force -Path $modsDir | Out-Null

if (Test-Path -LiteralPath $targetMod) {
    if (-not $Force) {
        Write-Host "Replacing existing BalatroMCP mod at $targetMod"
    }
    $resolvedTarget = (Resolve-Path -LiteralPath $targetMod).Path
    if ($resolvedTarget -notlike "$modsDir*") {
        throw "Refusing to remove unexpected path: $resolvedTarget"
    }
    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
}

if (Test-Path -LiteralPath $legacyMod) {
    $resolvedLegacy = (Resolve-Path -LiteralPath $legacyMod).Path
    if ($resolvedLegacy -notlike "$modsDir*") {
        throw "Refusing to remove unexpected legacy path: $resolvedLegacy"
    }
    Remove-Item -LiteralPath $resolvedLegacy -Recurse -Force
    Write-Host "Removed legacy BalatroAgent mod at $resolvedLegacy"
}

Copy-Item -LiteralPath $sourceMod -Destination $targetMod -Recurse -Force

$lovelyDll = Join-Path $BalatroPath "winmm.dll"
$legacyLovelyDll = Join-Path $BalatroPath "version.dll"
if (-not ((Test-Path -LiteralPath $lovelyDll) -or (Test-Path -LiteralPath $legacyLovelyDll))) {
    Write-Warning "Lovely is not installed. Expected winmm.dll (Lovely 0.10+) or version.dll in $BalatroPath"
}

$steamodded = Get-ChildItem -LiteralPath $modsDir -Directory -ErrorAction SilentlyContinue |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName "manifest.json")) -or
        (Test-Path -LiteralPath (Join-Path $_.FullName "Steamodded.json")) -or
        $_.Name -match "smods|Steamodded"
    } |
    Select-Object -First 1

if (-not $steamodded) {
    Write-Warning "Steamodded/smods was not found in $modsDir. Install it before launching the mod."
}

Write-Host "Installed BalatroMCP to $targetMod"
Write-Host "AppData Mods directory: $modsDir"

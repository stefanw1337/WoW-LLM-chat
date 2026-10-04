param([Parameter(Mandatory=$true)][string]$WowDirectory)
$ErrorActionPreference = 'Stop'
$wowRoot = (Resolve-Path -LiteralPath $WowDirectory).Path
if (-not (Test-Path -LiteralPath (Join-Path $wowRoot 'Interface') -PathType Container)) {
    throw 'Select the WoW client folder that contains the Interface folder.'
}
if (Get-Process -Name Wow,Ascension -ErrorAction SilentlyContinue) {
    throw 'Close WoW before installing. New addon folders are discovered when the game next starts.'
}
$addonRoot = Join-Path $wowRoot 'Interface/AddOns'
$null = New-Item -ItemType Directory -Path $addonRoot -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Addon/WoWLLMChat') -Destination $addonRoot -Recurse -Force
for ($slot = 1; $slot -le 2048; $slot++) {
    $name = 'WoWLLMChat_S{0:D4}' -f $slot
    $slotPath = Join-Path $addonRoot $name
    $null = New-Item -ItemType Directory -Path $slotPath -Force
    $toc = "## Interface: 30300`n## Title: WoW LLM reply $slot`n## LoadOnDemand: 1`n## Dependencies: WoWLLMChat`nReply.lua`n"
    [IO.File]::WriteAllText((Join-Path $slotPath "$name.toc"), $toc)
    [IO.File]::WriteAllText((Join-Path $slotPath 'Reply.lua'), '-- Awaiting local LM Studio response.')
}
$configPath = Join-Path $PSScriptRoot 'bridge/config.json'
if (Test-Path -LiteralPath $configPath) {
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
} else {
    $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bridge/config.example.json') -Raw | ConvertFrom-Json
}
$config.wow_directory = $wowRoot
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-Host "Installed in $addonRoot. Restart WoW and enable WoW LLM Chat and its reply addons."

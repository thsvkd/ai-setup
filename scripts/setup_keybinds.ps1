<#
.SYNOPSIS
    줄바꿈 키바인딩 설치 워커 (Windows).
.DESCRIPTION
    scripts/setup.ps1 이 -Keybinds 로 호출한다. 실제 병합은 res/keybinds/apply.py.
.USAGE
    powershell -ExecutionPolicy Bypass -File setup_keybinds.ps1
    powershell -ExecutionPolicy Bypass -File setup_keybinds.ps1 -Newline ctrl-enter
    powershell -ExecutionPolicy Bypass -File setup_keybinds.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File setup_keybinds.ps1 -Uninstall
#>

param(
    [switch]$DryRun,
    [switch]$Uninstall,
    [string]$Newline = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\SetupCommon.ps1")

# 값이 비었는지가 아니라 '인자가 주어졌는지' 로 판정한다 — -Newline "" 도 잘못된 값이다.
if ($PSBoundParameters.ContainsKey("Newline") -and $Newline -notin @("shift-enter", "ctrl-enter")) {
    Write-Host "--Newline 값은 shift-enter 또는 ctrl-enter 여야 합니다 (받은 값: $Newline)." -ForegroundColor Red
    exit 1
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$apply = Join-Path $RepoRoot "res\keybinds\apply.py"
if (-not (Test-Path $apply)) {
    Write-Host "❌ 키바인드 스크립트를 찾을 수 없습니다: $apply" -ForegroundColor Red
    exit 1
}

$py = Resolve-PythonCommand
if (-not $py) {
    Write-Host "❌ Python을 찾을 수 없습니다." -ForegroundColor Red
    exit 1
}

$homeDir = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$pyArgs = @("-X", "utf8", $apply, "--home", $homeDir)
if ($DryRun) { $pyArgs += "--dry-run" }
if ($Uninstall) { $pyArgs += "--uninstall" }
if ($Newline) { $pyArgs += @("--newline", $Newline) }

& $py.Exe @($py.Args) @pyArgs
exit $LASTEXITCODE

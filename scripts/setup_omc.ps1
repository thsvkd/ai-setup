<#
.SYNOPSIS
    oh-my-claudecode(OMC) 설치 워커 (Windows).
.DESCRIPTION
    scripts/setup.ps1 이 -Omc 로 호출한다. 플러그인은 claude CLI 로 설치하고,
    HUD 에 캐시 TTL 을 띄우는 statusLine 설정은 res/omc/apply.py 가 한다.
.USAGE
    powershell -ExecutionPolicy Bypass -File setup_omc.ps1
    powershell -ExecutionPolicy Bypass -File setup_omc.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File setup_omc.ps1 -Uninstall   # 캐시 TTL HUD 설정만 되돌린다
#>

param(
    [switch]$DryRun,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "lib\SetupCommon.ps1")

$OmcMarketplaceRepo = "Yeachan-Heo/oh-my-claudecode"
$OmcPlugin = "oh-my-claudecode@omc"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$apply = Join-Path $RepoRoot "res\omc\apply.py"

$py = Resolve-PythonCommand
if (-not $py) {
    Write-Host "❌ Python을 찾을 수 없습니다." -ForegroundColor Red
    Write-PythonInstallHint
    exit 1
}

$homeDir = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$pyArgs = @("-X", "utf8", $apply, "--home", $homeDir)
if ($DryRun) { $pyArgs += "--dry-run" }

if ($Uninstall) {
    & $py.Exe @($py.Args) @pyArgs --uninstall
    exit $LASTEXITCODE
}

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "❌ claude CLI 를 찾을 수 없습니다. Claude Code 를 먼저 설치하세요." -ForegroundColor Red
    exit 1
}

function Invoke-Step([string[]]$CliArgs) {
    if ($DryRun) {
        Write-Host "  • (dry-run) claude $($CliArgs -join ' ')"
        return
    }
    & claude @CliArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Windows PowerShell 5.1 은 Stop 아래에서 네이티브 명령의 stderr 리디렉션을 종료 오류로 승격한다.
# 목록 조회는 실패해도 '미설치' 로 보고 진행하면 되므로 이 구간만 Continue 로 읽는다.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$plugins = & claude plugin list 2>$null | Out-String
$marketplaces = & claude plugin marketplace list 2>$null | Out-String
$ErrorActionPreference = $prevEap

Write-Host "── OMC 플러그인 ────────────────────────"
if ($plugins -match "oh-my-claudecode@") {
    Write-Host "  • 이미 설치됨: $OmcPlugin"
} else {
    if ($marketplaces -notmatch [regex]::Escape($OmcMarketplaceRepo)) {
        Invoke-Step @("plugin", "marketplace", "add", $OmcMarketplaceRepo)
    }
    Invoke-Step @("plugin", "install", $OmcPlugin)
}

Write-Host "── OMC HUD (캐시 TTL) ──────────────────"
& $py.Exe @($py.Args) @pyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "  ℹ️  CLAUDE.md 등 OMC 의 나머지 설정은 Claude Code 안에서 /oh-my-claudecode:omc-setup 으로 진행하세요."
Write-Host "     그 과정에서 statusLine 이 다시 써지면 이 스크립트를 한 번 더 실행하면 됩니다."
exit 0

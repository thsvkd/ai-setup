<#
.SYNOPSIS
    Claude Code 사용자 레벨 설정 CLI 엔트리포인트 (Windows)
.DESCRIPTION
    인자 없이 실행하면 훅/권한 설정(setup_hooks.ps1)과 AGENTS.md 설치(setup_agentsmd.ps1)를
    모두 실행합니다. -Hooks 또는 -AgentsMd 를 지정하면 지정한 것만 실행합니다.
.USAGE
    powershell -ExecutionPolicy Bypass -File setup.ps1                       # 전체 실행
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Hooks                # 훅/권한만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -AgentsMd             # AGENTS.md만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -DryRun               # 미리보기 (전체)
#>

param(
    [switch]$Hooks,
    [switch]$AgentsMd,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$runAll = -not ($Hooks -or $AgentsMd)

if ($runAll -or $Hooks) {
    & (Join-Path $PSScriptRoot "setup_hooks.ps1") -DryRun:$DryRun
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($runAll -or $AgentsMd) {
    & (Join-Path $PSScriptRoot "setup_agentsmd.ps1") -DryRun:$DryRun
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

exit 0

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
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host @"
claude-code-setup — Claude Code 사용자 레벨 설정

사용법: .\setup.ps1 [옵션]
  (옵션 없음)   가드/권한 + AGENTS.md 모두 설치
  -Hooks        전역 가드 훅 + 권한만 설치 (~/.claude)
  -AgentsMd     현재 폴더에 AGENTS.md 만 설치
  -Uninstall    가드 훅 제거 + settings.json 등록 해제 (권한은 보존)
  -DryRun       아무것도 바꾸지 않고 변경 계획만 출력
  -Help         이 도움말
"@
    exit 0
}

# uninstall 은 훅 전용 (프로젝트 AGENTS.md 는 사용자 콘텐츠라 건드리지 않음).
if ($Uninstall) {
    & (Join-Path $PSScriptRoot "setup_hooks.ps1") -Uninstall -DryRun:$DryRun
    exit $LASTEXITCODE
}

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

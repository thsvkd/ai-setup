<#
.SYNOPSIS
    res/AGENTS.md 를 현재 작업 디렉터리(대상 프로젝트 루트로 가정)에 설치 (Windows)
.DESCRIPTION
    이미 대상 프로젝트에 AGENTS.md 가 있으면 덮어쓰지 않고 건너뜁니다 — 이 파일은
    프로젝트별로 커스터마이징되는 것을 전제하기 때문에, settings.json 처럼 정교한
    외과적 병합을 하지 않고 "없을 때만 설치"라는 단순한 정책을 씁니다.

    이 스크립트는 scripts/setup.ps1 디스패처가 -AgentsMd 로 호출하는 워커입니다.
    프로젝트 루트에서 직접 실행할 수도 있습니다.
.USAGE
    powershell -ExecutionPolicy Bypass -File setup_agentsmd.ps1              # 실제 설치
    powershell -ExecutionPolicy Bypass -File setup_agentsmd.ps1 -DryRun      # 미리보기만
#>

param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $RepoRoot "res\AGENTS.md"
$Target = Join-Path (Get-Location).Path "AGENTS.md"

Write-Host "🔧 AGENTS.md 설치..." -ForegroundColor Cyan

if (-not (Test-Path $Source)) {
    Write-Error "❌ 소스 파일을 찾을 수 없습니다: $Source"
    exit 1
}

if (Test-Path $Target) {
    Write-Host "  ℹ️ 이미 $Target 가 존재합니다 — 덮어쓰지 않고 건너뜁니다." -ForegroundColor DarkGray
} elseif ($DryRun) {
    Write-Host "  🧪 DRY RUN — $Target 에 설치될 예정입니다 (실제로 쓰지 않음)." -ForegroundColor Magenta
} else {
    Copy-Item -Path $Source -Destination $Target
    Write-Host "  ✅ 설치 완료: $Target" -ForegroundColor Green
}

exit 0

<#
.SYNOPSIS
    Claude Code 사용자 레벨 설정 CLI 엔트리포인트 (Windows)
.DESCRIPTION
    인자 없이 실행하면 대화형 온보딩(res/onboard.py)이 떠서 설치 범위·권한 모드 등을
    고르게 합니다. 플래그를 하나라도 주면 사용자가 이미 뜻을 밝힌 것이므로 온보딩을
    건너뛰고 예전과 똑같이 동작합니다. 온보딩을 띄울 수 없는 환경(콘솔 없음/CI)에서도
    예전 기본값(훅+권한 설치 + AGENTS.md 설치)으로 그대로 진행합니다.
.USAGE
    powershell -ExecutionPolicy Bypass -File setup.ps1                       # 온보딩 → 선택대로
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Hooks                # 훅/권한만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -AgentsMd             # AGENTS.md만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -DryRun               # 미리보기 (전체)
    powershell -ExecutionPolicy Bypass -File setup.ps1 -NoOnboard            # 온보딩 끄기
#>

param(
    [switch]$Hooks,
    [switch]$AgentsMd,
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$NoOnboard,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# PS 7.4+ 는 네이티브 명령의 0이 아닌 종료 코드를 종료 오류로 승격시킬 수 있다 ($true 가 기본인
# 빌드/프로필이 있음). 이 스크립트들은 실패를 $LASTEXITCODE 로 직접 판정하므로 명시적으로 끈다.
$PSNativeCommandUseErrorActionPreference = $false

if ($Help) {
    Write-Host @"
claude-code-setup — Claude Code 사용자 레벨 설정

사용법: .\setup.ps1 [옵션]
  (옵션 없음)   대화형 온보딩으로 설치 범위/권한 모드를 고른 뒤 실행
  -Hooks        전역 가드 훅 + 권한만 설치 (~/.claude)
  -AgentsMd     현재 폴더에 AGENTS.md 만 설치
  -Uninstall    가드 훅 제거 + settings.json 등록 해제 (권한은 보존)
  -DryRun       아무것도 바꾸지 않고 변경 계획만 출력
  -NoOnboard    대화형 온보딩을 띄우지 않고 기본값으로 실행
  -Help         이 도움말

온보딩에서 고를 수 있는 것:
  · 설치 범위 (전체 / 가드 훅+권한만 / AGENTS.md만)
  · 권한 모드 (auto / bypassPermissions)
  · 기존 AGENTS.md 덮어쓰기 여부 (파일이 이미 있을 때만 물음)
  · 지금 적용할지, 변경 계획(-DryRun)만 먼저 볼지
"@
    exit 0
}

$RepoRoot = Split-Path -Parent $PSScriptRoot

# 온보딩이 채우는 값들. 비어 있으면 워커가 각자의 기본값을 쓴다.
$defaultMode = ""
$forceAgentsMd = $false
$runHooks = [bool]$Hooks
$runAgentsMd = [bool]$AgentsMd
$dryRun = [bool]$DryRun

function Resolve-PythonForOnboard {
    # Get-Command 존재만으로는 부족하다. Windows 에서 `py` 가 런처가 아니라 python.exe
    # 자체이면 `py -3` 이 "Unknown option: -3" 을 stderr 로 내고, PS 5.1 은 그걸
    # NativeCommandError 로 승격시켜 설치가 죽는다. 각 후보를 실제로 실행해 3.8+ 인지
    # 확인하고, 실패하면 다음 후보로 넘어간다. 순서는 SetupCommon.Resolve-PythonCommand
    # 와 같다 (python → python3 → py -3 → py).
    $candidates = @(
        @{ Exe = "python";  Args = @() },
        @{ Exe = "python3"; Args = @() },
        @{ Exe = "py";      Args = @("-3") },
        @{ Exe = "py";      Args = @() }   # 런처가 아닌 py.exe (= CPython) 는 -3 을 모른다
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
        $ok = $false
        try {
            & $c.Exe @($c.Args) -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" *> $null
            $ok = ($LASTEXITCODE -eq 0)
        } catch {
            $ok = $false
        }
        if ($ok) { return $c }
    }
    return $null
}

# 온보딩 종료 코드: 0=선택 완료, 2=대화형 불가(콘솔 없음/CI), 130=사용자 취소.
# 2 와 130 을 구분하는 게 중요하다 — 2 는 "물어볼 수 없었다"라서 예전 기본값으로 계속
# 진행해야 하고, 130 은 사용자가 명시적으로 거부한 것이라 아무것도 설치하면 안 된다.
function Invoke-Onboarding {
    $onboard = Join-Path $RepoRoot "res\onboard.py"
    if (-not (Test-Path $onboard)) { return $null }

    $py = Resolve-PythonForOnboard
    if (-not $py) { return $null }

    $answersPath = [System.IO.Path]::GetTempFileName()
    try {
        & $py.Exe @($py.Args) -X utf8 $onboard --out $answersPath --project-dir (Get-Location).Path
        $status = $LASTEXITCODE

        if ($status -eq 130) { exit 130 }
        if ($status -ne 0) { return $null }   # 대화형 불가 — 예전 기본값 그대로

        # Invoke-Expression 대신 한 줄씩 읽어 아는 키만 받는다.
        $parsed = @{}
        foreach ($line in (Get-Content $answersPath -Encoding UTF8)) {
            $pair = $line -split "=", 2
            if ($pair.Count -eq 2) { $parsed[$pair[0]] = $pair[1] }
        }
        return $parsed
    } finally {
        Remove-Item $answersPath -Force -ErrorAction SilentlyContinue
    }
}

$hadArgs = $Hooks -or $AgentsMd -or $Uninstall -or $DryRun -or $NoOnboard
if (-not $hadArgs) {
    $answers = Invoke-Onboarding
    if ($answers) {
        switch ($answers["SCOPE"]) {
            "all"      { $runHooks = $true; $runAgentsMd = $true }
            "hooks"    { $runHooks = $true }
            "agentsmd" { $runAgentsMd = $true }
        }
        if ($answers.ContainsKey("DEFAULT_MODE") -and
            $answers["DEFAULT_MODE"] -in @("auto", "bypassPermissions", "default", "acceptEdits", "plan")) {
            $defaultMode = $answers["DEFAULT_MODE"]
        }
        if ($answers["OVERWRITE_AGENTSMD"] -eq "1") { $forceAgentsMd = $true }
        if ($answers["DRY_RUN"] -eq "1") { $dryRun = $true }
    }
}

# uninstall 은 훅 전용 (프로젝트 AGENTS.md 는 사용자 콘텐츠라 건드리지 않음).
if ($Uninstall) {
    & (Join-Path $PSScriptRoot "setup_hooks.ps1") -Uninstall -DryRun:$dryRun
    exit $LASTEXITCODE
}

if (-not ($runHooks -or $runAgentsMd)) {
    $runHooks = $true
    $runAgentsMd = $true
}

if ($runHooks) {
    & (Join-Path $PSScriptRoot "setup_hooks.ps1") -DryRun:$dryRun -DefaultMode $defaultMode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($runAgentsMd) {
    & (Join-Path $PSScriptRoot "setup_agentsmd.ps1") -DryRun:$dryRun -Force:$forceAgentsMd
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

exit 0

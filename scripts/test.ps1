<#
.SYNOPSIS
    전체 테스트 스위트 실행 (Windows)
.DESCRIPTION
    이 저장소는 서로 다른 러너 세 개로 테스트한다 — pytest(훅 정책·git 실측·병합 엔진·셋업
    스크립트), Pester(PowerShell 셋업 스크립트), bats(bash 셋업 스크립트, Git Bash 에 있으면).
    러너마다 설치 여부가 달라서, 하나가 없다고 전체가 멈추거나 반대로 "없어서 안 돌았는데
    통과처럼 보이는" 일이 없도록 통과/실패/건너뜀을 구분해 마지막에 한 번에 보고한다.

    첫 실패에서 멈추지 않고 가능한 스위트를 전부 돌린다. 종료 코드는 '실행된' 스위트 중
    하나라도 실패하면 1이다. 하나도 실행하지 못한 경우도 1이다 — 아무것도 검증되지 않은
    상태를 통과로 보고하면 안 되기 때문이다.
.USAGE
    powershell -ExecutionPolicy Bypass -File scripts\test.ps1                  # 전부 실행
    powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -PythonOnly      # pytest 만
    powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -Strict          # 건너뜀도 실패 취급
    powershell -ExecutionPolicy Bypass -File scripts\test.ps1 -PytestArgs '-k','git_guard'
#>

param(
    [switch]$PythonOnly,
    [switch]$Strict,
    [string[]]$PytestArgs = @(),
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# PS 7.4+ 는 네이티브 명령의 0이 아닌 종료 코드를 종료 오류로 승격시킬 수 있다. 이 스크립트는
# 각 러너의 실패를 $LASTEXITCODE 로 직접 판정하고 계속 진행해야 하므로 명시적으로 끈다.
$PSNativeCommandUseErrorActionPreference = $false

if ($Help) {
    Write-Host @"
claude-code-setup — 테스트 스위트 실행

사용법: .\test.ps1 [옵션]
  (옵션 없음)    설치된 러너로 pytest + Pester + bats 전부 실행
  -PythonOnly    pytest 만 실행
  -Strict        러너 미설치로 건너뛴 스위트도 실패로 취급 (종료 코드 1)
  -PytestArgs    pytest 에 그대로 전달할 인자 배열 (예: -PytestArgs '-k','git_guard')
  -Help          이 도움말
"@
    exit 0
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$suites = [System.Collections.ArrayList]::new()

function Add-Result([string]$Name, [string]$State, [string]$Note) {
    [void]$suites.Add([pscustomobject]@{ Name = $Name; State = $State; Note = $Note })
}

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host "── $Title ─────────────────────────────────────"
}

function Resolve-PytestPython {
    # SetupCommon.ps1 의 Resolve-PythonCommand 는 '아무 python' 이면 되지만(병합 스크립트용),
    # 테스트 러너는 'pytest 가 설치된 python' 이 필요하다 — 요구사항이 다르다. 한 머신에
    # python 이 여러 개 깔려 있고 그중 일부에만 pytest 가 있는 경우가 흔해서, 첫 번째로 찾은
    # python 을 그냥 쓰면 "pytest 미설치" 로 오판한다.
    $PSNativeCommandUseErrorActionPreference = $false
    $candidates = @(
        @{ Exe = "python";  Args = @() },
        @{ Exe = "python3"; Args = @() },
        @{ Exe = "py";      Args = @("-3") }
    )
    foreach ($c in $candidates) {
        if (Get-Command $c.Exe -ErrorAction SilentlyContinue) {
            & $c.Exe @($c.Args) -c "import pytest" *> $null
            if ($LASTEXITCODE -eq 0) { return $c }
        }
    }
    return $null
}

function Test-AnyPython {
    $PSNativeCommandUseErrorActionPreference = $false
    foreach ($exe in @("python", "python3", "py")) {
        if (Get-Command $exe -ErrorAction SilentlyContinue) { return $true }
    }
    return $false
}

# --- pytest: 이 저장소의 핵심 스위트 ---
Write-Section "pytest"
$py = Resolve-PytestPython
if ($null -eq $py) {
    if (Test-AnyPython) {
        Write-Host "python 은 있으나 pytest 가 설치돼 있지 않습니다. (python -m pip install pytest)"
        Add-Result "pytest" "skip" "pytest 미설치"
    } else {
        Write-Host "python 을 찾지 못했습니다."
        Add-Result "pytest" "skip" "python 없음"
    }
} else {
    Write-Host "인터프리터: $($py.Exe) $($py.Args -join ' ')"
    # -rs: 스킵된 테스트의 '사유'까지 출력한다. 이 저장소의 스킵은 환경 조건부라
    # (macOS 전용 경로, 3.9.x 인터프리터 유무) 무엇이 검증되지 '않았는지' 보이는 게 중요하다.
    & $py.Exe @($py.Args) -m pytest (Join-Path $repoRoot "tests") -rs @PytestArgs
    if ($LASTEXITCODE -eq 0) { Add-Result "pytest" "pass" "" } else { Add-Result "pytest" "fail" "" }
}

if ($PythonOnly) {
    # -PythonOnly 는 '요청하지 않은' 것이므로 아예 기록하지 않는다 — 러너가 없어서 못 돌린
    # skip 과 섞이면 -Strict 가 사용자가 직접 고른 선택까지 실패로 만든다.
    Write-Host ""
    Write-Host "(-PythonOnly: Pester/bats 는 요청되지 않아 실행하지 않습니다)"
} else {
    # --- Pester: PowerShell 셋업 스크립트. Windows 훅의 PS 경로를 실제로 실행하는 유일한 스위트 ---
    Write-Section "Pester"
    if (-not (Get-Module -ListAvailable -Name Pester)) {
        Write-Host "Pester 모듈이 없어 건너뜁니다. (Install-Module Pester -Scope CurrentUser)"
        Add-Result "Pester (Setup.Tests.ps1)" "skip" "Pester 미설치"
    } else {
        $result = Invoke-Pester (Join-Path $repoRoot "tests\Setup.Tests.ps1") -Output Detailed -PassThru
        if ($result.FailedCount -eq 0) {
            Add-Result "Pester (Setup.Tests.ps1)" "pass" ""
        } else {
            Add-Result "Pester (Setup.Tests.ps1)" "fail" ""
        }
    }

    # --- bats: bash 셋업 스크립트. Git for Windows 의 Git Bash 에 bats 가 있으면 돌린다 ---
    Write-Section "bats"
    $bash = Get-Command bash -ErrorAction SilentlyContinue
    if (-not $bash) {
        Write-Host "bash 가 없어 건너뜁니다. (Git for Windows 미설치)"
        Add-Result "bats (setup.bats)" "skip" "bash 없음"
    } else {
        & bash -lc "command -v bats" *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "bats 가 없어 건너뜁니다. (npm i -g bats)"
            Add-Result "bats (setup.bats)" "skip" "bats 미설치"
        } else {
            # Windows 경로를 그대로 넘기면 Git Bash 가 해석하지 못하므로 POSIX 경로로 바꾼다.
            $batsPath = (Join-Path $repoRoot "tests/setup.bats") -replace '\\', '/'
            & bash -lc "bats '$batsPath'"
            if ($LASTEXITCODE -eq 0) { Add-Result "bats (setup.bats)" "pass" "" } else { Add-Result "bats (setup.bats)" "fail" "" }
        }
    }
}

# --- 종합 리포트 ---
Write-Host ""
Write-Host "══ 결과 ═══════════════════════════════════════"
$failed = 0
$skipped = 0
$ran = 0
foreach ($s in $suites) {
    switch ($s.State) {
        "pass" { Write-Host ("  [PASS] {0,-26} 통과" -f $s.Name); $ran++ }
        "fail" { Write-Host ("  [FAIL] {0,-26} 실패" -f $s.Name); $failed++; $ran++ }
        "skip" { Write-Host ("  [SKIP] {0,-26} 건너뜀 ({1})" -f $s.Name, $s.Note); $skipped++ }
    }
}

if ($skipped -gt 0) {
    Write-Host ""
    Write-Host "  건너뛴 스위트는 '통과'가 아니라 '검증 안 됨' 이다."
}

Write-Host ""
if ($failed -gt 0) {
    Write-Host "실패한 스위트: ${failed}개"
    exit 1
}
# 하나도 못 돌린 것은 통과가 아니다 — 테스트를 요청했는데 아무것도 검증되지 않은 상태다.
if ($ran -eq 0) {
    Write-Host "실행된 스위트가 없습니다. 최소한 pytest 는 돌 수 있어야 합니다."
    exit 1
}
if ($Strict -and $skipped -gt 0) {
    Write-Host "-Strict: 건너뛴 스위트 ${skipped}개를 실패로 취급합니다."
    exit 1
}
Write-Host "실행된 스위트 ${ran}개 모두 통과."
exit 0

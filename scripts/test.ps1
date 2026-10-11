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

    $env:CLAUDE_TEST_PYTHON = 'C:\path\to\python.exe'   # pytest 를 돌릴 인터프리터 지정
        venv 안이거나 pytest 가 python/python3/py 라는 이름으로 잡히지 않는 환경에서 쓴다.
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
# 이 스크립트의 출력은 한글과 박스 문자를 쓴다. 콘솔 코드페이지(예: CP949)로 인코딩되면
# '—' 처럼 그 코드페이지에 없는 글자가 '?' 로 뭉개지고, 파이프로 받는 쪽도 UTF-8 로 읽지 못한다.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if ($Help) {
    Write-Host @"
claude-code-setup — run the test suites

Usage: .\test.ps1 [options]
  (no options)   run all of pytest + Pester + bats with the installed runners
  -PythonOnly    run pytest only
  -Strict        treat suites skipped for a missing runner as failures (exit code 1)
  -PytestArgs    argument array passed to pytest as is (e.g. -PytestArgs '-k','git_guard')
  -Help          this help

Environment variables:
  CLAUDE_TEST_PYTHON   interpreter path for pytest (skips auto-detection when set)
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
    # python 을 그냥 쓰면 "pytest not installed" 로 오판한다.
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
function Invoke-PytestSuite {
    $override = $env:CLAUDE_TEST_PYTHON
    if ($override) {
        # 명시적으로 지정한 인터프리터를 쓸 수 없는 것은 '러너가 없어 건너뜀' 이 아니라 오류다.
        # 조용히 skip 하면 pytest 를 돌리라고 지정해 놓고 아무것도 안 돈 상태가 통과처럼 보인다.
        $ok = $false
        try {
            & $override -c "import pytest" *> $null
            $ok = ($LASTEXITCODE -eq 0)
        } catch { $ok = $false }
        if (-not $ok) {
            Write-Host "CLAUDE_TEST_PYTHON=$override could not import pytest."
            Add-Result "pytest" "fail" "pytest missing from the given interpreter"
            return
        }
        $py = @{ Exe = $override; Args = @() }
    } else {
        $py = Resolve-PytestPython
    }

    if ($null -eq $py) {
        if (Test-AnyPython) {
            Write-Host "python found but pytest is not installed. (python -m pip install pytest)"
            Write-Host "  (if pytest is in another interpreter, point CLAUDE_TEST_PYTHON at it.)"
            Add-Result "pytest" "skip" "pytest not installed"
        } else {
            Write-Host "python not found."
            Add-Result "pytest" "skip" "no python"
        }
        return
    }

    Write-Host "Interpreter: $($py.Exe) $($py.Args -join ' ')"
    # -rs: 스킵된 테스트의 '사유'까지 출력한다. 이 저장소의 스킵은 환경 조건부라
    # (macOS 전용 경로, 3.9.x 인터프리터 유무) 무엇이 검증되지 '않았는지' 보이는 게 중요하다.
    & $py.Exe @($py.Args) -m pytest (Join-Path $repoRoot "tests") -rs @PytestArgs
    if ($LASTEXITCODE -eq 0) { Add-Result "pytest" "pass" "" } else { Add-Result "pytest" "fail" "" }
}

Write-Section "pytest"
Invoke-PytestSuite

if ($PythonOnly) {
    # -PythonOnly 는 '요청하지 않은' 것이므로 아예 기록하지 않는다 — 러너가 없어서 못 돌린
    # skip 과 섞이면 -Strict 가 사용자가 직접 고른 선택까지 실패로 만든다.
    Write-Host ""
    Write-Host "(-PythonOnly: Pester/bats not requested, not run)"
} else {
    # --- Pester: PowerShell 셋업 스크립트. Windows 훅의 PS 경로를 실제로 실행하는 유일한 스위트 ---
    Write-Section "Pester"
    if (-not (Get-Module -ListAvailable -Name Pester)) {
        Write-Host "Pester module not found, skipping. (Install-Module Pester -Scope CurrentUser)"
        Add-Result "Pester (Setup.Tests.ps1)" "skip" "Pester not installed"
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
        Write-Host "bash not found, skipping. (Git for Windows not installed)"
        Add-Result "bats (setup.bats)" "skip" "no bash"
    } else {
        & bash -lc "command -v bats" *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "bats not found, skipping. (npm i -g bats)"
            Add-Result "bats (setup.bats)" "skip" "bats not installed"
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
Write-Host "══ Results ═══════════════════════════════════════"
$failed = 0
$skipped = 0
$ran = 0
foreach ($s in $suites) {
    switch ($s.State) {
        "pass" { Write-Host ("  [PASS] {0,-26} passed" -f $s.Name); $ran++ }
        "fail" { Write-Host ("  [FAIL] {0,-26} failed" -f $s.Name); $failed++; $ran++ }
        "skip" { Write-Host ("  [SKIP] {0,-26} skipped ({1})" -f $s.Name, $s.Note); $skipped++ }
    }
}

if ($skipped -gt 0) {
    Write-Host ""
    Write-Host "  A skipped suite is 'not verified', not 'passed'."
}

Write-Host ""
if ($failed -gt 0) {
    Write-Host "Failed suites: ${failed}"
    exit 1
}
# 하나도 못 돌린 것은 통과가 아니다 — 테스트를 요청했는데 아무것도 검증되지 않은 상태다.
if ($ran -eq 0) {
    Write-Host "No suites ran. At least pytest must be able to run."
    exit 1
}
if ($Strict -and $skipped -gt 0) {
    Write-Host "-Strict: treating ${skipped} skipped suite(s) as failures."
    exit 1
}
Write-Host "All ${ran} suite(s) that ran passed."
exit 0

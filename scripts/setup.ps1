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

[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Hooks,
    [switch]$AgentsMd,
    [switch]$Keybinds,
    [string[]]$Harness = @(),
    [string]$Newline = "",
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$NoOnboard,
    [Alias("h")]
    [switch]$Help,
    # setup.sh 와 같은 `--dry-run` 식 긴 표기를 받아내는 자리.
    #
    # PowerShell 은 이름에 하이픈이 들어간 플래그를 파라미터로 인식하지 못한다. 게다가
    # 셸에서 `setup.ps1 --help` 처럼 직접 실행하면 (`-File` 로 넘길 때와 달리) `--help`
    # 조차 파라미터가 아닌 '위치 인자' 로 들어온다. 위치 바인딩이 켜져 있으면 그게 전부
    # 첫 번째 비-스위치 파라미터인 -Newline 으로 빨려 들어가서, 도움말을 부른 사용자에게
    # "값은 shift-enter 또는 ctrl-enter 여야 합니다 (받은 값: --help)" 라는 엉뚱한 오류가
    # 나갔다. 그래서 위치 바인딩을 끄고, 남은 토큰은 여기 모아 아래에서 직접 읽는다.
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# PS 7.4+ 는 네이티브 명령의 0이 아닌 종료 코드를 종료 오류로 승격시킬 수 있다 ($true 가 기본인
# 빌드/프로필이 있음). 이 스크립트들은 실패를 $LASTEXITCODE 로 직접 판정하므로 명시적으로 끈다.
$PSNativeCommandUseErrorActionPreference = $false

function Show-Usage {
    Write-Host @"
claude-code-setup — Claude Code 사용자 레벨 설정

사용법: .\setup.ps1 [옵션]
  (옵션 없음)   대화형 온보딩으로 설치 범위/권한 모드를 고른 뒤 실행
  -Hooks        전역 가드 훅 + 권한만 설치 (~/.claude)
  -AgentsMd     현재 폴더에 프로젝트 지침만 설치
  -Harness L    지침을 설치할 하네스 (쉼표 구분: claude,codex,grok,opencode,all)
                claude 를 고르면 CLAUDE.md 도 함께 설치된다. 기본값은 all.
  -Keybinds     줄바꿈 키바인딩만 설치 (VS Code/Cursor/Claude/Codex)
  -Newline VAL  줄바꿈 키 (shift-enter | ctrl-enter). 기본 shift-enter
  -Uninstall    가드 훅 + 관리 키바인딩 제거 (권한·사용자 항목은 보존)
  -DryRun       아무것도 바꾸지 않고 변경 계획만 출력
  -NoOnboard    대화형 온보딩을 띄우지 않고 기본값으로 실행
  -Help         이 도움말

온보딩에서 고를 수 있는 것:
  · 설치 범위 (전체 / 가드 훅+권한만 / AGENTS.md만)
  · 권한 모드 (auto / bypassPermissions)
  · 줄바꿈 키 (Shift+Enter / Ctrl+Enter) — 범위=전체일 때만
  · 기존 AGENTS.md 덮어쓰기 여부 (파일이 이미 있을 때만 물음)
  · 지금 적용할지, 변경 계획(-DryRun)만 먼저 볼지

setup.sh 와 같은 긴 표기도 그대로 받습니다:
  --hooks  --agentsmd  --harness L  --keybinds  --newline VAL  --uninstall  --dry-run
  --no-onboard  --help
"@
}

# param 블록의 $Rest 로 흘러든 토큰을 setup.sh 와 같은 규칙으로 해석한다. 조용히 버리면
# 오타(--keybind)가 '전체 설치' 로 둔갑하므로, 모르는 것은 사용법과 함께 거절한다.
$newlineGiven = $PSBoundParameters.ContainsKey("Newline")
$harnessGiven = $PSBoundParameters.ContainsKey("Harness")
$unknownArgs = @()
for ($i = 0; $i -lt $Rest.Count; $i++) {
    switch -Regex ($Rest[$i]) {
        '^(--help|-help|/[?h])$' { $Help = $true }
        '^--hooks$'              { $Hooks = $true }
        '^--agents-?md$'         { $AgentsMd = $true }
        '^--keybinds$'           { $Keybinds = $true }
        '^--uninstall$'          { $Uninstall = $true }
        '^--dry-run$'            { $DryRun = $true }
        '^--no-onboard$'         { $NoOnboard = $true }
        '^--newline=(.*)$'       { $Newline = $Matches[1]; $newlineGiven = $true }
        '^--harness=(.*)$'       { $Harness = @($Matches[1]); $harnessGiven = $true }
        '^--harness$' {
            $harnessGiven = $true
            $Harness = if ($i + 1 -lt $Rest.Count) { @($Rest[++$i]) } else { @("") }
        }
        '^--newline$' {
            # 값이 없으면 빈 문자열로 둬서 아래 검증에 걸리게 한다 (--newline "" 도 오류다).
            $newlineGiven = $true
            $Newline = if ($i + 1 -lt $Rest.Count) { $Rest[++$i] } else { "" }
        }
        default { $unknownArgs += $Rest[$i] }
    }
}

if ($Help) {
    Show-Usage
    exit 0
}

if ($unknownArgs.Count -gt 0) {
    Write-Host "알 수 없는 옵션: $($unknownArgs -join ' ')" -ForegroundColor Red
    Write-Host ""
    Show-Usage
    exit 1
}

$RepoRoot = Split-Path -Parent $PSScriptRoot

# 온보딩이 채우는 값들. 비어 있으면 워커가 각자의 기본값을 쓴다.
$defaultMode = ""
$forceAgentsMd = $false
$runHooks = [bool]$Hooks
$runAgentsMd = [bool]$AgentsMd
$runKeybinds = [bool]$Keybinds
$dryRun = [bool]$DryRun
$newlineChord = $Newline
$harnesses = $Harness

if ($newlineGiven -and $newlineChord -notin @("shift-enter", "ctrl-enter")) {
    Write-Host "-Newline (--newline) 값은 shift-enter 또는 ctrl-enter 여야 합니다 (받은 값: $newlineChord)." -ForegroundColor Red
    exit 1
}

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

$hadArgs = $Hooks -or $AgentsMd -or $Keybinds -or $Uninstall -or $DryRun -or $NoOnboard -or $newlineGiven -or $harnessGiven
if (-not $hadArgs) {
    $answers = Invoke-Onboarding
    if ($answers) {
        switch ($answers["SCOPE"]) {
            "all"      { $runHooks = $true; $runAgentsMd = $true; $runKeybinds = $true }
            "hooks"    { $runHooks = $true }
            "agentsmd" { $runAgentsMd = $true }
        }
        if ($answers.ContainsKey("DEFAULT_MODE") -and
            $answers["DEFAULT_MODE"] -in @("auto", "bypassPermissions", "default", "acceptEdits", "plan")) {
            $defaultMode = $answers["DEFAULT_MODE"]
        }
        if ($answers.ContainsKey("NEWLINE_CHORD") -and
            $answers["NEWLINE_CHORD"] -in @("shift-enter", "ctrl-enter") -and
            -not $newlineGiven) {
            $newlineChord = $answers["NEWLINE_CHORD"]
        }
        # onboard.py writes a controlled set, but a stray value must not reach
        # the worker, whose ValidateSet-free parameter would pass it through.
        if ($answers.ContainsKey("HARNESSES") -and
            $answers["HARNESSES"] -match "^[a-z,-]+$" -and
            -not $harnessGiven) {
            $harnesses = $answers["HARNESSES"] -split ","
        }
        if ($answers["OVERWRITE_AGENTSMD"] -eq "1") { $forceAgentsMd = $true }
        if ($answers["DRY_RUN"] -eq "1") { $dryRun = $true }
    }
}

# 제거도 설치와 같은 범위 규칙을 따른다. 범위를 지정했으면 그것만 지운다 —
# -Hooks -Uninstall 이 키바인딩까지 지우면 "-Hooks 는 키바인딩을 건드리지 않는다"
# (핵심 결정 4)를 제거 쪽에서만 어기는 것이 된다.
if ($Uninstall) {
    $hadScope = $Hooks -or $AgentsMd -or $Keybinds
    $unKeybinds = if ($hadScope) { [bool]$Keybinds } else { $true }
    $unHooks = if ($hadScope) { [bool]$Hooks } else { $true }

    # 키바인드를 '먼저' 지운다. 훅 uninstall 이 매니페스트를 손보는데, 키바인드 제거는
    # 그 영수증(tmux_added 등)이 있어야 '우리가 넣은 것' 과 사용자 것을 구분할 수 있다.
    $kbExit = 0
    $hooksExit = 0
    if ($unKeybinds) {
        & (Join-Path $PSScriptRoot "setup_keybinds.ps1") -Uninstall -DryRun:$dryRun
        $kbExit = $LASTEXITCODE
    }
    if ($unHooks) {
        & (Join-Path $PSScriptRoot "setup_hooks.ps1") -Uninstall -DryRun:$dryRun
        $hooksExit = $LASTEXITCODE
    }
    if ($hooksExit -ne 0) { exit $hooksExit }
    exit $kbExit
}

if (-not ($runHooks -or $runAgentsMd -or $runKeybinds)) {
    $runHooks = $true
    $runAgentsMd = $true
    $runKeybinds = $true
}

if ($runHooks) {
    & (Join-Path $PSScriptRoot "setup_hooks.ps1") -DryRun:$dryRun -DefaultMode $defaultMode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($runAgentsMd) {
    # An empty selection means "not specified", so the worker applies its own
    # default rather than being handed an empty array it would have to reject.
    if ($harnesses.Count -gt 0) {
        & (Join-Path $PSScriptRoot "setup_agentsmd.ps1") -DryRun:$dryRun -Force:$forceAgentsMd -Harness $harnesses
    } else {
        & (Join-Path $PSScriptRoot "setup_agentsmd.ps1") -DryRun:$dryRun -Force:$forceAgentsMd
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if ($runKeybinds) {
    $kbParams = @{ DryRun = $dryRun }
    if ($newlineChord) { $kbParams["Newline"] = $newlineChord }
    & (Join-Path $PSScriptRoot "setup_keybinds.ps1") @kbParams
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

exit 0

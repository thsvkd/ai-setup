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
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Omc                  # OMC + 캐시 TTL HUD만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -OutputStyle          # fluent-korean 출력 스타일만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Mods                 # Claude Code mod 만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -DryRun               # 미리보기 (전체)
    powershell -ExecutionPolicy Bypass -File setup.ps1 -NoOnboard            # 온보딩 끄기
#>

[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Hooks,
    [switch]$AgentsMd,
    [switch]$Keybinds,
    [switch]$Skills,
    [switch]$Omc,
    [switch]$OutputStyle,
    [switch]$Mods,
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
  -Skills       번들 스킬만 설치 (~/.claude/skills)
  -Keybinds     줄바꿈 키바인딩만 설치 (VS Code/Cursor/Claude/Codex)
  -Newline VAL  줄바꿈 키 (shift-enter | ctrl-enter). 기본 shift-enter
  -Omc          oh-my-claudecode 플러그인 설치 + HUD 에 캐시 TTL 표시
                (범위 지정이 없는 기본 설치에는 포함되지 않는다)
  -OutputStyle  fluent-korean 플러그인 설치 + outputStyle 을 fluent-korean 으로 지정
                (범위 지정이 없는 기본 설치에는 포함되지 않는다)
  -Mods         Claude Code mod 설치 (~/.claude/mods, v2.1.290 이상)
                · bash-diff-filter: Bash 변경 파일 표시에서 OMC HUD 캐시 파일을 뺀다
                · cache-ttl-status: 프롬프트 캐시 잔여 시간을 프롬프트 아래 상태 줄에 띄운다
                (범위 지정이 없는 기본 설치에는 포함되지 않는다)
  -Uninstall    가드 훅 + 관리 키바인딩·스킬 + 캐시 TTL HUD + outputStyle + mod 설정 제거
                (권한·사용자 항목·OMC/fluent-korean 플러그인은 보존)
  -DryRun       아무것도 바꾸지 않고 변경 계획만 출력
  -NoOnboard    대화형 온보딩을 띄우지 않고 기본값으로 실행
  -Help         이 도움말

온보딩에서 고를 수 있는 것:
  · 설치 범위 (전체(번들 스킬 포함) / 가드 훅+권한만 / AGENTS.md만)
  · 권한 모드 (auto / bypassPermissions)
  · 줄바꿈 키 (Shift+Enter / Ctrl+Enter) — 범위=전체일 때만
  · oh-my-claudecode 설치 여부 — 범위=전체/훅일 때만
  · fluent-korean 출력 스타일 설치 여부 — 범위=전체/훅일 때만
  · Claude Code mod 설치 여부 — 범위=전체/훅일 때만
  · 기존 AGENTS.md 덮어쓰기 여부 (파일이 이미 있을 때만 물음)
  · 지금 적용할지, 변경 계획(-DryRun)만 먼저 볼지

setup.sh 와 같은 긴 표기도 그대로 받습니다:
  --hooks  --agentsmd  --harness L  --skills  --keybinds  --omc  --output-style  --mods  --newline VAL  --uninstall  --dry-run
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
        '^--skills$'             { $Skills = $true }
        '^--keybinds$'           { $Keybinds = $true }
        '^--omc$'                { $Omc = $true }
        '^--output-style$'       { $OutputStyle = $true }
        '^--mods$'               { $Mods = $true }
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
$runSkills = [bool]$Skills
$runOmc = [bool]$Omc
$runOutputStyle = [bool]$OutputStyle
$runMods = [bool]$Mods
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

$hadArgs = $Hooks -or $AgentsMd -or $Keybinds -or $Skills -or $Omc -or $OutputStyle -or $Mods -or $Uninstall -or $DryRun -or $NoOnboard -or $newlineGiven -or $harnessGiven
if (-not $hadArgs) {
    $answers = Invoke-Onboarding
    if ($answers) {
        switch ($answers["SCOPE"]) {
            "all"      { $runHooks = $true; $runAgentsMd = $true; $runKeybinds = $true; $runSkills = $true }
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
        if ($answers["OMC"] -eq "1") { $runOmc = $true }
        if ($answers["OUTPUT_STYLE"] -eq "1") { $runOutputStyle = $true }
        if ($answers["MODS"] -eq "1") { $runMods = $true }
        if ($answers["DRY_RUN"] -eq "1") { $dryRun = $true }
    }
}

# ── 출력 서식 ────────────────────────────────────────────────────────
# setup.sh 의 ui_format 과 같은 규칙. 워커는 단독으로도 실행되므로 각자 이모지 마커로 줄을
# 찍고, 여기서 그 출력(Write-Host 는 6>&1 로 받는다)을 한 줄씩 clack 거터 모양으로 바꾼다.
# 문구는 그대로 둔다. 기본 conhost 는 이 기호들을 못 그리는 글꼴이 많아 ASCII 로 대체한다
# (clack 이 쓰는 is-unicode-supported 와 같은 판정).
$onWindows = [System.Environment]::OSVersion.Platform -eq 'Win32NT'
$uiUnicode = (-not $onWindows) -or [bool]$env:WT_SESSION -or ($env:TERM_PROGRAM -eq 'vscode') -or
    ($env:TERMINAL_EMULATOR -eq 'JetBrains-JediTerm') -or ($env:ConEmuTask -eq '{cmd::Cmder}')
if ($uiUnicode) {
    $G = @{ Bar = '│'; Start = '┌'; End = '└'; Section = '◇'; Ok = '✓'; Warn = '▲'; Err = '✗'; Dry = '○'; Dot = '•' }
} else {
    $G = @{ Bar = '|'; Start = 'T'; End = '-'; Section = 'o'; Ok = '+'; Warn = '!'; Err = 'x'; Dry = 'o'; Dot = '-' }
}
$uiMarks = @(
    @{ Prefixes = @('✅', '🎉'); Mark = 'Ok'; Color = 'Green' },
    @{ Prefixes = @('⚠️', '⚠'); Mark = 'Warn'; Color = 'Yellow' },
    @{ Prefixes = @('❌'); Mark = 'Err'; Color = 'Red' },
    @{ Prefixes = @('🧪'); Mark = 'Dry'; Color = 'Cyan' },
    @{ Prefixes = @('ℹ️', '💾', '🗑️', '📦', '🐍', '🧾', '🔁', '•'); Mark = 'Dot'; Color = 'DarkGray' }
)

$ord = [System.StringComparison]::Ordinal

function Write-UiBar([string]$Rest = '') {
    Write-Host $G.Bar -ForegroundColor DarkGray -NoNewline
    Write-Host $Rest
}

filter Format-SetupOutput {
    foreach ($line in ([string]$_ -split "`r?`n")) {
        if (-not $line.Trim()) { Write-UiBar; continue }
        $body = $line.TrimStart(' ')
        $pad = [Math]::Max(0, $line.Length - $body.Length - 2)
        # Windows PowerShell 5.1(.NET Framework)의 StartsWith 는 문화권 비교라 이모지를 무시할 수 있다.
        if ($body.StartsWith('🔧 ', $ord) -or $body.StartsWith('🧹 ', $ord)) {
            $title = $body.Substring($body.IndexOf(' ') + 1).Replace('...', '')
            if ($title.EndsWith(' 시작', $ord)) { $title = $title.Substring(0, $title.Length - 3) }
            Write-UiBar
            Write-Host $G.Section -ForegroundColor Green -NoNewline
            Write-Host "  $title"
            continue
        }
        if ($body.StartsWith('── ', $ord)) {
            $title = $body.Substring(3)
            $cut = $title.IndexOf(' ─', $ord)
            if ($cut -ge 0) { $title = $title.Substring(0, $cut) }
            Write-UiBar "  $title"
            continue
        }
        if ($body -match '^\[\d/\d\] ') { Write-UiBar ("  " + $body.Replace('...', '')); continue }
        # 닫는 가로줄(──────)만 있는 줄은 거터가 대신하므로 버린다.
        if (-not $body.Replace('─', '')) { continue }

        $hit = $null
        foreach ($m in $uiMarks) {
            foreach ($p in $m.Prefixes) {
                if ($body.StartsWith("$p ", $ord)) { $hit = $m; $body = $body.Substring($p.Length).TrimStart(' '); break }
            }
            if ($hit) { break }
        }
        Write-Host $G.Bar -ForegroundColor DarkGray -NoNewline
        Write-Host ("  " + (' ' * $pad)) -NoNewline
        if ($hit) {
            Write-Host $G[$hit.Mark] -ForegroundColor $hit.Color -NoNewline
            Write-Host " $body"
        } else {
            Write-Host $body
        }
    }
}

function Exit-Setup([int]$Code) {
    # 설치 출력은 온보딩과 같은 모양의 블록 하나로 묶는다. 끝줄은 종료 코드를 보고 찍는다.
    $what = if ($Uninstall) { "제거" } else { "설치" }
    Write-UiBar
    Write-Host $G.End -ForegroundColor DarkGray -NoNewline
    if ($Code -ne 0) {
        Write-Host "  $what 실패 (exit $Code) — 위 메시지를 확인하세요." -ForegroundColor Red
    } elseif ($dryRun) {
        Write-Host "  DRY RUN 완료 — 아무것도 바꾸지 않았습니다."
    } else {
        Write-Host "  $what 완료"
    }
    Write-Host ""
    exit $Code
}

# 워커가 찍는 python 출력이 파이프 너머에서 블록 버퍼링되면 stderr 경고와 순서가 뒤바뀐다.
$env:PYTHONUNBUFFERED = '1'

Write-Host ""
Write-Host $G.Start -ForegroundColor DarkGray -NoNewline
Write-Host "  claude-code-setup"

# 워커가 throw 로 끝나도(셀프테스트 실패 등) 끝줄을 찍고 실패 코드로 나간다.
try {

# 제거도 설치와 같은 범위 규칙을 따른다. 범위를 지정했으면 그것만 지운다 —
# -Hooks -Uninstall 이 키바인딩까지 지우면 "-Hooks 는 키바인딩을 건드리지 않는다"
# (핵심 결정 4)를 제거 쪽에서만 어기는 것이 된다.
if ($Uninstall) {
    $hadScope = $Hooks -or $AgentsMd -or $Keybinds -or $Skills -or $Omc -or $OutputStyle -or $Mods
    $unKeybinds = if ($hadScope) { [bool]$Keybinds } else { $true }
    $unHooks = if ($hadScope) { [bool]$Hooks } else { $true }
    $unSkills = if ($hadScope) { [bool]$Skills } else { $true }
    $unOmc = if ($hadScope) { [bool]$Omc } else { $true }
    $unOutputStyle = if ($hadScope) { [bool]$OutputStyle } else { $true }
    $unMods = if ($hadScope) { [bool]$Mods } else { $true }

    # 키바인드를 '먼저' 지운다. 훅 uninstall 이 매니페스트를 손보는데, 키바인드 제거는
    # 그 영수증(tmux_added 등)이 있어야 '우리가 넣은 것' 과 사용자 것을 구분할 수 있다.
    $kbExit = 0
    $hooksExit = 0
    $skillsExit = 0
    if ($unSkills) {
        & (Join-Path $PSScriptRoot "setup_skills.ps1") -Uninstall -DryRun:$dryRun 6>&1 | Format-SetupOutput
        $skillsExit = $LASTEXITCODE
    }
    # mod·출력 스타일·캐시 TTL HUD 영수증도 매니페스트에 있으므로 훅 uninstall 보다 먼저 되돌린다.
    # 이 셋은 설치(OMC → 출력 스타일 → mod)의 역순으로 되돌린다 — settings.json 을 처음 만든
    # 워커가 마지막에 와야, 다른 워커의 키가 다 빠진 뒤 빈 파일을 지울 수 있다.
    $modsExit = 0
    if ($unMods) {
        & (Join-Path $PSScriptRoot "setup_mods.ps1") -Uninstall -DryRun:$dryRun 6>&1 | Format-SetupOutput
        $modsExit = $LASTEXITCODE
    }
    $styleExit = 0
    if ($unOutputStyle) {
        & (Join-Path $PSScriptRoot "setup_output_style.ps1") -Uninstall -DryRun:$dryRun 6>&1 | Format-SetupOutput
        $styleExit = $LASTEXITCODE
    }
    $omcExit = 0
    if ($unOmc) {
        & (Join-Path $PSScriptRoot "setup_omc.ps1") -Uninstall -DryRun:$dryRun 6>&1 | Format-SetupOutput
        $omcExit = $LASTEXITCODE
    }
    if ($unKeybinds) {
        & (Join-Path $PSScriptRoot "setup_keybinds.ps1") -Uninstall -DryRun:$dryRun 6>&1 | Format-SetupOutput
        $kbExit = $LASTEXITCODE
    }
    if ($unHooks) {
        & (Join-Path $PSScriptRoot "setup_hooks.ps1") -Uninstall -DryRun:$dryRun 6>&1 | Format-SetupOutput
        $hooksExit = $LASTEXITCODE
    }
    if ($hooksExit -ne 0) { Exit-Setup $hooksExit }
    if ($skillsExit -ne 0) { Exit-Setup $skillsExit }
    if ($omcExit -ne 0) { Exit-Setup $omcExit }
    if ($styleExit -ne 0) { Exit-Setup $styleExit }
    if ($modsExit -ne 0) { Exit-Setup $modsExit }
    Exit-Setup $kbExit
}

# OMC·fluent-korean 은 서드파티 플러그인이라, mod 는 최신 Claude Code 에서만 동작해서 기본 전체
# 설치에 끼우지 않는다 — 명시적으로 고른 경우에만.
if (-not ($runHooks -or $runAgentsMd -or $runKeybinds -or $runSkills -or $runOmc -or $runOutputStyle -or $runMods)) {
    $runHooks = $true
    $runAgentsMd = $true
    $runKeybinds = $true
    $runSkills = $true
}

if ($runHooks) {
    & (Join-Path $PSScriptRoot "setup_hooks.ps1") -DryRun:$dryRun -DefaultMode $defaultMode 6>&1 | Format-SetupOutput
    if ($LASTEXITCODE -ne 0) { Exit-Setup $LASTEXITCODE }
}

if ($runAgentsMd) {
    # An empty selection means "not specified", so the worker applies its own
    # default rather than being handed an empty array it would have to reject.
    if ($harnesses.Count -gt 0) {
        & (Join-Path $PSScriptRoot "setup_agentsmd.ps1") -DryRun:$dryRun -Force:$forceAgentsMd -Harness $harnesses 6>&1 | Format-SetupOutput
    } else {
        & (Join-Path $PSScriptRoot "setup_agentsmd.ps1") -DryRun:$dryRun -Force:$forceAgentsMd 6>&1 | Format-SetupOutput
    }
    if ($LASTEXITCODE -ne 0) { Exit-Setup $LASTEXITCODE }
}

if ($runKeybinds) {
    $kbParams = @{ DryRun = $dryRun }
    if ($newlineChord) { $kbParams["Newline"] = $newlineChord }
    & (Join-Path $PSScriptRoot "setup_keybinds.ps1") @kbParams 6>&1 | Format-SetupOutput
    if ($LASTEXITCODE -ne 0) { Exit-Setup $LASTEXITCODE }
}

if ($runOmc) {
    & (Join-Path $PSScriptRoot "setup_omc.ps1") -DryRun:$dryRun 6>&1 | Format-SetupOutput
    if ($LASTEXITCODE -ne 0) { Exit-Setup $LASTEXITCODE }
}

if ($runOutputStyle) {
    & (Join-Path $PSScriptRoot "setup_output_style.ps1") -DryRun:$dryRun 6>&1 | Format-SetupOutput
    if ($LASTEXITCODE -ne 0) { Exit-Setup $LASTEXITCODE }
}

if ($runMods) {
    & (Join-Path $PSScriptRoot "setup_mods.ps1") -DryRun:$dryRun 6>&1 | Format-SetupOutput
    if ($LASTEXITCODE -ne 0) { Exit-Setup $LASTEXITCODE }
}

if ($runSkills) {
    & (Join-Path $PSScriptRoot "setup_skills.ps1") -DryRun:$dryRun 6>&1 | Format-SetupOutput
    if ($LASTEXITCODE -ne 0) { Exit-Setup $LASTEXITCODE }
}

Exit-Setup 0
} catch {
    "❌ $($_.Exception.Message)" | Format-SetupOutput
    # 어디서 실패했는지는 거터 밖(stderr)에 남긴다 — throw 를 잡지 않던 때 보이던 정보다.
    [Console]::Error.WriteLine($_.InvocationInfo.PositionMessage)
    Exit-Setup 1
}

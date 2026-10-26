<#
.SYNOPSIS
    Claude Code 사용자 레벨 설정 CLI 엔트리포인트 (Windows)
.DESCRIPTION
    인자 없이 실행하면 대화형 온보딩(res/onboard.py)이 단계 산책을 띄운다. 산책 뒤나 Skip 은
    카테고리 허브로 가고, 허브의 Apply 만 설치한다. Quit 이나 콘솔 없음은 아무것도 설치하지 않는다. 플래그를 주면 온보딩을 건너뛴다.
    -NoOnboard 는 예전 기본 설치를 유지한다. --stages 는 res/stages.py 액션 목록을 따른다.
.USAGE
    powershell -ExecutionPolicy Bypass -File setup.ps1                       # 온보딩 → 선택대로
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Hooks                # 훅/권한만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -AgentsMd             # AGENTS.md만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Omc                  # OMC + 캐시 TTL HUD만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -OutputStyle          # fluent-korean 출력 스타일만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Mods                 # Claude Code mod 만
    powershell -ExecutionPolicy Bypass -File setup.ps1 -DryRun               # 미리보기 (전체)
    powershell -ExecutionPolicy Bypass -File setup.ps1 -NoOnboard            # 온보딩 끄기
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Doctor               # 읽기 전용 점검
#>

[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Hooks,
    [switch]$AgentsMd,
    [switch]$Keybinds,
    [switch]$Skills,
    [string]$Tools = "",
    [switch]$Omc,
    [switch]$OutputStyle,
    [switch]$Mods,
    [string[]]$Harness = @(),
    [string]$Newline = "",
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$NoOnboard,
    [switch]$Doctor,
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
$toolsGiven = $PSBoundParameters.ContainsKey("Tools")

function Show-Usage {
    Write-Host @"
ai-setup — Claude Code user-level setup

Usage: .\setup.ps1 [options]
  (no options)  walk the stages, then the category hub. Only Apply installs; Quit or no console installs nothing
  -Hooks        install global guard hooks + permissions only (~/.claude)
  -AgentsMd     install project instructions into the current folder only
  -Harness L    harnesses to install instructions for (comma-separated: claude,codex,grok,opencode,agy,gemini,copilot,all)
                choosing claude also installs CLAUDE.md. Default is all.
  -Skills       install bundled skills only (~/.claude/skills)
  -Tools orca   install the official Orca package and its bundled skills only
                may be combined with -DryRun or -Uninstall
  -Keybinds     install newline keybindings only (VS Code/Cursor/Claude/Codex)
  -Newline VAL  newline key (shift-enter | ctrl-enter). Default shift-enter
  -Omc          install the oh-my-claudecode plugin + show cache TTL in the HUD
                (not included in the default install without a scope)
  -OutputStyle  install the fluent-korean plugin + set outputStyle to fluent-korean
                (not included in the default install without a scope)
  -Mods         install Claude Code mods (~/.claude/mods, v2.1.290 or later)
                · bash-diff-filter: hides OMC HUD cache files from the Bash changed-files display
                · cache-ttl-status: shows the remaining prompt-cache time in a status line below the prompt
                · korean-reply-rewrite: after a Korean prompt, stores English replies in Korean so later replies stay Korean
                (not included in the default install without a scope)
  -Uninstall    remove guard hooks + managed keybindings/skills + cache TTL HUD + outputStyle + mod settings
                (permissions, user entries and the OMC/fluent-korean plugins are kept)
  -DryRun       print the change plan only, without changing anything
  --stages L    all or a comma list, in stage order. -DryRun prints the list only
  --jarvis-role gateway|core
                with --stages, clone and register Jarvis for that role
  --herdr       with --stages, include herdr (off unless chosen)
  --orca-desktop
                with -Tools orca or --stages, also open the paired Orca desktop app
                (points the Orca shortcuts at the desktop profile). Off by default
  --ss-caps     with --stages, grant the Jarvis ss capability
  -NoOnboard    run the old default install without interactive onboarding
  -Doctor       read-only health report: installed harnesses/tools and versions, duplicate installs,
                retired hooks still wired, plaintext secrets (key names only), skills outside the lock.
                Runs alone and changes nothing. Exit 1 when it finds a problem
  -Help         this help

What onboarding lets you choose:
  · Walk the stages, or Skip straight to the category menu (hub)
  · a machine that already has a receipt opens the hub directly
  · each stage, on by default: base, harness, plugins, skills, codegraph, mcp, newline, claude_special, tools, hooks, agentsmd
  · harnesses (default Claude Code and Codex)
  · newline key (Shift+Enter / Ctrl+Enter)
  · Claude specials when Claude Code is selected
  · Jarvis role (default: do not install) and herdr (default off)
  · permission mode (auto / bypassPermissions)
  · whether to overwrite an existing AGENTS.md (asked only when the file exists)
  · in the hub: Apply, Preview the plan (-DryRun), or Quit

The same long options as setup.sh are accepted too:
  --hooks  --agentsmd  --harness L  --skills  --keybinds  --omc  --output-style  --mods  --newline VAL  --uninstall  --dry-run
  --stages L  --jarvis-role gateway|core  --herdr  --ss-caps
  --no-onboard  --doctor  --help
"@
}

# param 블록의 $Rest 로 흘러든 토큰을 setup.sh 와 같은 규칙으로 해석한다. 조용히 버리면
# 오타(--keybind)가 '전체 설치' 로 둔갑하므로, 모르는 것은 사용법과 함께 거절한다.
$newlineGiven = $PSBoundParameters.ContainsKey("Newline")
$harnessGiven = $PSBoundParameters.ContainsKey("Harness")
$unknownArgs = @()
$stageRun = $false
$stagesValue = ""
$jarvisRole = ""
$herdrFlag = $false
$orcaDesktop = $false
$ssCaps = $false
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
        '^--doctor$'             { $Doctor = $true }
        '^--tools=(.*)$'         { $Tools = $Matches[1]; $toolsGiven = $true }
        '^--tools$' {
            $toolsGiven = $true
            $Tools = if ($i + 1 -lt $Rest.Count) { $Rest[++$i] } else { "" }
            if (-not $Tools) { Write-Host "--tools requires orca."; exit 1 }
        }
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
        '^--stages=(.*)$' { $stagesValue = $Matches[1]; $stageRun = $true }
        '^--stages$' {
            $stageRun = $true
            $stagesValue = if ($i + 1 -lt $Rest.Count) { $Rest[++$i] } else { "" }
            if (-not $stagesValue) { Write-Host "--stages requires all or a comma-separated list."; exit 1 }
        }
        '^--jarvis-role=(.*)$' { $jarvisRole = $Matches[1] }
        '^--jarvis-role$' {
            $jarvisRole = if ($i + 1 -lt $Rest.Count) { $Rest[++$i] } else { "" }
            if (-not $jarvisRole) { Write-Host "--jarvis-role requires gateway or core."; exit 1 }
        }
        '^--herdr$' { $herdrFlag = $true }
        '^--orca-desktop$' { $orcaDesktop = $true }
        '^--ss-caps$' { $ssCaps = $true }
        default { $unknownArgs += $Rest[$i] }
    }
}

if ($Help) {
    Show-Usage
    exit 0
}

if ($unknownArgs.Count -gt 0) {
    Write-Host "Unknown option: $($unknownArgs -join ' ')" -ForegroundColor Red
    Write-Host ""
    Show-Usage
    exit 1
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
if ($toolsGiven -and -not $Tools) { Write-Host "--tools requires orca." -ForegroundColor Red; exit 1 }

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
# 온보딩 답이 있을 때만 채운다. $null 이면 --stages 는 특별 설정을 기본으로 계획한다.
$includeOutputStyle = $null
$includeMods = $null
$includeOmc = $null

if ($jarvisRole -and $jarvisRole -notin @("gateway", "core")) {
    Write-Host "--jarvis-role must be gateway or core (got: $jarvisRole)." -ForegroundColor Red
    exit 1
}
if (($jarvisRole -or $herdrFlag -or $ssCaps) -and -not $stageRun) {
    Write-Host "--jarvis-role, --herdr, and --ss-caps require --stages." -ForegroundColor Red
    exit 1
}
if ($orcaDesktop -and -not $stageRun -and -not $Tools) {
    Write-Host "--orca-desktop requires -Tools orca or --stages." -ForegroundColor Red
    exit 1
}

if ($newlineGiven -and $newlineChord -notin @("shift-enter", "ctrl-enter")) {
    Write-Host "-Newline (--newline) must be shift-enter or ctrl-enter (got: $newlineChord)." -ForegroundColor Red
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

# doctor 는 읽기 전용이라 설치 흐름(온보딩·영수증·배너)과 섞지 않고 단독으로 끝낸다.
if ($Doctor) {
    $otherArgs = @($PSBoundParameters.Keys | Where-Object { $_ -notin @("Doctor", "Rest") }).Count + @($Rest | Where-Object { $_ -ne "--doctor" }).Count
    if ($otherArgs -gt 0) {
        Write-Host "--doctor runs alone; drop the other options." -ForegroundColor Red
        exit 1
    }
    $py = Resolve-PythonForOnboard
    if (-not $py) { Write-Host "Python 3.8+ is required." -ForegroundColor Red; exit 2 }
    $homeDir = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
    # -B: 바이트코드 캐시도 쓰지 않는다(doctor 는 읽기 전용).
    & $py.Exe @($py.Args) -B -X utf8 (Join-Path $RepoRoot "res\doctor\doctor.py") --home $homeDir
    exit $LASTEXITCODE
}

if ($Tools) {
    if ($Tools -ne "orca" -or $Hooks -or $AgentsMd -or $Keybinds -or $Skills -or $Omc -or $OutputStyle -or $Mods -or $Harness.Count -or $Newline) {
        Write-Host "-Tools currently accepts orca alone, with -DryRun or -Uninstall." -ForegroundColor Red
        exit 1
    }
    $py = Resolve-PythonForOnboard
    if (-not $py) { Write-Host "Python 3.8+ is required." -ForegroundColor Red; exit 2 }
    $toolArgs = @()
    if ($DryRun) { $toolArgs += "--dry-run" }
    if ($Uninstall) { $toolArgs += "--uninstall" }
    if ($orcaDesktop) { $toolArgs += "--desktop-app" }
    & $py.Exe @($py.Args) -B -X utf8 (Join-Path $RepoRoot "res\tools\orca.py") @toolArgs
    exit $LASTEXITCODE
}

# 온보딩 종료 코드: 0=선택 완료, 1=프롬프트가 깨짐, 2=대화형 불가(콘솔 없음/CI), 130=사용자 취소.
# 2 는 "물어볼 수 없었다"라서 아무것도 설치하지 않고 끝낸다. 나머지(취소·깨짐·traceback)도
# 설치하지 않고 멈춘다.
function Invoke-Onboarding {
    $onboard = Join-Path $RepoRoot "res\onboard.py"
    if (-not (Test-Path $onboard)) { return $null }

    $py = Resolve-PythonForOnboard
    if (-not $py) { return $null }

    $answersPath = [System.IO.Path]::GetTempFileName()
    try {
        # 5.1 은 출력이 리다이렉트되면(ISE·원격·`2>&1 | Tee`) 네이티브 stderr 를 오류 레코드로 바꾸고,
        # Stop 이면 거기서 설치가 죽는다. 온보딩은 '물을 수 없음'(exit 2)을 stderr 로 알리므로
        # 판정은 종료 코드로만 한다.
        $ErrorActionPreference = "Continue"
        try {
            & $py.Exe @($py.Args) -X utf8 $onboard --out $answersPath --project-dir (Get-Location).Path
        } finally {
            $ErrorActionPreference = "Stop"
        }
        $status = $LASTEXITCODE

        if ($status -eq 2) {
            Write-Host "No terminal, so nothing was installed."
            exit 0
        }
        if ($status -ne 0) {
            if ($status -ne 130) { Write-Host "Onboarding did not finish. Aborting installation (exit $status)." -ForegroundColor Red }
            exit $status
        }

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

$hadArgs = $Hooks -or $AgentsMd -or $Keybinds -or $Skills -or $Omc -or $OutputStyle -or $Mods -or $Uninstall -or $DryRun -or $NoOnboard -or $newlineGiven -or $harnessGiven -or $stageRun -or $herdrFlag -or $ssCaps -or [bool]$jarvisRole
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
        if ($answers["SKIP"] -eq "1") {
            Write-Host "Nothing selected, so nothing was installed."
            exit 0
        }
        if ($answers.ContainsKey("STAGES") -and $answers["STAGES"] -match "^[a-z_,]+$") {
            $stagesValue = $answers["STAGES"]
            $stageRun = $true
        }
        if ($answers["JARVIS_ROLE"] -in @("gateway", "core")) { $jarvisRole = $answers["JARVIS_ROLE"] }
        if ($answers["HERDR"] -eq "1") { $herdrFlag = $true }
        if ($answers["OVERWRITE_AGENTSMD"] -eq "1") { $forceAgentsMd = $true }
        if ($answers.ContainsKey("OMC") -and $answers["OMC"] -in @("0", "1")) {
            $includeOmc = $answers["OMC"]
            if ($answers["OMC"] -eq "1") { $runOmc = $true }
        }
        if ($answers.ContainsKey("OUTPUT_STYLE") -and $answers["OUTPUT_STYLE"] -in @("0", "1")) {
            $includeOutputStyle = $answers["OUTPUT_STYLE"]
            if ($answers["OUTPUT_STYLE"] -eq "1") { $runOutputStyle = $true }
        }
        if ($answers.ContainsKey("MODS") -and $answers["MODS"] -in @("0", "1")) {
            $includeMods = $answers["MODS"]
            if ($answers["MODS"] -eq "1") { $runMods = $true }
        }
        if ($answers["DRY_RUN"] -eq "1") { $dryRun = $true }
    }
}

function Invoke-StagePlan {
    $py = Resolve-PythonForOnboard
    if (-not $py) { Write-Host "Python 3.8+ is required." -ForegroundColor Red; exit 2 }
    $planArgs = @("--plan", "--stages", $stagesValue, "--project-dir", (Get-Location).Path)
    if ($harnesses -and @($harnesses).Count -gt 0 -and @($harnesses)[0]) {
        $planArgs += @("--harness", (@($harnesses) -join ","))
    }
    if ($jarvisRole) { $planArgs += @("--jarvis-role", $jarvisRole) }
    if ($herdrFlag) { $planArgs += "--herdr" }
    if ($orcaDesktop) { $planArgs += "--orca-desktop" }
    if ($ssCaps) { $planArgs += "--ss-caps" }
    if ($dryRun) { $planArgs += "--dry-run" }
    if ($Uninstall) { $planArgs += "--uninstall" }
    if ($newlineChord) { $planArgs += @("--newline", $newlineChord) }
    if ($defaultMode) { $planArgs += @("--permission-mode", $defaultMode) }
    if ($forceAgentsMd) { $planArgs += "--overwrite-agentsmd" }
    if ($null -ne $includeOutputStyle) { $planArgs += @("--include-output-style", $includeOutputStyle) }
    if ($null -ne $includeMods) { $planArgs += @("--include-mods", $includeMods) }
    if ($null -ne $includeOmc) { $planArgs += @("--include-omc", $includeOmc) }
    & $py.Exe @($py.Args) -B -X utf8 (Join-Path $RepoRoot "res\stages.py") @planArgs
    $status = $LASTEXITCODE
    if ($dryRun -and $status -eq 0) {
        Write-Host "DRY RUN complete — nothing was changed."
    }
    exit $status
}

if ($stageRun) {
    if ($Tools) { Write-Host "--tools cannot be combined with --stages." -ForegroundColor Red; exit 1 }
    Invoke-StagePlan
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
            if ($title.StartsWith('Starting ', $ord)) { $title = $title.Substring(9) }
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
    $what = if ($Uninstall) { "Uninstall" } else { "Install" }
    Write-UiBar
    Write-Host $G.End -ForegroundColor DarkGray -NoNewline
    if ($Code -ne 0) {
        Write-Host "  $what failed (exit $Code) — check the messages above." -ForegroundColor Red
    } elseif ($dryRun) {
        Write-Host "  DRY RUN complete — nothing was changed."
    } else {
        Write-Host "  $what complete"
    }
    Write-Host ""
    exit $Code
}

# 워커가 찍는 python 출력이 파이프 너머에서 블록 버퍼링되면 stderr 경고와 순서가 뒤바뀐다.
$env:PYTHONUNBUFFERED = '1'

Write-Host ""
Write-Host $G.Start -ForegroundColor DarkGray -NoNewline
Write-Host "  ai-setup"

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

# setup.ps1 / setup_hooks.ps1 오케스트레이션 계층 테스트 (Pester v5).
#   실행: Invoke-Pester tests/Setup.Tests.ps1 -Output Detailed
#
# 스크립트가 `exit` 를 호출하므로 Pester 세션을 죽이지 않도록 자식 pwsh 프로세스로 실행한다.

BeforeAll {
    $script:RepoRoot = Split-Path -Parent $PSScriptRoot
    $script:Setup = Join-Path $script:RepoRoot "scripts\setup.ps1"
    $script:SetupHooks = Join-Path $script:RepoRoot "scripts\setup_hooks.ps1"

    function Invoke-Script {
        param([string]$Path, [string[]]$ScriptArgs)
        $out = pwsh -NoProfile -File $Path @ScriptArgs 2>&1 | Out-String
        return [pscustomobject]@{ Output = $out; ExitCode = $LASTEXITCODE }
    }

    # 지침 워커는 "현재 디렉터리 = 대상 프로젝트" 규약이라 반드시 그 안에서 돌려야 한다.
    # Pester 5 는 Describe 본문을 discovery 단계에 실행하므로 헬퍼는 여기 둔다.
    function Invoke-AgentsMdIn {
        param([string]$ProjectDir, [string[]]$ScriptArgs = @())
        Push-Location $ProjectDir
        try {
            return Invoke-Script (Join-Path $script:RepoRoot "scripts\setup_agentsmd.ps1") $ScriptArgs
        } finally { Pop-Location }
    }

    # `-File` 로 넘기면 PowerShell 이 `--help` 를 -Help 로 붙여주지만, 사용자가 셸에서 직접
    # 치는 `.\setup.ps1 --help` 는 파라미터가 아닌 위치 인자로 들어온다.
    # 위치 바인딩 회귀는 후자로만 재현되므로 그 경로를 그대로 흉내 낸다.
    function Invoke-ScriptInline {
        param([string]$Path, [string]$ArgString)
        $out = pwsh -NoProfile -Command "& '$Path' $ArgString; exit `$LASTEXITCODE" 2>&1 | Out-String
        return [pscustomobject]@{ Output = $out; ExitCode = $LASTEXITCODE }
    }
}

Describe "setup.ps1 dispatcher" {
    BeforeEach {
        $script:sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:oldUP = $env:USERPROFILE
        $env:USERPROFILE = $script:sandbox     # 자식 pwsh 가 상속 → 실제 프로필 격리
    }
    AfterEach {
        $env:USERPROFILE = $script:oldUP
        Remove-Item -Recurse -Force $script:sandbox -ErrorAction SilentlyContinue
    }

    It "-Help exits 0 and prints usage" {
        $r = Invoke-Script $script:Setup @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "Usage"
    }

    It "-Hooks -DryRun does not create settings.json" {
        Invoke-Script $script:Setup @("-Hooks", "-DryRun") | Out-Null
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }

    # 병합은 영수증을 보고 예전 설치가 넣은 항목을 걷어낸다. dry-run 이 영수증을 임시 홈에 복사하지
    # 않으면 계획에서 빠져, 미리 본 것과 실제 설치가 달라진다.
    It "-Hooks -DryRun plans the receipt-based retirement and writes nothing" {
        $claude = Join-Path $env:USERPROFILE ".claude"
        New-Item -ItemType Directory -Force -Path $claude | Out-Null
        $settings = Join-Path $claude "settings.json"
        $receipt = Join-Path $claude ".claude-code-setup.json"
        Set-Content -Path $settings -Encoding ascii -Value '{"autoMode": {"allow": ["$defaults", "old exception"]}}'
        Set-Content -Path $receipt -Encoding ascii -Value '{"version": 1, "added_auto_allow": ["$defaults", "old exception"]}'
        $before = (Get-Content $settings -Raw) + (Get-Content $receipt -Raw)
        $r = Invoke-Script $script:Setup @("-Hooks", "-DryRun")
        $r.ExitCode | Should -Be 0 -Because $r.Output
        $r.Output | Should -Match "no longer shipped"
        ((Get-Content $settings -Raw) + (Get-Content $receipt -Raw)) | Should -Be $before
    }

    It "-Uninstall -DryRun on clean profile exits 0" {
        $r = Invoke-Script $script:SetupHooks @("-Uninstall", "-DryRun")
        $r.ExitCode | Should -Be 0
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }

    # 회귀: 셸에서 직접 실행하면 `--help` 가 위치 인자로 들어와 -Newline 에 바인딩됐고,
    # 도움말 대신 "값은 shift-enter 또는 ctrl-enter 여야 합니다 (받은 값: --help)" 가 나왔다.
    It "--help run directly from the shell also prints the help" {
        $r = Invoke-ScriptInline $script:Setup "--help"
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "Usage"
        $r.Output | Should -Match "--no-onboard"
    }

    It "also accepts setup.sh-style --hooks --dry-run and runs only the hooks scope" {
        $r = Invoke-ScriptInline $script:Setup "--hooks --dry-run"
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "AGENTS.md"      # --hooks 범위가 지켜졌다
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }

    It "an invalid --newline value exits 1 regardless of notation" {
        $r = Invoke-ScriptInline $script:Setup "--keybinds --newline foo"
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "shift-enter"
    }

    # doctor 는 읽기 전용 단독 실행이다. lock 밖 스킬로 경고(exit 1)를 확정한다.
    It "-Doctor and --doctor report a stray skill with exit 1 and write nothing (covers: AI-1, AI-6)" {
        $skills = Join-Path $env:USERPROFILE ".agents\skills\stray"
        New-Item -ItemType Directory -Force -Path $skills | Out-Null
        Set-Content -Path (Join-Path $env:USERPROFILE ".agents\.skill-lock.json") -Encoding ascii -Value '{"version": 3, "skills": {}}'
        # 자식 pwsh 자신이 프로필 아래에 시작 캐시(AppData\Local\Microsoft\PowerShell)를 쓴다.
        # doctor 가 아니라 테스트가 띄운 인터프리터의 흔적이므로 그 경로만 비교에서 뺀다.
        $listHome = {
            (Get-ChildItem -Recurse -Force $env:USERPROFILE | ForEach-Object FullName |
                Where-Object { $_ -notmatch '[\\/]AppData([\\/]Local([\\/]Microsoft([\\/]PowerShell([\\/].*)?)?)?)?$' } |
                Sort-Object) -join "`n"
        }
        $before = & $listHome
        $r = Invoke-Script $script:Setup @("-Doctor")
        $r.ExitCode | Should -Be 1 -Because $r.Output
        $r.Output | Should -Match "stray"
        $r = Invoke-ScriptInline $script:Setup "--doctor"
        $r.ExitCode | Should -Be 1 -Because $r.Output
        (& $listHome) | Should -Be $before
    }

    It "-Doctor refuses other options instead of silently dropping them" {
        $r = Invoke-Script $script:Setup @("-Doctor", "-Uninstall")
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "--doctor runs alone"
        $r = Invoke-ScriptInline $script:Setup "--doctor --hooks"
        $r.ExitCode | Should -Be 1
    }

    It "Update-Ai.ps1 passes -Help, -Only and the long notation through to Python" {
        $updateAi = Join-Path $script:RepoRoot "scripts\Update-Ai.ps1"
        $r = Invoke-Script $updateAi @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "--allow-interrupt"
        $r = Invoke-Script $updateAi @("-Only", "nope")
        $r.ExitCode | Should -Be 2
        $r.Output | Should -Match "unknown target"
        $r = Invoke-ScriptInline $updateAi "--only nope"
        $r.ExitCode | Should -Be 2
    }

    # 조용히 무시하면 오타(--keybind)가 '전체 설치' 로 둔갑한다.
    It "an unknown option exits 1 and shows the usage too" {
        $r = Invoke-ScriptInline $script:Setup "--keybind"
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "Unknown option"
        $r.Output | Should -Match "Usage"
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }
}

Describe "install.ps1 bootstrap" {
    It "-Help exits 0 without network" {
        $r = Invoke-Script (Join-Path $script:RepoRoot "install.ps1") @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "bootstrap"
    }

    # scriptblock 형태(= 셸 직접 실행)에서 --help 가 -Newline 에 바인딩되던 회귀.
    It "--help run directly from the shell also prints the help" {
        $r = Invoke-ScriptInline (Join-Path $script:RepoRoot "install.ps1") "--help"
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "bootstrap"
    }

    # --dry-run 은 알아듣고 --bogus 만 거절해야 한다. 거절은 다운로드 전에 일어나므로
    # 이 테스트는 네트워크를 타지 않는다.
    It "rejects only the unknown option and consumes the long notation" {
        $r = Invoke-ScriptInline (Join-Path $script:RepoRoot "install.ps1") "--dry-run --bogus"
        $r.ExitCode | Should -Not -Be 0
        $r.Output | Should -Match "--bogus"
        $r.Output | Should -Not -Match "--dry-run"
    }

    # README 옵션 표의 -Harness 가 부트스트랩에서 '알 수 없는 옵션' 으로 죽던 회귀.
    # 값까지 소비해야 하므로 --bogus 만 거절되는지로 본다 (다운로드 전이라 네트워크 없음).
    It "consumes -Harness and --harness together with their values" {
        foreach ($a in @("-Harness claude,codex --bogus", "--harness claude --bogus")) {
            $r = Invoke-ScriptInline (Join-Path $script:RepoRoot "install.ps1") $a
            $r.ExitCode | Should -Not -Be 0
            $r.Output | Should -Match "(?m)Unknown option: --bogus\r?$" -Because $a
        }
    }

    # README 의 `irm | iex` 는 인자를 하나도 넘기지 않는다. 그 경로가 빈 인자를 '알 수 없는 옵션'
    # 으로 거절하던 회귀. 존재하지 않는 레포를 가리켜 다운로드 단계에서 멈추게 하므로 설치는
    # 일어나지 않고, 오프라인이어도 결론은 같다.
    It "passes the option check when run without arguments" {
        $oldRepo, $oldTok, $oldUP, $oldTemp = $env:CLAUDE_SETUP_REPO, $env:GITHUB_TOKEN, $env:USERPROFILE, $env:TEMP
        $env:CLAUDE_SETUP_REPO = "thsvkd/does-not-exist-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
        $env:GITHUB_TOKEN = "invalid"
        $env:USERPROFILE = [System.IO.Path]::GetTempPath()
        # install.ps1 은 Windows 부트스트랩이라 $env:TEMP 를 쓴다. Linux/macOS 의 pwsh 에는 없다.
        $env:TEMP = [System.IO.Path]::GetTempPath()
        try {
            $r = Invoke-ScriptInline (Join-Path $script:RepoRoot "install.ps1") ""
        } finally {
            $env:CLAUDE_SETUP_REPO, $env:GITHUB_TOKEN, $env:USERPROFILE, $env:TEMP = $oldRepo, $oldTok, $oldUP, $oldTemp
        }
        $r.Output | Should -Not -Match "Unknown option"
        $r.Output | Should -Match "Download failed"
    }

    # 온보딩이 깨져 setup.ps1 이 중단돼도 install.ps1 이 exit 0 이면 자동화는 성공으로 본다.
    # 다운로드만 대역으로 바꾼다 — 같은 이름의 함수가 cmdlet 보다 먼저 해석된다.
    It "a file run exits with the exit code of the downloaded setup.ps1" {
        $sb = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-inst-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        $src = Join-Path $sb "src\ai-setup-main\scripts"
        New-Item -ItemType Directory -Force -Path $src | Out-Null
        Set-Content -Path (Join-Path $src "setup.ps1") -Value "exit 3" -Encoding ascii
        $zip = Join-Path $sb "repo.zip"
        Compress-Archive -Path (Join-Path $sb "src\*") -DestinationPath $zip
        $mock = "function Invoke-WebRequest { param(`$Uri, `$OutFile, `$UseBasicParsing, `$Headers) Copy-Item '$zip' `$OutFile }"
        $text = (Get-Content (Join-Path $script:RepoRoot "install.ps1") -Raw).Replace(
            "Set-StrictMode -Version Latest", "Set-StrictMode -Version Latest`r`n$mock")
        # 대역이 안 들어가면 진짜 저장소를 내려받아 설치한다 — 그 전에 멈춘다.
        $text | Should -Match "function Invoke-WebRequest"
        $inst = Join-Path $sb "install.ps1"
        [System.IO.File]::WriteAllText($inst, $text, (New-Object System.Text.UTF8Encoding $false))
        $oldTemp, $oldUP, $oldTok = $env:TEMP, $env:USERPROFILE, $env:GITHUB_TOKEN
        $env:TEMP = $sb
        $env:USERPROFILE = $sb
        $env:GITHUB_TOKEN = "unused"
        try {
            $out = pwsh -NoProfile -File $inst -NoOnboard 2>&1 | Out-String
            $ec = $LASTEXITCODE
        } finally {
            $env:TEMP, $env:USERPROFILE, $env:GITHUB_TOKEN = $oldTemp, $oldUP, $oldTok
            Remove-Item -Recurse -Force $sb -ErrorAction SilentlyContinue
        }
        $ec | Should -Be 3 -Because $out
    }
}

# S2: 기존 Pester 스위트는 -Help / -DryRun 만 밟고 실제 설치 경로를 한 번도 실행하지 않았다.
# macOS 의 치명적 버그(패턴 A)가 정확히 이 빈칸에 숨어 있었던 전례가 있어 추가한다.
Describe "real install path (S2)" {
    BeforeEach {
        $script:sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-real-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:oldUP = $env:USERPROFILE
        $script:oldHome = $env:HOME
        $script:oldApp = $env:APPDATA
        $script:oldLocal = $env:LOCALAPPDATA
        $script:oldVs = $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS
        $script:oldCur = $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS
        $script:oldWt = $env:CLAUDE_SETUP_WT_SETTINGS
        $env:USERPROFILE = $script:sandbox
        $env:HOME = $script:sandbox
        $env:APPDATA = Join-Path $script:sandbox "appdata"
        $env:LOCALAPPDATA = Join-Path $script:sandbox "local"
        New-Item -ItemType Directory -Force -Path $env:APPDATA | Out-Null
        New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA | Out-Null
        $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS = Join-Path $script:sandbox "vscode-keybindings.json"
        $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS = Join-Path $script:sandbox "cursor-keybindings.json"
        $env:CLAUDE_SETUP_WT_SETTINGS = Join-Path $script:sandbox "wt-settings.json"
        Set-Content -Path $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Value '[]' -Encoding utf8
        Set-Content -Path $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS -Value '[]' -Encoding utf8
        Set-Content -Path $env:CLAUDE_SETUP_WT_SETTINGS -Value '{"actions":[]}' -Encoding utf8
    }
    AfterEach {
        $env:USERPROFILE = $script:oldUP
        if ($null -eq $script:oldHome) { Remove-Item Env:HOME -ErrorAction SilentlyContinue } else { $env:HOME = $script:oldHome }
        if ($null -eq $script:oldApp) { Remove-Item Env:APPDATA -ErrorAction SilentlyContinue } else { $env:APPDATA = $script:oldApp }
        if ($null -eq $script:oldLocal) { Remove-Item Env:LOCALAPPDATA -ErrorAction SilentlyContinue } else { $env:LOCALAPPDATA = $script:oldLocal }
        if ($null -eq $script:oldVs) { Remove-Item Env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS = $script:oldVs }
        if ($null -eq $script:oldCur) { Remove-Item Env:CLAUDE_SETUP_CURSOR_KEYBINDINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS = $script:oldCur }
        if ($null -eq $script:oldWt) { Remove-Item Env:CLAUDE_SETUP_WT_SETTINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_WT_SETTINGS = $script:oldWt }
        Remove-Item -Recurse -Force $script:sandbox -ErrorAction SilentlyContinue
    }

    It "a real -Hooks install creates the hook files, the shim and settings.json" {
        $r = Invoke-Script $script:Setup @("-Hooks")
        $r.ExitCode | Should -Be 0
        $hooksDir = Join-Path $env:USERPROFILE ".claude\hooks"
        Test-Path (Join-Path $hooksDir "danger_guard.py") | Should -Be $true
        Test-Path (Join-Path $hooksDir "send_to_trash.py") | Should -Be $true
        Test-Path (Join-Path $hooksDir "shims/rm") | Should -Be $true
        Test-Path (Join-Path $hooksDir "shims/RmShim.psm1") | Should -Be $true
        Test-Path (Join-Path $hooksDir "secrets_guard.py") | Should -Be $false
        Test-Path (Join-Path $hooksDir "graft_sync_hidden.cjs") | Should -Be $true
        $settings = Get-Content (Join-Path $env:USERPROFILE ".claude\settings.json") -Raw | ConvertFrom-Json
        $settings.hooks.PreToolUse.Count | Should -Be 1
        $settings.hooks.SessionStart.Count | Should -Be 1
        $settings.env.GRAFT_TEST_SYNC_RUN | Should -Match '/hooks/graft_sync_hidden\.cjs$'
    }

    It "the manifest (added_allow) survives an idempotent rerun without duplicates" {
        Invoke-Script $script:Setup @("-Hooks") | Out-Null
        $r2 = Invoke-Script $script:Setup @("-Hooks")
        $r2.ExitCode | Should -Be 0
        $settings = Get-Content (Join-Path $env:USERPROFILE ".claude\settings.json") -Raw | ConvertFrom-Json
        $settings.hooks.PreToolUse.Count | Should -Be 1
        $settings.hooks.SessionStart.Count | Should -Be 1
        $manifest = Get-Content (Join-Path $env:USERPROFILE ".claude\.claude-code-setup.json") -Raw | ConvertFrom-Json
        $manifest.added_allow.Count | Should -BeGreaterThan 0
        $manifest.default_mode_changed | Should -Be $true
    }

    It "-Uninstall restores the pre-install state (no settings file)" {
        Invoke-Script $script:Setup @("-Hooks") | Out-Null
        $r = Invoke-Script $script:Setup @("-Uninstall")
        $r.ExitCode | Should -Be 0
        Test-Path (Join-Path $env:USERPROFILE ".claude\hooks\danger_guard.py") | Should -Be $false
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }

    It "keeps the existing settings.json model/env and only switches defaultMode to auto" {
        New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE ".claude") | Out-Null
        $seed = @{ env = @{ MY_VAR = "keep-me" }; model = "sonnet"; permissions = @{ defaultMode = "acceptEdits" } } | ConvertTo-Json -Depth 5
        Set-Content -Path (Join-Path $env:USERPROFILE ".claude\settings.json") -Value $seed -Encoding utf8
        $r = Invoke-Script $script:Setup @("-Hooks")
        $r.ExitCode | Should -Be 0
        $after = Get-Content (Join-Path $env:USERPROFILE ".claude\settings.json") -Raw | ConvertFrom-Json
        $after.env.MY_VAR | Should -Be "keep-me"
        $after.model | Should -Be "sonnet"
        $after.permissions.defaultMode | Should -Be "auto"
    }

    # OMC 설치는 실제 claude CLI 를 부르므로, 설치 결과(settings + 영수증)를 심어 두고 제거 경로만 검증한다.
    It "-Uninstall -Hooks leaves the omc_hud manifest, then -Uninstall -Omc reverts the cache TTL setting" {
        Invoke-Script $script:Setup @("-Hooks") | Out-Null
        $claudeDir = Join-Path $env:USERPROFILE ".claude"
        $settingsPath = Join-Path $claudeDir "settings.json"
        $manifestPath = Join-Path $claudeDir ".claude-code-setup.json"
        $omcCmd = 'sh "$HOME/.claude/hud/omc-hud-cache.sh" "$HOME/.claude/hud/omc-hud.mjs"'
        $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
        $settings | Add-Member -NotePropertyName statusLine -NotePropertyValue ([pscustomobject]@{
            type = "command"; command = 'node "$HOME/.claude/hud/omc-hud-ttl.mjs" ' + $omcCmd; refreshInterval = 10 })
        Set-Content -Path $settingsPath -Value ($settings | ConvertTo-Json -Depth 20) -Encoding utf8
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        $manifest | Add-Member -NotePropertyName omc_hud -NotePropertyValue ([pscustomobject]@{ refresh_interval_added = $true })
        Set-Content -Path $manifestPath -Value ($manifest | ConvertTo-Json -Depth 20) -Encoding utf8

        (Invoke-Script $script:Setup @("-Uninstall", "-Hooks")).ExitCode | Should -Be 0
        (Get-Content $manifestPath -Raw | ConvertFrom-Json).omc_hud.refresh_interval_added | Should -Be $true

        $r = Invoke-Script $script:Setup @("-Uninstall", "-Omc")
        $r.ExitCode | Should -Be 0
        $after = (Get-Content $settingsPath -Raw | ConvertFrom-Json).statusLine
        $after.command | Should -Be $omcCmd
        $after.PSObject.Properties.Name | Should -Not -Contain "refreshInterval"
        Test-Path $manifestPath | Should -Be $false
    }

    It "-Omc -Uninstall -DryRun changes nothing" {
        New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE ".claude") | Out-Null
        $settingsPath = Join-Path $env:USERPROFILE ".claude\settings.json"
        $seed = '{"statusLine": {"type": "command", "command": "node \"$HOME/.claude/hud/omc-hud-ttl.mjs\" node x/omc-hud.mjs", "refreshInterval": 10}}'
        Set-Content -Path $settingsPath -Value $seed -Encoding utf8
        $r = Invoke-Script $script:Setup @("-Omc", "-Uninstall", "-DryRun")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "DRY RUN"
        (Get-Content $settingsPath -Raw).Trim() | Should -Be $seed
    }

    It "-Uninstall -Hooks leaves the output_style manifest, then -Uninstall -OutputStyle reverts outputStyle" {
        Invoke-Script $script:Setup @("-Hooks") | Out-Null
        $claudeDir = Join-Path $env:USERPROFILE ".claude"
        $settingsPath = Join-Path $claudeDir "settings.json"
        $manifestPath = Join-Path $claudeDir ".claude-code-setup.json"
        $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
        $settings | Add-Member -NotePropertyName outputStyle -NotePropertyValue "fluent-korean:fluent-korean"
        Set-Content -Path $settingsPath -Value ($settings | ConvertTo-Json -Depth 20) -Encoding utf8
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        $manifest | Add-Member -NotePropertyName output_style -NotePropertyValue ([pscustomobject]@{ previous = "Concise"; settings_created = $false })
        Set-Content -Path $manifestPath -Value ($manifest | ConvertTo-Json -Depth 20) -Encoding utf8

        (Invoke-Script $script:Setup @("-Uninstall", "-Hooks")).ExitCode | Should -Be 0
        (Get-Content $manifestPath -Raw | ConvertFrom-Json).output_style.previous | Should -Be "Concise"

        $r = Invoke-Script $script:Setup @("-Uninstall", "-OutputStyle")
        $r.ExitCode | Should -Be 0
        (Get-Content $settingsPath -Raw | ConvertFrom-Json).outputStyle | Should -Be "Concise"
        Test-Path $manifestPath | Should -Be $false
    }

    It "the default full install with -NoOnboard does not install mods" {
        $r = Invoke-Script $script:Setup @("-NoOnboard")
        $r.ExitCode | Should -Be 0
        $claudeDir = Join-Path $env:USERPROFILE ".claude"
        Test-Path (Join-Path $claudeDir "mods") | Should -Be $false
        (Get-Content (Join-Path $claudeDir "settings.json") -Raw) | Should -Not -Match "CLAUDE_CODE_PLUGIN_DIRS"
    }

    It "installs with the long --mods notation and reverts only the mods with -Uninstall -Mods" {
        $claudeDir = Join-Path $env:USERPROFILE ".claude"
        New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null
        Set-Content -Path (Join-Path $claudeDir "settings.json") -Value '{"model": "opus"}' -Encoding utf8
        (Invoke-ScriptInline $script:Setup "--mods").ExitCode | Should -Be 0
        Test-Path (Join-Path $claudeDir "mods\cache-ttl-status\hooks\register.ts") | Should -Be $true
        (Invoke-Script $script:Setup @("-Uninstall", "-Mods")).ExitCode | Should -Be 0
        Test-Path (Join-Path $claudeDir "mods") | Should -Be $false
        $after = Get-Content (Join-Path $claudeDir "settings.json") -Raw | ConvertFrom-Json
        $after.model | Should -Be "opus"
        $after.PSObject.Properties.Name | Should -Not -Contain "env"
    }

    Context "claude CLI stub" {
        BeforeAll {
            # 실제 claude 를 부르지 않도록 PATH 앞에 기록만 하는 스텁을 둔다. Windows 는 claude.cmd,
            # Linux/macOS 의 pwsh 는 배치 파일을 실행하지 못하므로 같은 일을 하는 셸 스크립트를 함께 둔다.
            function Set-ClaudeStub([string]$Log, [string]$ListLine) {
                $cmd = @()
                if ($Log) { $cmd += "@echo %* >> `"$Log`"" }
                $cmd += "@if `"%1 %2`"==`"plugin list`" echo   $ListLine"
                Set-Content -Path (Join-Path $script:stubBin "claude.cmd") -Encoding ascii -Value $cmd
                if ($IsLinux -or $IsMacOS) {
                    $sh = @("#!/bin/sh")
                    if ($Log) { $sh += "echo `"`$*`" >> '$Log'" }
                    $sh += "[ `"`$1 `$2`" = 'plugin list' ] && echo '  $ListLine'"
                    $sh += "exit 0"
                    $p = Join-Path $script:stubBin "claude"
                    Set-Content -Path $p -Encoding ascii -Value $sh
                    chmod +x $p
                }
            }
        }
        BeforeEach {
            $script:stubBin = Join-Path $script:sandbox "stubbin"
            New-Item -ItemType Directory -Force -Path $script:stubBin | Out-Null
            $script:claudeLog = Join-Path $script:sandbox "claude.log"
            Set-ClaudeStub -Log $script:claudeLog -ListLine "other@x"
            $script:oldPath = $env:PATH
            $env:PATH = $script:stubBin + [System.IO.Path]::PathSeparator + $env:PATH
        }
        AfterEach { $env:PATH = $script:oldPath }

        It "-OutputStyle installs the fluent-korean plugin and sets only outputStyle" {
            $r = Invoke-Script $script:Setup @("-OutputStyle")
            $r.ExitCode | Should -Be 0
            $calls = Get-Content $script:claudeLog -Raw
            $calls | Should -Match "plugin marketplace add snflkd/fluent-korean"
            $calls | Should -Match "plugin install fluent-korean@fluent-korean"
            $after = Get-Content (Join-Path $env:USERPROFILE ".claude\settings.json") -Raw | ConvertFrom-Json
            $after.outputStyle | Should -Be "fluent-korean:fluent-korean"
            # -OutputStyle 만 줬으므로 훅은 설치되지 않는다
            $after.PSObject.Properties.Name | Should -Not -Contain "hooks"
        }

        It "after -Omc -Mods on an empty home, -Uninstall leaves no settings.json and no mods" {
            Set-ClaudeStub -ListLine "oh-my-claudecode@omc"
            # HUD 래퍼 템플릿을 복사할 플러그인 캐시를 흉내 낸다
            $lib = Join-Path $env:USERPROFILE ".claude\plugins\cache\omc\oh-my-claudecode\5.4.0\scripts\lib"
            New-Item -ItemType Directory -Force -Path $lib | Out-Null
            Set-Content -Path (Join-Path $lib "hud-wrapper-template.txt") -Value "// template" -Encoding ascii
            Set-Content -Path (Join-Path $lib "config-dir.mjs") -Value "// config" -Encoding ascii
            $claudeDir = Join-Path $env:USERPROFILE ".claude"

            (Invoke-Script $script:Setup @("-Omc", "-Mods")).ExitCode | Should -Be 0
            $after = Get-Content (Join-Path $claudeDir "settings.json") -Raw | ConvertFrom-Json
            $after.statusLine.command | Should -Match "omc-hud-ttl.mjs"
            # 목록 구분자는 OS 의 경로 구분자다(apply.py 의 os.pathsep — Windows ';', 그 외 ':').
            $after.env.CLAUDE_CODE_PLUGIN_DIRS | Should -Be ((Join-Path $claudeDir "mods\bash-diff-filter") + [System.IO.Path]::PathSeparator + (Join-Path $claudeDir "mods\cache-ttl-status"))
            Test-Path (Join-Path $claudeDir "mods\bash-diff-filter\hooks\register.ts") | Should -Be $true
            Test-Path (Join-Path $claudeDir "mods\cache-ttl-status\hooks\register.ts") | Should -Be $true

            (Invoke-Script $script:Setup @("-Uninstall")).ExitCode | Should -Be 0
            Test-Path (Join-Path $claudeDir "settings.json") | Should -Be $false
            Test-Path (Join-Path $claudeDir "mods") | Should -Be $false
            Test-Path (Join-Path $claudeDir ".claude-code-setup.json") | Should -Be $false
        }

        It "--output-style --dry-run neither installs claude nor writes settings" {
            $r = Invoke-ScriptInline $script:Setup "--output-style --dry-run"
            $r.ExitCode | Should -Be 0
            $r.Output | Should -Match "\(dry-run\) claude plugin install fluent-korean@fluent-korean"
            (Get-Content $script:claudeLog -Raw) | Should -Not -Match "install"
            Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
        }
    }
}

# Windows PowerShell 5.1 은 BOM 없는 UTF-8 .ps1 을 OS ANSI 코드페이지([System.Text.Encoding]::Default)
# 로 읽는다. DBCS 코드페이지(한국어 949, 일본어 932, 중국어 936 등) 에서는 UTF-8 멀티바이트
# 시퀀스의 특정 바이트가 개행/따옴표까지 삼켜버려 스크립트 전체가 파싱조차 안 된다 — 실측 확인됨.
Describe "Windows .ps1 encoding regression (BOM)" {
    It "every shipped .ps1 file must start with a UTF-8 BOM" {
        $files = @(
            "scripts\setup.ps1", "scripts\setup_hooks.ps1", "scripts\setup_agentsmd.ps1",
            "scripts\lib\SetupCommon.ps1", "scripts\setup_output_style.ps1", "scripts\setup_mods.ps1", "tests\Setup.Tests.ps1"
        )
        foreach ($f in $files) {
            $path = Join-Path $script:RepoRoot $f
            $bytes = [System.IO.File]::ReadAllBytes($path)
            $hasBom = ($bytes.Length -ge 3) -and ($bytes[0] -eq 0xEF) -and ($bytes[1] -eq 0xBB) -and ($bytes[2] -eq 0xBF)
            $hasBom | Should -Be $true -Because "$f without a BOM can fail to parse on Windows PowerShell 5.1 with a DBCS locale"
        }
    }

    # install.ps1 은 파일로 실행되지 않고 `irm | iex` 로 문자열이 된다. 5.1 의 irm 은 BOM 을
    # U+FEFF 문자로 남기고, 파서는 그걸 공백이 아닌 명령 이름으로 읽어 첫 줄 `<#` 주석부터
    # 무너진다 (실측). 디코딩은 raw.githubusercontent 의 charset=utf-8 헤더가 맡으므로 BOM 이 필요 없다.
    It "install.ps1 must start without a BOM (irm | iex path)" {
        $bytes = [System.IO.File]::ReadAllBytes((Join-Path $script:RepoRoot "install.ps1"))
        $hasBom = ($bytes.Length -ge 3) -and ($bytes[0] -eq 0xEF) -and ($bytes[1] -eq 0xBB) -and ($bytes[2] -eq 0xBF)
        $hasBom | Should -Be $false -Because "irm | iex fails with a parse error on Windows PowerShell 5.1"
    }

    # powershell.exe 는 Windows 에만 있다. 없는 곳에서 '실패'로 잡으면 진짜 실패가 묻힌다 —
    # 건너뛴 것은 통과가 아니라 '검증 안 됨'이며, Pester 요약에 Skipped 로 정직하게 남는다.
    It "setup.ps1 -Help parses and runs correctly under powershell.exe (Windows PowerShell 5.1)" -Skip:(-not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
        $out = powershell.exe -ExecutionPolicy Bypass -File $script:Setup -Help 2>&1 | Out-String
        $ec = $LASTEXITCODE
        $ec | Should -Be 0
        # 비ASCII 줄로 확인해야 BOM 없이 ANSI 로 읽혀 깨진 경우를 잡는다.
        $out | Should -Match "ai-setup — Claude Code user-level setup"
    }
}

# S1: PS 7.4+ 에서 $PSNativeCommandUseErrorActionPreference 가 $true 인 환경(사용자 프로필/그룹
# 정책/향후 PS 버전 기본값 변경 등) 에서는 `& python -c "import send2trash" *> $null` 같은 네이티브
# 명령의 0이 아닌 종료 코드가 예외로 승격되어 첫 설치가 통째로 실패한다 (실측 재현됨). 이 저장소는
# 공유 send2trash 패키지를 설치/제거하며 동적으로 재현하는 대신, 방어 코드가 소스에 남아있는지
# 정적으로 확인한다 (동적 재현은 Phase 2 수기 검증에서 이미 수행함 — docs/HANDOFF.md 참고).
Describe "native command error escalation guard regression (S1)" {
    It "scripts that judge native commands by LASTEXITCODE explicitly turn off PSNativeCommandUseErrorActionPreference" {
        $files = @(
            "scripts\setup.ps1", "scripts\setup_hooks.ps1", "install.ps1", "scripts\lib\SetupCommon.ps1"
        )
        foreach ($f in $files) {
            $path = Join-Path $script:RepoRoot $f
            $content = Get-Content -Path $path -Raw
            $content | Should -Match '\$PSNativeCommandUseErrorActionPreference\s*=\s*\$false' `
                -Because "$f judges native command failures by `$LASTEXITCODE directly, so PS 7.4+ must not escalate them to exceptions"
        }
    }
}

# 온보딩은 인자 없이 실행할 때만 파이썬을 찾는다. Windows 런처 `py -3` 을 Get-Command 존재만으로
# 고르면, `py` 가 실제로는 python.exe(또는 python.exe 와 같은 바이너리)인 머신에서
# `Unknown option: -3` 이 stderr 로 나오고, Windows PowerShell 5.1 은 그걸 NativeCommandError
# 로 승격시켜 설치 전체가 죽는다 (실측: setup.ps1:95). pwsh 7 은 *> $null 로 삼키고 온보딩만
# 건너뛰므로, 이 회귀는 5.1 로 돌려야 사용자 증상을 재현한다.
#
# python 이 PATH 에 남아 있으면 리졸버가 py 보다 python 을 먼저 고르므로 스텁이 실행되지 않는다.
# 그래서 python/python3 은 실패 스텁으로 가리고, py.cmd 만 -3 을 거부한 뒤 나머지 인자는 진짜
# 인터프리터로 넘긴다 — try/catch 와 `py` 빈 Args 후보가 둘 다 실제로 밟힌다.
Describe "onboarding Python detection (py -3 NativeCommandError regression)" {
    BeforeEach {
        $script:realPython = (Get-Command python -CommandType Application -ErrorAction SilentlyContinue).Source
        $script:sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-py3-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:stub = Join-Path $script:sandbox "stubbin"
        New-Item -ItemType Directory -Force -Path $script:stub | Out-Null
        Set-Content -Path (Join-Path $script:stub "python.cmd") -Value "@echo off`r`nexit /b 1" -Encoding ascii
        Set-Content -Path (Join-Path $script:stub "python3.cmd") -Value "@echo off`r`nexit /b 1" -Encoding ascii
        if ($script:realPython) {
            $pyCmd = @(
                "@echo off",
                "if `"%~1`"==`"-3`" (",
                "  echo Unknown option: -3 1>&2",
                "  exit /b 2",
                ")",
                "`"$($script:realPython)`" %*"
            ) -join "`r`n"
            Set-Content -Path (Join-Path $script:stub "py.cmd") -Value $pyCmd -Encoding ascii
        }

        $script:oldUP = $env:USERPROFILE
        $script:oldHome = $env:HOME
        $script:oldApp = $env:APPDATA
        $script:oldLocal = $env:LOCALAPPDATA
        $script:oldPath = $env:PATH
        $script:oldCI = $env:CI
        $script:oldLoc = Get-Location
        $script:oldVs = $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS
        $script:oldCur = $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS
        $script:oldWt = $env:CLAUDE_SETUP_WT_SETTINGS
        $env:USERPROFILE = $script:sandbox
        $env:HOME = $script:sandbox
        $env:APPDATA = Join-Path $script:sandbox "appdata"
        $env:LOCALAPPDATA = Join-Path $script:sandbox "local"
        $env:CI = "1"
        New-Item -ItemType Directory -Force -Path $env:APPDATA | Out-Null
        New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA | Out-Null
        $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS = Join-Path $script:sandbox "vscode-keybindings.json"
        $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS = Join-Path $script:sandbox "cursor-keybindings.json"
        $env:CLAUDE_SETUP_WT_SETTINGS = Join-Path $script:sandbox "wt-settings.json"
        Set-Content -Path $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Value '[]' -Encoding utf8
        Set-Content -Path $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS -Value '[]' -Encoding utf8
        Set-Content -Path $env:CLAUDE_SETUP_WT_SETTINGS -Value '{"actions":[]}' -Encoding utf8
        $env:PATH = "$($script:stub);$($script:oldPath)"
        Set-Location $script:sandbox
    }
    AfterEach {
        Set-Location $script:oldLoc
        $env:USERPROFILE = $script:oldUP
        $env:PATH = $script:oldPath
        if ($null -eq $script:oldCI) { Remove-Item Env:CI -ErrorAction SilentlyContinue } else { $env:CI = $script:oldCI }
        if ($null -eq $script:oldHome) { Remove-Item Env:HOME -ErrorAction SilentlyContinue } else { $env:HOME = $script:oldHome }
        if ($null -eq $script:oldApp) { Remove-Item Env:APPDATA -ErrorAction SilentlyContinue } else { $env:APPDATA = $script:oldApp }
        if ($null -eq $script:oldLocal) { Remove-Item Env:LOCALAPPDATA -ErrorAction SilentlyContinue } else { $env:LOCALAPPDATA = $script:oldLocal }
        if ($null -eq $script:oldVs) { Remove-Item Env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS = $script:oldVs }
        if ($null -eq $script:oldCur) { Remove-Item Env:CLAUDE_SETUP_CURSOR_KEYBINDINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS = $script:oldCur }
        if ($null -eq $script:oldWt) { Remove-Item Env:CLAUDE_SETUP_WT_SETTINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_WT_SETTINGS = $script:oldWt }
        Remove-Item -Recurse -Force $script:sandbox -ErrorAction SilentlyContinue
    }

    It "on powershell.exe 5.1 the install survives py -3 being an Unknown option by falling through to empty Args" -Skip:(-not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
        if (-not $script:realPython) {
            Set-ItResult -Skipped -Because "a real python must be on PATH so the stub py can delegate everything except -3"
            return
        }
        $out = powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script:Setup 2>&1 | Out-String
        # 온보딩 리졸버가 py.cmd 를 고르면 이후 셀프테스트의 Process.Start('py') 는
        # .cmd 를 찾지 못해 실패할 수 있다. 이 케이스가 잠그는 건 그 셀프테스트가 아니라
        # 'py -3 NativeCommandError 로 setup.ps1 이 즉시 죽는가' 이므로, 훅 파일이 남았는지와
        # NativeCommandError 부재로 판정한다.
        $out | Should -Not -Match "NativeCommandError" -Because "a py -3 failure must be swallowed by try/catch and move on to the next candidate"
        $out | Should -Not -Match "Python not found"
        Test-Path (Join-Path $env:USERPROFILE ".claude\hooks\danger_guard.py") | Should -Be $true `
            -Because "the original crash died before the hooks were installed; if the file remains, onboarding detection survived"
    }

    # 5.1 은 출력이 리다이렉트되면 네이티브 stderr 를 오류 레코드로 바꾼다. 온보딩이 '물을 수 없음'(2)을
    # stderr 로 알리는 순간 $ErrorActionPreference=Stop 이 설치를 죽이면, 기본값 설치가 중단으로 둔갑한다.
    It "on powershell.exe 5.1 an onboarding that cannot ask and says so on stderr still installs the defaults" -Skip:(-not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
        if (-not $script:realPython) {
            Set-ItResult -Skipped -Because "a real python must be on PATH so the stub py can run the onboarding stub"
            return
        }
        $repo = Join-Path $script:sandbox "repo"
        New-Item -ItemType Directory -Force -Path $repo | Out-Null
        Copy-Item -Recurse (Join-Path $script:RepoRoot "scripts"), (Join-Path $script:RepoRoot "res") $repo
        Set-Content -Path (Join-Path $repo "res\onboard.py") -Encoding ascii `
            -Value "import sys`nsys.stderr.write('cannot ask here\n')`nsys.exit(2)"
        # 리다이렉트는 5.1 세션 안에서 해야 재현된다(-File 로 바깥에서 받으면 stderr 가 그대로 흐른다).
        # NativeCommandError 표시는 남지만, 설치를 멈추지 않으면 된다. 종료 코드는 보지 않는다 — 이
        # Describe 의 py.cmd 대역 때문에 뒤따르는 셀프테스트가 실패할 수 있다(위 케이스 주석 참고).
        $setup = Join-Path $repo "scripts\setup.ps1"
        $out = powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '$setup' 2>&1 | Out-String" 2>&1 | Out-String
        $out | Should -Not -Match "Aborting installation"
        Test-Path (Join-Path $env:USERPROFILE ".claude\hooks\danger_guard.py") | Should -Be $true -Because $out
    }
}

# 온보딩(res/onboard.py)은 인자 없이 실행할 때만 뜬다. 여기서 지키려는 건 두 가지다:
# 콘솔이 없을 때 아무것도 골라버리지 않을 것, 그리고 기존 플래그 호출이 멈추지 않을 것.
Describe "onboarding wiring" {
    BeforeEach {
        $script:sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-onboard-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:oldUP = $env:USERPROFILE
        $env:USERPROFILE = $script:sandbox
    }
    AfterEach {
        $env:USERPROFILE = $script:oldUP
        Remove-Item -Recurse -Force $script:sandbox -ErrorAction SilentlyContinue
    }

    It "-Help lists what can be chosen in onboarding" {
        $r = Invoke-Script $script:Setup @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "onboarding"
        $r.Output | Should -Match "bypassPermissions"
    }

    It "passing a flag does not launch onboarding" {
        # 자동화/CI 가 쓰던 기존 호출이 프롬프트를 기다리며 멈추면 안 된다.
        $r = Invoke-Script $script:Setup @("-Hooks", "-DryRun")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "What would you like to install"
    }

    It "-NoOnboard proceeds with the default behavior without onboarding" {
        $r = Invoke-Script $script:Setup @("-NoOnboard", "-DryRun")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "What would you like to install"
        $r.Output | Should -Match "DRY RUN"
    }

    It "onboard.py leaves no selection and exits 2 when there is no console" {
        $onboard = Join-Path $script:RepoRoot "res\onboard.py"
        $answers = Join-Path $script:sandbox "answers.txt"
        $py = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
        & $py -X utf8 $onboard --out $answers *> $null
        $LASTEXITCODE | Should -Be 2 -Because "picking anything in an environment that cannot ask becomes an install the user never agreed to"

        $written = if (Test-Path $answers) { Get-Content $answers -Raw -ErrorAction SilentlyContinue } else { $null }
        [string]::IsNullOrWhiteSpace($written) | Should -BeTrue -Because "if no selection was received, the result file must be empty too"
    }

    It "if onboarding breaks midway, it does not proceed with defaults and installs nothing" {
        # 2(물을 수 없음)만 기본값으로 진행한다. 1(프롬프트가 깨짐)·traceback 은 고르던 중이었다.
        $repo = Join-Path $script:sandbox "repo"
        New-Item -ItemType Directory -Force -Path $repo | Out-Null
        Copy-Item -Recurse (Join-Path $script:RepoRoot "scripts"), (Join-Path $script:RepoRoot "res") $repo
        Set-Content -Path (Join-Path $repo "res/onboard.py") -Value "import sys`nsys.exit(1)" -Encoding ascii
        # 회귀로 기본값 설치가 진행돼도 POSIX pwsh 의 워커가 실제 홈에 쓰지 않도록 HOME 도 격리한다.
        $oldHome = $env:HOME
        $env:HOME = $script:sandbox
        Push-Location $script:sandbox
        try {
            $r = Invoke-Script (Join-Path $repo "scripts/setup.ps1") @()
        } finally { Pop-Location; $env:HOME = $oldHome }
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "Aborting installation"
        Join-Path $script:sandbox ".claude" | Should -Not -Exist
        Join-Path $script:sandbox "AGENTS.md" | Should -Not -Exist
    }
}

Describe "the values picked in onboarding are reflected in the install" {
    BeforeEach {
        $script:sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-mode-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:oldUP = $env:USERPROFILE
        $env:USERPROFILE = $script:sandbox
    }
    AfterEach {
        $env:USERPROFILE = $script:oldUP
        Remove-Item -Recurse -Force $script:sandbox -ErrorAction SilentlyContinue
    }

    It "-DefaultMode bypassPermissions is reflected in the settings.json plan" {
        $r = Invoke-Script $script:SetupHooks @("-DryRun", "-DefaultMode", "bypassPermissions")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "permissions\.defaultMode: None -> 'bypassPermissions'"
    }

    It "without -DefaultMode, the fragment default (auto) is used as is" {
        $r = Invoke-Script $script:SetupHooks @("-DryRun")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "permissions\.defaultMode: None -> 'auto'"
    }

    It "an unknown -DefaultMode is rejected by ValidateSet" {
        $r = Invoke-Script $script:SetupHooks @("-DryRun", "-DefaultMode", "bypass")
        $r.ExitCode | Should -Not -Be 0
    }
}

Describe "AGENTS.md overwrite (-Force)" {
    BeforeEach {
        $script:proj = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-agents-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:proj | Out-Null
        $script:AgentsMd = Join-Path $script:RepoRoot "scripts\setup_agentsmd.ps1"
    }
    AfterEach {
        Remove-Item -Recurse -Force $script:proj -ErrorAction SilentlyContinue
    }

    It "without -Force the existing AGENTS.md is left alone" {
        $target = Join-Path $script:proj "AGENTS.md"
        Set-Content -Path $target -Value "사용자가 손댄 내용" -Encoding UTF8
        Push-Location $script:proj
        try { pwsh -NoProfile -File $script:AgentsMd *> $null } finally { Pop-Location }
        (Get-Content $target -Raw) | Should -Match "사용자가 손댄 내용"
    }

    It "-Force backs up the original before overwriting" {
        $target = Join-Path $script:proj "AGENTS.md"
        Set-Content -Path $target -Value "사용자가 손댄 내용" -Encoding UTF8
        Push-Location $script:proj
        try { pwsh -NoProfile -File $script:AgentsMd -Force *> $null } finally { Pop-Location }

        $backups = @(Get-ChildItem -Path $script:proj -Filter "AGENTS.md.bak.*")
        $backups.Count | Should -Be 1 -Because "overwriting user content must leave a way to undo it"
        (Get-Content $backups[0].FullName -Raw) | Should -Match "사용자가 손댄 내용"
        (Get-Content $target -Raw) | Should -Not -Match "사용자가 손댄 내용"
    }
}

Describe "project instructions harness selection" {
    BeforeEach {
        $script:proj = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-harness-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:proj | Out-Null
    }
    AfterEach {
        Remove-Item -Recurse -Force $script:proj -ErrorAction SilentlyContinue
    }

    It "with no arguments every harness is installed - AGENTS.md and CLAUDE.md" {
        (Invoke-AgentsMdIn $script:proj).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $true
    }

    It "-Harness codex does not create CLAUDE.md" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "codex")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $false -Because "Codex reads AGENTS.md directly"
    }

    It "-Harness grok,opencode does not create CLAUDE.md" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "grok,opencode")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $false
    }

    It "-Harness claude,codex is a multi-select that installs both" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude,codex")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $true
    }

    It "-Harness all is the same as -Harness claude,codex,grok,opencode" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "all")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $true
    }

    It "CLAUDE.md imports AGENTS.md" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude")).ExitCode | Should -Be 0
        (Get-Content (Join-Path $script:proj "CLAUDE.md") -Raw) | Should -Match "@AGENTS\.md"
    }

    It "an unknown harness installs nothing and fails" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "cursor")).ExitCode | Should -Not -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $false -Because "input that cannot be judged must stop the run"
    }

    It "-DryRun creates no files whichever harness is chosen" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude,codex", "-DryRun")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $false
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $false
    }

    It "an existing CLAUDE.md is left alone without -Force" {
        $target = Join-Path $script:proj "CLAUDE.md"
        Set-Content -Path $target -Value "사용자가 손댄 내용" -Encoding UTF8
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude")).ExitCode | Should -Be 0
        (Get-Content $target -Raw) | Should -Match "사용자가 손댄 내용"
    }

    It "warns about an existing CLAUDE.md that does not import @AGENTS.md" {
        # 건너뛰기 자체는 옳다 — 사용자 콘텐츠다. 다만 그 파일이 AGENTS.md 를 불러오지
        # 않으면 Claude Code 는 방금 설치한 지침을 영영 읽지 않는데, 조용히 성공으로
        # 보고하면 사용자가 알 방법이 없다.
        $target = Join-Path $script:proj "CLAUDE.md"
        Set-Content -Path $target -Value "프로젝트 고유 규칙만 있음" -Encoding UTF8

        $r = Invoke-AgentsMdIn $script:proj @("-Harness", "claude")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "@AGENTS\.md"
        $r.Output | Should -Match "will not read"
        (Get-Content $target -Raw) | Should -Match "프로젝트 고유 규칙만 있음" -Because "warn, but leave the user file untouched"
    }

    It "does not warn about a CLAUDE.md that already imports @AGENTS.md" {
        $target = Join-Path $script:proj "CLAUDE.md"
        Set-Content -Path $target -Value "@AGENTS.md`n`n## 프로젝트 고유" -Encoding UTF8

        $r = Invoke-AgentsMdIn $script:proj @("-Harness", "claude")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "will not read"
    }

    It "-Force also backs up CLAUDE.md before overwriting it" {
        $target = Join-Path $script:proj "CLAUDE.md"
        Set-Content -Path $target -Value "사용자가 손댄 내용" -Encoding UTF8
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude", "-Force")).ExitCode | Should -Be 0

        $backups = @(Get-ChildItem -Path $script:proj -Filter "CLAUDE.md.bak.*")
        $backups.Count | Should -Be 1 -Because "it must get the same recovery guarantee as AGENTS.md"
        (Get-Content $backups[0].FullName -Raw) | Should -Match "사용자가 손댄 내용"
        (Get-Content $target -Raw) | Should -Match "@AGENTS\.md"
    }

    # setup.sh 처럼 긴 표기 --harness 도 디스패처를 거쳐 워커까지 가야 한다.
    It "setup.ps1 --agentsmd --harness codex does not create CLAUDE.md" {
        $oldUP = $env:USERPROFILE
        $env:USERPROFILE = $script:proj
        Push-Location $script:proj
        try {
            $r = Invoke-ScriptInline $script:Setup "--agentsmd --harness codex"
        } finally { Pop-Location; $env:USERPROFILE = $oldUP }
        $r.ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $false
    }
}

# 줄바꿈 키바인드 디스패처. 실제 프로필을 건드리지 않도록 HOME/APPDATA 와
# CLAUDE_SETUP_* 경로를 샌드박스로 돌린다.
Describe "keybinding dispatcher" {
    BeforeEach {
        $script:sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-kb-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:oldUP = $env:USERPROFILE
        $script:oldHome = $env:HOME
        $script:oldApp = $env:APPDATA
        $script:oldLocal = $env:LOCALAPPDATA
        $script:oldVs = $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS
        $script:oldCur = $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS
        $script:oldWt = $env:CLAUDE_SETUP_WT_SETTINGS
        $env:USERPROFILE = $script:sandbox
        $env:HOME = $script:sandbox
        $env:APPDATA = Join-Path $script:sandbox "appdata"
        $env:LOCALAPPDATA = Join-Path $script:sandbox "local"
        New-Item -ItemType Directory -Force -Path $env:APPDATA | Out-Null
        New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA | Out-Null
        $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS = Join-Path $script:sandbox "vscode-keybindings.json"
        $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS = Join-Path $script:sandbox "cursor-keybindings.json"
        $env:CLAUDE_SETUP_WT_SETTINGS = Join-Path $script:sandbox "wt-settings.json"
        Set-Content -Path $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Value '[]' -Encoding utf8
        Set-Content -Path $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS -Value '[]' -Encoding utf8
        Set-Content -Path $env:CLAUDE_SETUP_WT_SETTINGS -Value '{"actions":[]}' -Encoding utf8
    }
    AfterEach {
        $env:USERPROFILE = $script:oldUP
        if ($null -eq $script:oldHome) { Remove-Item Env:HOME -ErrorAction SilentlyContinue } else { $env:HOME = $script:oldHome }
        if ($null -eq $script:oldApp) { Remove-Item Env:APPDATA -ErrorAction SilentlyContinue } else { $env:APPDATA = $script:oldApp }
        if ($null -eq $script:oldLocal) { Remove-Item Env:LOCALAPPDATA -ErrorAction SilentlyContinue } else { $env:LOCALAPPDATA = $script:oldLocal }
        if ($null -eq $script:oldVs) { Remove-Item Env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS = $script:oldVs }
        if ($null -eq $script:oldCur) { Remove-Item Env:CLAUDE_SETUP_CURSOR_KEYBINDINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_CURSOR_KEYBINDINGS = $script:oldCur }
        if ($null -eq $script:oldWt) { Remove-Item Env:CLAUDE_SETUP_WT_SETTINGS -ErrorAction SilentlyContinue } else { $env:CLAUDE_SETUP_WT_SETTINGS = $script:oldWt }
        Remove-Item -Recurse -Force $script:sandbox -ErrorAction SilentlyContinue
    }

    It "-Help shows -Keybinds and -Newline (covers: Test-15)" {
        $r = Invoke-Script $script:Setup @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "Keybinds"
        $r.Output | Should -Match "Newline"
    }

    It "-Keybinds -DryRun writes no target files and shows the paths in the plan (covers: Test-10)" {
        $beforeVs = Get-Content $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Raw
        $beforeWt = Get-Content $env:CLAUDE_SETUP_WT_SETTINGS -Raw
        $r = Invoke-Script $script:Setup @("-Keybinds", "-DryRun")
        $r.ExitCode | Should -Be 0
        (Get-Content $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Raw) | Should -Be $beforeVs
        (Get-Content $env:CLAUDE_SETUP_WT_SETTINGS -Raw) | Should -Be $beforeWt
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
        $r.Output | Should -Match "keybindings.json"
    }

    It "a disallowed -Newline exits 1 and leaves files untouched (covers: Test-8)" {
        $beforeVs = Get-Content $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Raw
        $r = Invoke-Script $script:Setup @("-Keybinds", "-Newline", "foo")
        $r.ExitCode | Should -Be 1
        (Get-Content $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Raw) | Should -Be $beforeVs
        $r.Output | Should -Not -Match "parameter cannot be found"
        $r.Output | Should -Match "Newline|newline|shift-enter"
    }

    It "-Keybinds does not install hooks or AGENTS.md (covers: Test-6)" {
        $r = Invoke-Script $script:Setup @("-Keybinds")
        $r.ExitCode | Should -Be 0
        Test-Path (Join-Path $env:USERPROFILE ".claude\hooks\danger_guard.py") | Should -Be $false
        Test-Path (Join-Path $script:sandbox "AGENTS.md") | Should -Be $false
        Test-Path (Join-Path $env:USERPROFILE ".claude\.claude-code-setup.json") | Should -Be $true
    }
}

Describe "Python-not-installed guidance" {
    It "without Python, setup_hooks.ps1 fails and shows the winget install command" -Skip:(-not $IsWindows) {
        $oldPath = $env:PATH; $oldUP = $env:USERPROFILE
        $sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("cc-pester-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $sandbox | Out-Null
        try {
            $env:USERPROFILE = $sandbox
            # python/python3/py 가 하나도 보이지 않는 PATH (Store 별칭이 있는 WindowsApps 도 뺀다).
            $env:PATH = "$PSHOME;$env:SystemRoot\System32"
            $pwshExe = (Get-Process -Id $PID).Path
            $out = & $pwshExe -NoProfile -File $script:SetupHooks -DryRun 2>&1 | Out-String
            $LASTEXITCODE | Should -Be 1
            $out | Should -Match "Python not found"
            $out | Should -Match "winget install -e --id Python\.Python\.3"
        } finally {
            $env:PATH = $oldPath; $env:USERPROFILE = $oldUP
            Remove-Item -Recurse -Force $sandbox -ErrorAction SilentlyContinue
        }
    }
}

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
        $script:sandbox = Join-Path $env:TEMP ("cc-pester-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
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
        $r.Output | Should -Match "사용법"
    }

    It "-Hooks -DryRun does not create settings.json" {
        Invoke-Script $script:Setup @("-Hooks", "-DryRun") | Out-Null
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }

    It "-Uninstall -DryRun on clean profile exits 0" {
        $r = Invoke-Script $script:SetupHooks @("-Uninstall", "-DryRun")
        $r.ExitCode | Should -Be 0
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }

    # 회귀: 셸에서 직접 실행하면 `--help` 가 위치 인자로 들어와 -Newline 에 바인딩됐고,
    # 도움말 대신 "값은 shift-enter 또는 ctrl-enter 여야 합니다 (받은 값: --help)" 가 나왔다.
    It "셸에서 직접 실행한 --help 도 도움말을 낸다" {
        $r = Invoke-ScriptInline $script:Setup "--help"
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "사용법"
        $r.Output | Should -Match "--no-onboard"
    }

    It "setup.sh 식 --hooks --dry-run 도 받고 훅 범위만 실행한다" {
        $r = Invoke-ScriptInline $script:Setup "--hooks --dry-run"
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "AGENTS.md"      # --hooks 범위가 지켜졌다
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }

    It "잘못된 --newline 값은 표기와 무관하게 exit 1 이다" {
        $r = Invoke-ScriptInline $script:Setup "--keybinds --newline foo"
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "shift-enter"
    }

    # 조용히 무시하면 오타(--keybind)가 '전체 설치' 로 둔갑한다.
    It "알 수 없는 옵션은 exit 1 이고 사용법을 함께 보여준다" {
        $r = Invoke-ScriptInline $script:Setup "--keybind"
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "알 수 없는 옵션"
        $r.Output | Should -Match "사용법"
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }
}

Describe "install.ps1 bootstrap" {
    It "-Help exits 0 without network" {
        $r = Invoke-Script (Join-Path $script:RepoRoot "install.ps1") @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "부트스트랩"
    }

    # scriptblock 형태(= 셸 직접 실행)에서 --help 가 -Newline 에 바인딩되던 회귀.
    It "셸에서 직접 실행한 --help 도 도움말을 낸다" {
        $r = Invoke-ScriptInline (Join-Path $script:RepoRoot "install.ps1") "--help"
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "부트스트랩"
    }

    # --dry-run 은 알아듣고 --bogus 만 거절해야 한다. 거절은 다운로드 전에 일어나므로
    # 이 테스트는 네트워크를 타지 않는다.
    It "알 수 없는 옵션만 거절하고 긴 표기는 소비한다" {
        $r = Invoke-ScriptInline (Join-Path $script:RepoRoot "install.ps1") "--dry-run --bogus"
        $r.ExitCode | Should -Not -Be 0
        $r.Output | Should -Match "--bogus"
        $r.Output | Should -Not -Match "--dry-run"
    }
}

# S2: 기존 Pester 스위트는 -Help / -DryRun 만 밟고 실제 설치 경로를 한 번도 실행하지 않았다.
# macOS 의 치명적 버그(패턴 A)가 정확히 이 빈칸에 숨어 있었던 전례가 있어 추가한다.
Describe "실제 설치 경로 (S2)" {
    BeforeEach {
        $script:sandbox = Join-Path $env:TEMP ("cc-pester-real-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
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

    It "-Hooks 실제 설치가 훅 파일 3개와 settings.json 을 만든다" {
        $r = Invoke-Script $script:Setup @("-Hooks")
        $r.ExitCode | Should -Be 0
        $hooksDir = Join-Path $env:USERPROFILE ".claude\hooks"
        Test-Path (Join-Path $hooksDir "danger_guard.py") | Should -Be $true
        Test-Path (Join-Path $hooksDir "secrets_guard.py") | Should -Be $true
        Test-Path (Join-Path $hooksDir "send_to_trash.py") | Should -Be $true
        $settings = Get-Content (Join-Path $env:USERPROFILE ".claude\settings.json") -Raw | ConvertFrom-Json
        $settings.hooks.PreToolUse.Count | Should -Be 2
    }

    It "멱등 재실행 후에도 중복 없이 영수증(added_allow)이 보존된다" {
        Invoke-Script $script:Setup @("-Hooks") | Out-Null
        $r2 = Invoke-Script $script:Setup @("-Hooks")
        $r2.ExitCode | Should -Be 0
        $settings = Get-Content (Join-Path $env:USERPROFILE ".claude\settings.json") -Raw | ConvertFrom-Json
        $settings.hooks.PreToolUse.Count | Should -Be 2
        $manifest = Get-Content (Join-Path $env:USERPROFILE ".claude\.claude-code-setup.json") -Raw | ConvertFrom-Json
        $manifest.added_allow.Count | Should -BeGreaterThan 0
        $manifest.default_mode_changed | Should -Be $true
    }

    It "-Uninstall 이 설치 전 상태(설정 파일 없음)로 복원한다" {
        Invoke-Script $script:Setup @("-Hooks") | Out-Null
        $r = Invoke-Script $script:Setup @("-Uninstall")
        $r.ExitCode | Should -Be 0
        Test-Path (Join-Path $env:USERPROFILE ".claude\hooks\danger_guard.py") | Should -Be $false
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
    }

    It "기존 settings.json 의 model/env 는 보존하고 defaultMode 만 auto 로 바꾼다" {
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
}

# Windows PowerShell 5.1 은 BOM 없는 UTF-8 .ps1 을 OS ANSI 코드페이지([System.Text.Encoding]::Default)
# 로 읽는다. DBCS 코드페이지(한국어 949, 일본어 932, 중국어 936 등) 에서는 UTF-8 멀티바이트
# 시퀀스의 특정 바이트가 개행/따옴표까지 삼켜버려 스크립트 전체가 파싱조차 안 된다 — 실측 확인됨.
Describe "Windows .ps1 인코딩 회귀 (BOM)" {
    It "배포되는 .ps1 파일은 전부 UTF-8 BOM 으로 시작해야 한다" {
        $files = @(
            "scripts\setup.ps1", "scripts\setup_hooks.ps1", "scripts\setup_agentsmd.ps1",
            "scripts\lib\SetupCommon.ps1", "install.ps1", "tests\Setup.Tests.ps1"
        )
        foreach ($f in $files) {
            $path = Join-Path $script:RepoRoot $f
            $bytes = [System.IO.File]::ReadAllBytes($path)
            $hasBom = ($bytes.Length -ge 3) -and ($bytes[0] -eq 0xEF) -and ($bytes[1] -eq 0xBB) -and ($bytes[2] -eq 0xBF)
            $hasBom | Should -Be $true -Because "$f 에 BOM이 없으면 Windows PowerShell 5.1 + DBCS 로케일에서 파싱이 깨질 수 있음"
        }
    }

    # powershell.exe 는 Windows 에만 있다. 없는 곳에서 '실패'로 잡으면 진짜 실패가 묻힌다 —
    # 건너뛴 것은 통과가 아니라 '검증 안 됨'이며, Pester 요약에 Skipped 로 정직하게 남는다.
    It "powershell.exe(Windows PowerShell 5.1) 로 setup.ps1 -Help 를 실행해도 정상 파싱/실행된다" -Skip:(-not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
        $out = powershell.exe -ExecutionPolicy Bypass -File $script:Setup -Help 2>&1 | Out-String
        $ec = $LASTEXITCODE
        $ec | Should -Be 0
        $out | Should -Match "사용법"
    }
}

# S1: PS 7.4+ 에서 $PSNativeCommandUseErrorActionPreference 가 $true 인 환경(사용자 프로필/그룹
# 정책/향후 PS 버전 기본값 변경 등) 에서는 `& python -c "import send2trash" *> $null` 같은 네이티브
# 명령의 0이 아닌 종료 코드가 예외로 승격되어 첫 설치가 통째로 실패한다 (실측 재현됨). 이 저장소는
# 공유 send2trash 패키지를 설치/제거하며 동적으로 재현하는 대신, 방어 코드가 소스에 남아있는지
# 정적으로 확인한다 (동적 재현은 Phase 2 수기 검증에서 이미 수행함 — docs/HANDOFF.md 참고).
Describe "네이티브 명령 오류 승격 방어 회귀 (S1)" {
    It "네이티브 명령을 LASTEXITCODE 로 판정하는 스크립트는 PSNativeCommandUseErrorActionPreference 를 명시적으로 끈다" {
        $files = @(
            "scripts\setup.ps1", "scripts\setup_hooks.ps1", "install.ps1", "scripts\lib\SetupCommon.ps1"
        )
        foreach ($f in $files) {
            $path = Join-Path $script:RepoRoot $f
            $content = Get-Content -Path $path -Raw
            $content | Should -Match '\$PSNativeCommandUseErrorActionPreference\s*=\s*\$false' `
                -Because "$f 는 네이티브 명령 실패를 `$LASTEXITCODE 로 직접 판정하므로, PS 7.4+ 에서 그 실패가 예외로 승격되면 안 됨"
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
Describe "온보딩 파이썬 탐지 (py -3 NativeCommandError 회귀)" {
    BeforeEach {
        $script:realPython = (Get-Command python -CommandType Application -ErrorAction SilentlyContinue).Source
        $script:sandbox = Join-Path $env:TEMP ("cc-pester-py3-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
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

    It "powershell.exe 5.1 에서 py -3 이 Unknown option 이어도 빈 Args 로 넘어가 설치가 산다" -Skip:(-not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
        if (-not $script:realPython) {
            Set-ItResult -Skipped -Because "PATH 에 진짜 python 이 있어야 스텁 py 가 -3 이외를 위임할 수 있음"
            return
        }
        $out = powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script:Setup 2>&1 | Out-String
        # 온보딩 리졸버가 py.cmd 를 고르면 이후 셀프테스트의 Process.Start('py') 는
        # .cmd 를 찾지 못해 실패할 수 있다. 이 케이스가 잠그는 건 그 셀프테스트가 아니라
        # 'py -3 NativeCommandError 로 setup.ps1 이 즉시 죽는가' 이므로, 훅 파일이 남았는지와
        # NativeCommandError 부재로 판정한다.
        $out | Should -Not -Match "NativeCommandError" -Because "py -3 실패는 try/catch 로 삼키고 다음 후보로 넘어가야 함"
        $out | Should -Not -Match "Python을 찾을 수 없습니다"
        Test-Path (Join-Path $env:USERPROFILE ".claude\hooks\danger_guard.py") | Should -Be $true `
            -Because "원래 크래시는 훅 설치 전에 죽었음. 파일이 남으면 온보딩 탐지가 산 것"
    }
}

# 온보딩(res/onboard.py)은 인자 없이 실행할 때만 뜬다. 여기서 지키려는 건 두 가지다:
# 콘솔이 없을 때 아무것도 골라버리지 않을 것, 그리고 기존 플래그 호출이 멈추지 않을 것.
Describe "온보딩 연결" {
    BeforeEach {
        $script:sandbox = Join-Path $env:TEMP ("cc-pester-onboard-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:oldUP = $env:USERPROFILE
        $env:USERPROFILE = $script:sandbox
    }
    AfterEach {
        $env:USERPROFILE = $script:oldUP
        Remove-Item -Recurse -Force $script:sandbox -ErrorAction SilentlyContinue
    }

    It "-Help 가 온보딩에서 고를 수 있는 항목을 안내한다" {
        $r = Invoke-Script $script:Setup @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "온보딩"
        $r.Output | Should -Match "bypassPermissions"
    }

    It "플래그를 주면 온보딩을 띄우지 않는다" {
        # 자동화/CI 가 쓰던 기존 호출이 프롬프트를 기다리며 멈추면 안 된다.
        $r = Invoke-Script $script:Setup @("-Hooks", "-DryRun")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "무엇을 설치할까요"
    }

    It "-NoOnboard 는 온보딩 없이 기본 동작으로 진행한다" {
        $r = Invoke-Script $script:Setup @("-NoOnboard", "-DryRun")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "무엇을 설치할까요"
        $r.Output | Should -Match "DRY RUN"
    }

    It "onboard.py 는 콘솔이 없으면 아무 선택도 남기지 않고 2 로 끝난다" {
        $onboard = Join-Path $script:RepoRoot "res\onboard.py"
        $answers = Join-Path $script:sandbox "answers.txt"
        $py = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
        & $py -X utf8 $onboard --out $answers *> $null
        $LASTEXITCODE | Should -Be 2 -Because "물어볼 수 없는 환경에서 뭔가를 고르면 사용자가 동의한 적 없는 설치가 된다"

        $written = if (Test-Path $answers) { Get-Content $answers -Raw -ErrorAction SilentlyContinue } else { $null }
        [string]::IsNullOrWhiteSpace($written) | Should -BeTrue -Because "선택을 못 받았으면 결과 파일도 비어 있어야 한다"
    }
}

Describe "온보딩이 고른 값이 설치에 반영된다" {
    BeforeEach {
        $script:sandbox = Join-Path $env:TEMP ("cc-pester-mode-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:oldUP = $env:USERPROFILE
        $env:USERPROFILE = $script:sandbox
    }
    AfterEach {
        $env:USERPROFILE = $script:oldUP
        Remove-Item -Recurse -Force $script:sandbox -ErrorAction SilentlyContinue
    }

    It "-DefaultMode bypassPermissions 가 settings.json 계획에 반영된다" {
        $r = Invoke-Script $script:SetupHooks @("-DryRun", "-DefaultMode", "bypassPermissions")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match '"defaultMode":\s*"bypassPermissions"'
    }

    It "-DefaultMode 를 주지 않으면 조각의 기본값(auto)이 그대로 쓰인다" {
        $r = Invoke-Script $script:SetupHooks @("-DryRun")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match '"defaultMode":\s*"auto"'
    }

    It "알 수 없는 -DefaultMode 는 ValidateSet 이 거부한다" {
        $r = Invoke-Script $script:SetupHooks @("-DryRun", "-DefaultMode", "bypass")
        $r.ExitCode | Should -Not -Be 0
    }
}

Describe "AGENTS.md 덮어쓰기 (-Force)" {
    BeforeEach {
        $script:proj = Join-Path $env:TEMP ("cc-pester-agents-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:proj | Out-Null
        $script:AgentsMd = Join-Path $script:RepoRoot "scripts\setup_agentsmd.ps1"
    }
    AfterEach {
        Remove-Item -Recurse -Force $script:proj -ErrorAction SilentlyContinue
    }

    It "-Force 없이는 기존 AGENTS.md 를 건드리지 않는다" {
        $target = Join-Path $script:proj "AGENTS.md"
        Set-Content -Path $target -Value "사용자가 손댄 내용" -Encoding UTF8
        Push-Location $script:proj
        try { pwsh -NoProfile -File $script:AgentsMd *> $null } finally { Pop-Location }
        (Get-Content $target -Raw) | Should -Match "사용자가 손댄 내용"
    }

    It "-Force 는 덮어쓰기 전에 원본을 백업한다" {
        $target = Join-Path $script:proj "AGENTS.md"
        Set-Content -Path $target -Value "사용자가 손댄 내용" -Encoding UTF8
        Push-Location $script:proj
        try { pwsh -NoProfile -File $script:AgentsMd -Force *> $null } finally { Pop-Location }

        $backups = @(Get-ChildItem -Path $script:proj -Filter "AGENTS.md.bak.*")
        $backups.Count | Should -Be 1 -Because "사용자 콘텐츠를 덮어쓸 때는 되돌릴 방법을 남겨야 한다"
        (Get-Content $backups[0].FullName -Raw) | Should -Match "사용자가 손댄 내용"
        (Get-Content $target -Raw) | Should -Not -Match "사용자가 손댄 내용"
    }
}

Describe "프로젝트 지침 하네스 선택" {
    BeforeEach {
        $script:proj = Join-Path $env:TEMP ("cc-pester-harness-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:proj | Out-Null
    }
    AfterEach {
        Remove-Item -Recurse -Force $script:proj -ErrorAction SilentlyContinue
    }

    It "인자가 없으면 모든 하네스를 설치한다 — AGENTS.md 와 CLAUDE.md" {
        (Invoke-AgentsMdIn $script:proj).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $true
    }

    It "-Harness codex 는 CLAUDE.md 를 만들지 않는다" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "codex")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $false -Because "Codex 는 AGENTS.md 를 직접 읽는다"
    }

    It "-Harness grok,opencode 는 CLAUDE.md 를 만들지 않는다" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "grok,opencode")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $false
    }

    It "-Harness claude,codex 는 다중 선택으로 둘 다 설치한다" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude,codex")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $true
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $true
    }

    It "-Harness all 은 -Harness claude,codex,grok,opencode 와 같다" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "all")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $true
    }

    It "CLAUDE.md 는 AGENTS.md 를 import 한다" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude")).ExitCode | Should -Be 0
        (Get-Content (Join-Path $script:proj "CLAUDE.md") -Raw) | Should -Match "@AGENTS\.md"
    }

    It "알 수 없는 하네스는 아무것도 설치하지 않고 실패한다" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "cursor")).ExitCode | Should -Not -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $false -Because "판정할 수 없는 입력에는 멈춰야 한다"
    }

    It "-DryRun 은 어떤 하네스를 골라도 파일을 만들지 않는다" {
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude,codex", "-DryRun")).ExitCode | Should -Be 0
        Test-Path (Join-Path $script:proj "AGENTS.md") | Should -Be $false
        Test-Path (Join-Path $script:proj "CLAUDE.md") | Should -Be $false
    }

    It "기존 CLAUDE.md 는 -Force 없이는 건드리지 않는다" {
        $target = Join-Path $script:proj "CLAUDE.md"
        Set-Content -Path $target -Value "사용자가 손댄 내용" -Encoding UTF8
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude")).ExitCode | Should -Be 0
        (Get-Content $target -Raw) | Should -Match "사용자가 손댄 내용"
    }

    It "@AGENTS.md 를 import 하지 않는 기존 CLAUDE.md 는 경고한다" {
        # 건너뛰기 자체는 옳다 — 사용자 콘텐츠다. 다만 그 파일이 AGENTS.md 를 불러오지
        # 않으면 Claude Code 는 방금 설치한 지침을 영영 읽지 않는데, 조용히 성공으로
        # 보고하면 사용자가 알 방법이 없다.
        $target = Join-Path $script:proj "CLAUDE.md"
        Set-Content -Path $target -Value "프로젝트 고유 규칙만 있음" -Encoding UTF8

        $r = Invoke-AgentsMdIn $script:proj @("-Harness", "claude")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "@AGENTS\.md"
        $r.Output | Should -Match "읽지 않습니다"
        (Get-Content $target -Raw) | Should -Match "프로젝트 고유 규칙만 있음" -Because "경고는 하되 사용자 파일은 건드리지 않는다"
    }

    It "이미 @AGENTS.md 를 import 하는 CLAUDE.md 에는 경고하지 않는다" {
        $target = Join-Path $script:proj "CLAUDE.md"
        Set-Content -Path $target -Value "@AGENTS.md`n`n## 프로젝트 고유" -Encoding UTF8

        $r = Invoke-AgentsMdIn $script:proj @("-Harness", "claude")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "읽지 않습니다"
    }

    It "-Force 는 CLAUDE.md 도 백업한 뒤 덮어쓴다" {
        $target = Join-Path $script:proj "CLAUDE.md"
        Set-Content -Path $target -Value "사용자가 손댄 내용" -Encoding UTF8
        (Invoke-AgentsMdIn $script:proj @("-Harness", "claude", "-Force")).ExitCode | Should -Be 0

        $backups = @(Get-ChildItem -Path $script:proj -Filter "CLAUDE.md.bak.*")
        $backups.Count | Should -Be 1 -Because "AGENTS.md 와 같은 복구 보장을 받아야 한다"
        (Get-Content $backups[0].FullName -Raw) | Should -Match "사용자가 손댄 내용"
        (Get-Content $target -Raw) | Should -Match "@AGENTS\.md"
    }
}

# 줄바꿈 키바인드 디스패처. 실제 프로필을 건드리지 않도록 HOME/APPDATA 와
# CLAUDE_SETUP_* 경로를 샌드박스로 돌린다.
Describe "키바인드 디스패처" {
    BeforeEach {
        $script:sandbox = Join-Path $env:TEMP ("cc-pester-kb-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
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

    It "-Help 에 -Keybinds 와 -Newline 이 보인다 (covers: Test-15)" {
        $r = Invoke-Script $script:Setup @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "Keybinds"
        $r.Output | Should -Match "Newline"
    }

    It "-Keybinds -DryRun 은 대상 파일을 쓰지 않고 계획에 경로가 보인다 (covers: Test-10)" {
        $beforeVs = Get-Content $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Raw
        $beforeWt = Get-Content $env:CLAUDE_SETUP_WT_SETTINGS -Raw
        $r = Invoke-Script $script:Setup @("-Keybinds", "-DryRun")
        $r.ExitCode | Should -Be 0
        (Get-Content $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Raw) | Should -Be $beforeVs
        (Get-Content $env:CLAUDE_SETUP_WT_SETTINGS -Raw) | Should -Be $beforeWt
        Test-Path (Join-Path $env:USERPROFILE ".claude\settings.json") | Should -Be $false
        $r.Output | Should -Match "keybindings.json"
    }

    It "허용되지 않는 -Newline 은 exit 1 이고 파일을 건드리지 않는다 (covers: Test-8)" {
        $beforeVs = Get-Content $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Raw
        $r = Invoke-Script $script:Setup @("-Keybinds", "-Newline", "foo")
        $r.ExitCode | Should -Be 1
        (Get-Content $env:CLAUDE_SETUP_VSCODE_KEYBINDINGS -Raw) | Should -Be $beforeVs
        $r.Output | Should -Not -Match "parameter cannot be found"
        $r.Output | Should -Match "Newline|newline|shift-enter"
    }

    It "-Keybinds 는 훅과 AGENTS.md 를 설치하지 않는다 (covers: Test-6)" {
        $r = Invoke-Script $script:Setup @("-Keybinds")
        $r.ExitCode | Should -Be 0
        Test-Path (Join-Path $env:USERPROFILE ".claude\hooks\danger_guard.py") | Should -Be $false
        Test-Path (Join-Path $script:sandbox "AGENTS.md") | Should -Be $false
        Test-Path (Join-Path $env:USERPROFILE ".claude\.claude-code-setup.json") | Should -Be $true
    }
}

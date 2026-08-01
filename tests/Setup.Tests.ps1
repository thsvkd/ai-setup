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
}

Describe "install.ps1 bootstrap" {
    It "-Help exits 0 without network" {
        $r = Invoke-Script (Join-Path $script:RepoRoot "install.ps1") @("-Help")
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "부트스트랩"
    }
}

# S2: 기존 Pester 스위트는 -Help / -DryRun 만 밟고 실제 설치 경로를 한 번도 실행하지 않았다.
# macOS 의 치명적 버그(패턴 A)가 정확히 이 빈칸에 숨어 있었던 전례가 있어 추가한다.
Describe "실제 설치 경로 (S2)" {
    BeforeEach {
        $script:sandbox = Join-Path $env:TEMP ("cc-pester-real-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $script:sandbox | Out-Null
        $script:oldUP = $env:USERPROFILE
        $env:USERPROFILE = $script:sandbox
    }
    AfterEach {
        $env:USERPROFILE = $script:oldUP
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

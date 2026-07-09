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

    It "powershell.exe(Windows PowerShell 5.1) 로 setup.ps1 -Help 를 실행해도 정상 파싱/실행된다" {
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

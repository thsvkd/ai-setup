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

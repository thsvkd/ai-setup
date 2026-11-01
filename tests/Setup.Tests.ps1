# ai-setup 의 기능은 모두 jarvis 로 옮겼다. 남은 PowerShell 진입점은 아무것도 바꾸지 않고 jarvis 를 안내한 뒤
# 종료 코드 1 로 끝나야 한다(covers: AI-70).
#   실행: Invoke-Pester tests/Setup.Tests.ps1 -Output Detailed

BeforeAll {
    $script:RepoRoot = Split-Path -Parent $PSScriptRoot
}

Describe "moved to jarvis" {
    It "every PowerShell entry point points to jarvis, exits 1 and writes nothing (covers: AI-70)" {
        $sandbox = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-setup-moved-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path $sandbox | Out-Null
        $oldUP = $env:USERPROFILE; $oldHome = $env:HOME
        $env:USERPROFILE = $sandbox; $env:HOME = $sandbox
        try {
            # pwsh 자신이 새 홈에 캐시·프로필 폴더를 만든다. 그것을 기준선으로 두고 진입점이 더 쓰는지만 본다
            pwsh -NoProfile -Command "exit 0" | Out-Null
            $before = @(Get-ChildItem -Force -Recurse $sandbox | ForEach-Object FullName | Sort-Object)
            foreach ($entry in @("install.ps1", "scripts\setup.ps1", "scripts\Update-Ai.ps1")) {
                foreach ($argList in @(@(), @("-Help"), @("--stages", "all"), @("-Keybinds"), @("-Uninstall"))) {
                    $out = pwsh -NoProfile -File (Join-Path $script:RepoRoot $entry) @argList 2>&1 | Out-String
                    $LASTEXITCODE | Should -Be 1 -Because "$entry $argList"
                    $out | Should -Match "ai-setup has moved into jarvis" -Because "$entry $argList"
                    $out | Should -Match ([regex]::Escape("py -3 -m jarvis module setup plan --json"))
                }
            }
            @(Get-ChildItem -Force -Recurse $sandbox | ForEach-Object FullName | Sort-Object) | Should -Be $before
        } finally {
            $env:USERPROFILE = $oldUP; $env:HOME = $oldHome
            Remove-Item -Recurse -Force $sandbox -ErrorAction SilentlyContinue
        }
    }

    It "install.ps1 run through a scriptblock (irm | iex) does not close the shell" {
        $body = Get-Content -Raw (Join-Path $script:RepoRoot "install.ps1")
        $out = pwsh -NoProfile -Command "& ([scriptblock]::Create(`$args[0])); 'still here'" $body 2>&1 | Out-String
        $out | Should -Match "still here"
    }
}

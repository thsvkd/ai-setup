# res/hooks/shims/RmShim.psm1 이 원본 Remove-Item 과 '관측 가능한 결과'가 같은지 대조한다.
#
# 이 셰임의 존재 이유는 훅이 명령 문자열을 재작성하지 않게 하는 것이다. 그래서 검증도
# "치환된 문자열이 어떻게 생겼나"가 아니라 "같은 명령을 원본 cmdlet 으로 돌렸을 때와 결과가
# 같은가"로 한다. 각 케이스를 동일한 픽스처 두 벌에서 실행하고 살아남은 파일 목록과 오류
# 발생 여부를 비교한다.

BeforeAll {
    $script:RepoRoot = Split-Path -Parent $PSScriptRoot
    $script:ModulePath = Join-Path $RepoRoot 'res/hooks/shims/RmShim.psm1'
    # 픽스처는 저장소 안에 만든다 — 실제 사용자 홈을 테스트 대상으로 쓰지 않는다.
    $script:Base = Join-Path $RepoRoot '.tmp-rmshim-ps'
    if (Test-Path $Base) { Remove-Item -LiteralPath $Base -Recurse -Force }
    New-Item -ItemType Directory -Path $Base -Force | Out-Null

    function New-Fixture([string]$dir) {
        if (Test-Path -LiteralPath $dir) {
            Microsoft.PowerShell.Management\Remove-Item -LiteralPath $dir -Recurse -Force
        }
        New-Item -ItemType Directory -Path (Join-Path $dir 'sub/deep') -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $dir 'emptydir') -Force | Out-Null
        foreach ($n in 'a.txt', 'b.txt', 'c.log', 'name with spaces.txt') {
            'x' | Set-Content -LiteralPath (Join-Path $dir $n)
        }
        'x' | Set-Content -LiteralPath (Join-Path $dir 'sub/deep/x.log')
    }

    function Get-Observation([string]$script, [bool]$UseShim) {
        $dir = Join-Path $Base $(if ($UseShim) { 'shim' } else { 'real' })
        New-Fixture $dir
        $import = if ($UseShim) { "Import-Module '$ModulePath' -Force -DisableNameChecking -Global" } else { '' }
        $body = @"
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$dir'
`$ErrorActionPreference = 'Continue'
$import
`$global:Error.Clear()
$script
if (`$global:Error.Count -gt 0) { Write-Output '<<ERR>>' }
Get-ChildItem -Recurse -Force -Name | Sort-Object | ForEach-Object { Write-Output "F:`$_" }
"@
        $out = & (Join-Path $PSHOME 'pwsh') -NoProfile -Command $body 2>&1
        return (($out | Where-Object { $_ -match '^(F:|<<ERR>>)' }) -join "`n")
    }

    # 셰임이 실제로 잡혔는지, 홈이 샌드박스인지 같은 세션에서 확인하고, 아니면 아무것도 지우지 않고 97 로 끝낸다.
    function Invoke-Guarded([string]$module, [bool]$posixHome, [string]$sandbox, [string]$script) {
        $out = & (Join-Path $PSHOME 'pwsh') -NoProfile -Command @"
`$ErrorActionPreference='Stop'
Import-Module '$module' -Force -DisableNameChecking -Global
if ((Get-Command Remove-Item).Source -ne 'RmShim') { exit 97 }
if ('$posixHome' -eq 'True' -and `$HOME -ne '$sandbox') { exit 97 }
`$ErrorActionPreference='Continue'
$script
"@ 2>&1 | Out-String
        return [pscustomobject]@{ Out = $out; Rc = $LASTEXITCODE }
    }
}

AfterAll {
    if (Test-Path $Base) {
        Microsoft.PowerShell.Management\Remove-Item -LiteralPath $Base -Recurse -Force `
            -ErrorAction SilentlyContinue
    }
}

Describe 'RmShim gives the same result as the real Remove-Item' {
    It '<name>' -ForEach @(
        @{ name = 'plain file';                     script = 'Remove-Item a.txt' }
        @{ name = 'rm alias';                       script = 'rm a.txt' }
        @{ name = 'del alias';                      script = 'del a.txt' }
        @{ name = 'ri alias';                       script = 'ri a.txt' }
        @{ name = 'directory -Recurse';             script = 'Remove-Item sub -Recurse' }
        @{ name = 'directory -Recurse -Force';      script = 'Remove-Item sub -Recurse -Force' }
        @{ name = 'empty directory';                script = 'Remove-Item emptydir' }
        @{ name = 'wildcard';                       script = 'Remove-Item *.txt' }
        @{ name = 'unmatched wildcard';             script = 'Remove-Item *.nomatch' }
        @{ name = 'nonexistent file';               script = 'Remove-Item nope.txt' }
        @{ name = 'nonexistent file -EA Silent';    script = 'Remove-Item nope.txt -ErrorAction SilentlyContinue' }
        @{ name = 'multiple targets';               script = 'Remove-Item a.txt,b.txt,c.log' }
        @{ name = 'only some exist';                script = 'Remove-Item a.txt,nope.txt,b.txt' }
        @{ name = 'name with spaces';               script = 'Remove-Item "name with spaces.txt"' }
        @{ name = 'variable expansion';             script = '$f = "a.txt"; Remove-Item $f' }
        @{ name = 'variable + path join';           script = '$d = "sub"; Remove-Item "$d/deep" -Recurse' }
        @{ name = '-LiteralPath';                   script = 'Remove-Item -LiteralPath a.txt' }
        @{ name = 'explicit -Path';                 script = 'Remove-Item -Path a.txt' }
        @{ name = 'pipeline';                       script = 'Get-ChildItem *.log -Recurse | Remove-Item' }
        @{ name = 'pipeline directory';             script = 'Get-ChildItem -Directory | Remove-Item -Recurse' }
        @{ name = '-WhatIf does not delete';        script = 'Remove-Item a.txt -WhatIf' }
        @{ name = '-Include filter';                script = 'Remove-Item * -Include *.log -Recurse' }
        @{ name = 'nested path';                    script = 'Remove-Item sub/deep/x.log' }
        @{ name = 'non-filesystem provider';        script = '$env:CLAUDETMP="x"; Remove-Item Env:CLAUDETMP' }
    ) {
        $real = Get-Observation $script $false
        $shim = Get-Observation $script $true
        $shim | Should -Be $real
    }
}

Describe 'refuses to delete the entire root/home' {
    # 실제 홈을 대상으로 삼지 않는다. 셰임 import 가 실패하거나 퇴행하면 원본 Remove-Item 이 그대로
    # 지우기 때문이다. 자식 프로세스의 홈을 샌드박스로 두고, 휴지통 도구도 아무것도 옮기지 않는 가짜로 둔다.
    # 셰임은 $env:USERPROFILE 을 먼저 보고, 없으면(POSIX pwsh) $HOME 을 본다. 두 경로를 각각 검증한다.
    It '<script>' -ForEach @(
        @{ script = 'Remove-Item $env:USERPROFILE -Recurse -Force'; posixHome = $false }
        @{ script = 'Remove-Item -LiteralPath $env:USERPROFILE'; posixHome = $false }
        @{ script = 'Remove-Item $HOME -Recurse -Force'; posixHome = $true }
    ) {
        if ($posixHome -and $IsWindows) {
            Set-ItResult -Skipped -Because 'On Windows, $HOME does not follow the HOME environment variable - verified via the USERPROFILE path'
            return
        }
        $sandbox = Join-Path $Base 'guarded-home'
        New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
        'x' | Set-Content -LiteralPath (Join-Path $sandbox 'keep')
        $fakeBin = Join-Path $Base 'fakebin'
        New-Item -ItemType Directory -Path $fakeBin -Force | Out-Null
        if (-not $IsWindows) {
            $fake = Join-Path $fakeBin 'trash-put'
            "#!/bin/sh`necho TRASHED `"`$*`"" | Set-Content -LiteralPath $fake
            chmod +x $fake
        }
        $old = @($env:USERPROFILE, $env:HOME, $env:PATH)
        $env:USERPROFILE = if ($posixHome) { $null } else { $sandbox }
        $env:HOME = $sandbox
        $env:PATH = $fakeBin + [System.IO.Path]::PathSeparator + $env:PATH
        try {
            $r = Invoke-Guarded $ModulePath $posixHome $sandbox $script
        } finally { $env:USERPROFILE = $old[0]; $env:HOME = $old[1]; $env:PATH = $old[2] }
        $r.Rc | Should -Not -Be 97 -Because "the shim and the sandbox home must be in effect: $($r.Out)"
        $r.Out | Should -Match 'refusing'
        (Test-Path -LiteralPath (Join-Path $sandbox 'keep')) | Should -BeTrue
    }

    # 가드 자체의 검증. 셰임이 잡히지 않으면 원본 Remove-Item 이 지우기 전에 97 로 끝나야 한다.
    It 'the guard stops before deleting when the shim is not loaded' {
        $sandbox = Join-Path $Base 'guard-check'
        New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
        'x' | Set-Content -LiteralPath (Join-Path $sandbox 'keep')
        $empty = Join-Path $Base 'NotTheShim.psm1'
        '# Remove-Item 을 가리지 않는 빈 모듈' | Set-Content -LiteralPath $empty
        $r = Invoke-Guarded $empty $false $sandbox "Remove-Item -LiteralPath '$sandbox' -Recurse -Force"
        $r.Rc | Should -Be 97
        (Test-Path -LiteralPath (Join-Path $sandbox 'keep')) | Should -BeTrue
    }
}

Describe 'deleted content can be recovered' {
    It 'shows up in the trash' {
        if (-not (Get-Command trash-list -ErrorAction SilentlyContinue)) {
            Set-ItResult -Skipped -Because 'trash-cli not installed (on Windows the send2trash path is used)'
            return
        }
        $dir = Join-Path $Base 'rec'
        New-Fixture $dir
        # 휴지통도 실제 홈의 것을 쓰지 않는다. `pip --user` 로 깔린 trash-cli 가 모듈을 찾도록
        # PYTHONUSERBASE 만 실제 위치로 둔다.
        $trashHome = Join-Path $Base 'trash-home'
        $userBase = (& python3 -c 'import site; print(site.getuserbase())' | Out-String).Trim()
        $old = @($env:HOME, $env:XDG_DATA_HOME, $env:PYTHONUSERBASE)
        $env:HOME = $trashHome
        $env:XDG_DATA_HOME = Join-Path $trashHome '.local/share'
        $env:PYTHONUSERBASE = $userBase
        try {
            & (Join-Path $PSHOME 'pwsh') -NoProfile -Command @"
Import-Module '$ModulePath' -Force -DisableNameChecking -Global
Set-Location -LiteralPath '$dir'
Remove-Item sub -Recurse -Force
"@ | Out-Null
            $listing = & trash-list | Out-String
        } finally { $env:HOME = $old[0]; $env:XDG_DATA_HOME = $old[1]; $env:PYTHONUSERBASE = $old[2] }
        (Test-Path -LiteralPath (Join-Path $dir 'sub')) | Should -BeFalse
        $listing | Should -BeLike ("*" + (Join-Path $dir 'sub') + "*")
        (Test-Path -LiteralPath (Join-Path $trashHome '.local/share/Trash/files/sub')) | Should -BeTrue
    }
}

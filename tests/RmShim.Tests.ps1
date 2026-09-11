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
`$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath '$dir'
$import
`$global:Error.Clear()
$script
if (`$global:Error.Count -gt 0) { Write-Output '<<ERR>>' }
Get-ChildItem -Recurse -Force -Name | Sort-Object | ForEach-Object { Write-Output "F:`$_" }
"@
        $out = & (Join-Path $PSHOME 'pwsh') -NoProfile -Command $body 2>&1
        return (($out | Where-Object { $_ -match '^(F:|<<ERR>>)' }) -join "`n")
    }
}

AfterAll {
    if (Test-Path $Base) {
        Microsoft.PowerShell.Management\Remove-Item -LiteralPath $Base -Recurse -Force `
            -ErrorAction SilentlyContinue
    }
}

Describe 'RmShim 이 원본 Remove-Item 과 같은 결과를 낸다' {
    It '<name>' -ForEach @(
        @{ name = '일반 파일';                  script = 'Remove-Item a.txt' }
        @{ name = 'rm 별칭';                    script = 'rm a.txt' }
        @{ name = 'del 별칭';                   script = 'del a.txt' }
        @{ name = 'ri 별칭';                    script = 'ri a.txt' }
        @{ name = '디렉터리 -Recurse';          script = 'Remove-Item sub -Recurse' }
        @{ name = '디렉터리 -Recurse -Force';   script = 'Remove-Item sub -Recurse -Force' }
        @{ name = '빈 디렉터리';                script = 'Remove-Item emptydir' }
        @{ name = '와일드카드';                 script = 'Remove-Item *.txt' }
        @{ name = '와일드카드 미일치';          script = 'Remove-Item *.nomatch' }
        @{ name = '없는 파일';                  script = 'Remove-Item nope.txt' }
        @{ name = '없는 파일 -EA Silent';       script = 'Remove-Item nope.txt -ErrorAction SilentlyContinue' }
        @{ name = '여러 대상';                  script = 'Remove-Item a.txt,b.txt,c.log' }
        @{ name = '일부만 존재';                script = 'Remove-Item a.txt,nope.txt,b.txt' }
        @{ name = '공백 포함 이름';             script = 'Remove-Item "name with spaces.txt"' }
        @{ name = '변수 확장';                  script = '$f = "a.txt"; Remove-Item $f' }
        @{ name = '변수+경로 결합';             script = '$d = "sub"; Remove-Item "$d/deep" -Recurse' }
        @{ name = '-LiteralPath';               script = 'Remove-Item -LiteralPath a.txt' }
        @{ name = '-Path 명시';                 script = 'Remove-Item -Path a.txt' }
        @{ name = '파이프라인';                 script = 'Get-ChildItem *.log -Recurse | Remove-Item' }
        @{ name = '파이프라인 디렉터리';        script = 'Get-ChildItem -Directory | Remove-Item -Recurse' }
        @{ name = '-WhatIf 는 지우지 않는다';   script = 'Remove-Item a.txt -WhatIf' }
        @{ name = '-Include 필터';              script = 'Remove-Item * -Include *.log -Recurse' }
        @{ name = '중첩 경로';                  script = 'Remove-Item sub/deep/x.log' }
        @{ name = '비-파일시스템 공급자';       script = '$env:CLAUDETMP="x"; Remove-Item Env:CLAUDETMP' }
    ) {
        $real = Get-Observation $script $false
        $shim = Get-Observation $script $true
        $shim | Should -Be $real
    }
}

Describe '루트/홈 전체 삭제는 거부한다' {
    It '<script>' -ForEach @(
        @{ script = 'Remove-Item $HOME -Recurse -Force' }
        @{ script = 'Remove-Item -LiteralPath $HOME' }
    ) {
        $out = & (Join-Path $PSHOME 'pwsh') -NoProfile -Command @"
Import-Module '$ModulePath' -Force -DisableNameChecking -Global
`$ErrorActionPreference='Continue'
$script
"@ 2>&1 | Out-String
        $out | Should -Match '거부'
        (Test-Path -LiteralPath $HOME) | Should -BeTrue
    }
}

Describe '삭제한 내용은 복구할 수 있다' {
    It '휴지통에서 조회된다' {
        if (-not (Get-Command trash-list -ErrorAction SilentlyContinue)) {
            Set-ItResult -Skipped -Because 'trash-cli 미설치 (Windows 에서는 send2trash 경로)'
            return
        }
        $dir = Join-Path $Base 'rec'
        New-Fixture $dir
        & (Join-Path $PSHOME 'pwsh') -NoProfile -Command @"
Import-Module '$ModulePath' -Force -DisableNameChecking -Global
Set-Location -LiteralPath '$dir'
Remove-Item sub -Recurse -Force
"@ | Out-Null
        (Test-Path -LiteralPath (Join-Path $dir 'sub')) | Should -BeFalse
        (& trash-list | Out-String) | Should -BeLike ("*" + (Join-Path $dir 'sub') + "*")
    }
}

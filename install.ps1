<#
.SYNOPSIS
    claude-code-setup 원격 설치 부트스트랩 (Windows PowerShell)
.DESCRIPTION
    GitHub 에서 레포 전체를 임시 디렉터리로 내려받아 scripts\setup.ps1 을 실행한다.
    (setup.ps1 은 res\ 와 scripts\lib\ 등 형제 파일이 있어야 동작하므로 이 부트스트랩이 필요하다.)
    전체 로직을 Invoke-Install 함수에 넣고 마지막 줄에서만 호출한다 — irm 다운로드가 중간에
    끊기면 잘린 스크립트가 iex 로 파싱될 때 함수 정의만 있고 호출부가 없어 아무것도 실행되지 않는다.
    플래그(-DryRun 등)는 최상위 param 블록에서 [switch] 로 받아 해시테이블 스플랫으로 setup.ps1
    에 넘긴다 — 배열 스플랫(@Rest)은 '-DryRun' 을 위치 인자로 취급해 스위치 바인딩이 안 된다.
.EXAMPLE
    irm https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1 | iex
.EXAMPLE
    # 플래그를 넘기려면 scriptblock 형태로:
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -DryRun
.NOTES
    환경변수로 대상 레포/브랜치를 바꿀 수 있다: $env:CLAUDE_SETUP_REPO, $env:CLAUDE_SETUP_REF
    비공개(private) 레포라면 $env:GITHUB_TOKEN (또는 $env:GH_TOKEN) 에 PAT 을 넣어두면
    아카이브 다운로드에 Authorization 헤더가 자동으로 붙는다. (부트스트랩 파일 자체를
    받을 때도 irm -Headers @{Authorization="Bearer $env:GITHUB_TOKEN"} 로 넘겨야 한다.)
#>

param(
    [switch]$Hooks,
    [switch]$AgentsMd,
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments = $true)] $Rest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

function Invoke-Install {
    param(
        [switch]$Hooks,
        [switch]$AgentsMd,
        [switch]$Uninstall,
        [switch]$DryRun,
        [switch]$Help,
        [Parameter(ValueFromRemainingArguments = $true)] $Rest
    )

    if ($Help -or ($Rest -and ($Rest -contains "-h" -or $Rest -contains "--help"))) {
        Write-Host @"
claude-code-setup 원격 설치 부트스트랩 (Windows)

사용법:
  irm .../install.ps1 | iex                                              # 전체 설치
  & ([scriptblock]::Create((irm .../install.ps1))) -Hooks                 # 전역 가드/권한만
  & ([scriptblock]::Create((irm .../install.ps1))) -AgentsMd             # 현재 폴더에 AGENTS.md
  & ([scriptblock]::Create((irm .../install.ps1))) -DryRun               # 미리보기

환경변수:
  `$env:CLAUDE_SETUP_REPO (기본 thsvkd/claude-code-setup), `$env:CLAUDE_SETUP_REF (기본 main)
  `$env:GITHUB_TOKEN / `$env:GH_TOKEN — 비공개 레포 다운로드용 PAT (있으면 자동 사용)
"@
        return
    }

    $repo = if ($env:CLAUDE_SETUP_REPO) { $env:CLAUDE_SETUP_REPO } else { "thsvkd/claude-code-setup" }
    $ref = if ($env:CLAUDE_SETUP_REF) { $env:CLAUDE_SETUP_REF } else { "main" }

    $tmp = Join-Path $env:TEMP ("claude-code-setup-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp "repo.zip"
        $url = "https://github.com/$repo/archive/$ref.zip"
        Write-Host "⬇️  claude-code-setup 다운로드 중 ($repo@$ref)..." -ForegroundColor Cyan
        # 비공개 레포면 PAT 로 인증한다. github.com 아카이브 URL 은 Authorization 헤더를 받아준다.
        $token = if ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } elseif ($env:GH_TOKEN) { $env:GH_TOKEN } else { $null }
        $iwr = @{ Uri = $url; OutFile = $zip; UseBasicParsing = $true }
        if ($token) { $iwr.Headers = @{ Authorization = "Bearer $token" } }
        Invoke-WebRequest @iwr
        Expand-Archive -Path $zip -DestinationPath $tmp -Force

        $dir = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
        if (-not $dir) { throw "다운로드한 아카이브 압축 해제에 실패했습니다." }
        $setup = Join-Path $dir.FullName "scripts\setup.ps1"
        if (-not (Test-Path $setup)) {
            throw "다운로드한 아카이브에서 scripts\setup.ps1 을 찾지 못했습니다."
        }

        # setup_agentsmd 는 현재 작업 디렉터리에 AGENTS.md 를 설치하므로 cwd 를 유지한 채 실행한다.
        # 스위치는 반드시 해시테이블 스플랫으로 넘긴다 (배열 스플랫 @Rest 는 스위치 바인딩 실패).
        $fwd = @{}
        foreach ($k in 'Hooks', 'AgentsMd', 'Uninstall', 'DryRun') {
            if ($PSBoundParameters[$k]) { $fwd[$k] = $true }
        }
        & $setup @fwd
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

Invoke-Install @PSBoundParameters

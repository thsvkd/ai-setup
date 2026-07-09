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
# PS 7.4+ 는 네이티브 명령의 0이 아닌 종료 코드를 종료 오류로 승격시킬 수 있다 ($true 가 기본인
# 빌드/프로필이 있음). 하위 setup.ps1/setup_hooks.ps1 은 실패를 $LASTEXITCODE 로 직접 판정하므로
# 이 부트스트랩에서도 명시적으로 끈다 (자식 프로세스로 실행되는 setup.ps1 에는 전파되지 않지만,
# 이 프로세스 안에서 직접 실행하는 Invoke-WebRequest 등에는 영향을 준다).
$PSNativeCommandUseErrorActionPreference = $false
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

# GITHUB_TOKEN → GH_TOKEN → `gh auth token` 순으로 찾는다 (install.sh 의 resolve_token 과 동일).
# gh 폴백이 있으면 사용자가 GITHUB_TOKEN 을 세션에 영구히 넣어둘 필요가 없다 — 그 환경변수가
# 남아 있으면 gh 가 "환경변수를 쓰는 중"이라며 gh auth login 을 거부해, 토큰이 만료된 순간
# 재로그인조차 못 하는 상태에 빠진다.
function Resolve-GitHubToken {
    if ($env:GITHUB_TOKEN) { return $env:GITHUB_TOKEN }
    if ($env:GH_TOKEN) { return $env:GH_TOKEN }
    try {
        $t = & gh auth token 2>$null
        if ($LASTEXITCODE -eq 0 -and $t) { return ($t | Select-Object -First 1).ToString().Trim() }
    } catch {}
    return $null
}

# GitHub API 는 인증 실패를 정직하게 401 로 알려준다 (아카이브/raw URL 과 달리).
# PS 5.1(WebException)과 7.x(HttpResponseException) 모두 .Exception.Response.StatusCode 를
# 갖고 있어 이 방식이면 양쪽에서 동작한다 (-SkipHttpErrorCheck 는 7.x 전용이라 쓸 수 없다).
function Get-GitHubApiStatus {
    param([Parameter(Mandatory)][string]$Url, [string]$Token)
    try {
        $iwr = @{ Uri = $Url; UseBasicParsing = $true; Method = "Get" }
        if ($Token) { $iwr.Headers = @{ Authorization = "Bearer $Token" } }
        $resp = Invoke-WebRequest @iwr
        return [int]$resp.StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return $null
    }
}

# 비공개 레포는 인증 실패를 401 이 아니라 404 로 위장한다 (레포의 존재 자체를 숨기려고).
# 그래서 "다운로드 실패"처럼 보이는 오류의 진짜 원인은 대개 죽은 토큰이다. API 를 한 번 찔러
# 실제 원인을 특정해준다 (install.sh 의 explain_download_failure 와 동일).
function Show-DownloadFailureDiagnosis {
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$Ref,
        [string]$Token,
        [Parameter(Mandatory)][string]$Tarball
    )
    Write-Host ""
    Write-Host "❌ 다운로드 실패: $Tarball" -ForegroundColor Red
    Write-Host ""

    if (-not $Token) {
        Write-Host "  토큰을 찾지 못했습니다. 비공개(private) 레포라면 인증이 필요합니다:" -ForegroundColor Yellow
        Write-Host "    gh auth login -h github.com"
        Write-Host "  로그인해 두면 이 스크립트가 gh 에서 토큰을 알아서 읽어옵니다."
        return
    }

    Write-Host "  토큰이 있는데도 실패했습니다. 비공개 레포는 인증 실패를 401 이 아니라 404 로" -ForegroundColor Yellow
    Write-Host "  돌려주므로, '파일이 없다'처럼 보여도 원인은 대개 토큰입니다."
    Write-Host ""
    $status = Get-GitHubApiStatus -Url "https://api.github.com/repos/$Repo" -Token $Token
    switch ($status) {
        401 {
            Write-Host "  진단: 토큰이 만료/폐기되었습니다 (GitHub API 가 401 Bad credentials)." -ForegroundColor Yellow
            Write-Host "    Remove-Item Env:GITHUB_TOKEN, Env:GH_TOKEN -ErrorAction SilentlyContinue"
            Write-Host "    gh auth login -h github.com"
            Write-Host "  ※ GITHUB_TOKEN 이 설정돼 있으면 gh auth login 이 거부됩니다. 먼저 지우세요."
        }
        403 {
            Write-Host "  진단: 토큰은 유효하지만 이 레포에 접근할 권한이 없습니다 (403)." -ForegroundColor Yellow
            Write-Host "    classic PAT 는 repo 스코프, fine-grained PAT 는 Contents:Read 가 필요합니다."
        }
        404 {
            Write-Host "  진단: 토큰은 인증되지만 '$Repo' 를 볼 수 없습니다 (404)." -ForegroundColor Yellow
            Write-Host "    CLAUDE_SETUP_REPO 값이 맞는지, 토큰에 이 레포 권한이 있는지 확인하세요."
        }
        200 {
            Write-Host "  진단: 레포 접근은 되는데 ref '$Ref' 를 찾지 못했습니다." -ForegroundColor Yellow
            Write-Host "    브랜치/태그 이름을 확인하세요. 완전한 형태로도 지정할 수 있습니다:"
            Write-Host "      `$env:CLAUDE_SETUP_REF = 'refs/heads/feature/my-branch'"
        }
        default {
            Write-Host "  진단: GitHub API 에 닿지 못했습니다. 네트워크/프록시를 확인하세요." -ForegroundColor Yellow
        }
    }
}

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
        $token = Resolve-GitHubToken
        $iwr = @{ Uri = $url; OutFile = $zip; UseBasicParsing = $true }
        if ($token) { $iwr.Headers = @{ Authorization = "Bearer $token" } }
        try {
            Invoke-WebRequest @iwr
        } catch {
            Show-DownloadFailureDiagnosis -Repo $repo -Ref $ref -Token $token -Tarball $url
            exit 1
        }
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

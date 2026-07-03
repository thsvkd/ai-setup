<#
.SYNOPSIS
    claude-code-setup 원격 설치 부트스트랩 (Windows PowerShell)
.DESCRIPTION
    GitHub 에서 레포 전체를 임시 디렉터리로 내려받아 scripts\setup.ps1 을 실행한다.
    (setup.ps1 은 res\ 와 scripts\lib\ 등 형제 파일이 있어야 동작하므로 이 부트스트랩이 필요하다.)
.EXAMPLE
    irm https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1 | iex
.EXAMPLE
    # 플래그를 넘기려면 scriptblock 형태로:
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/claude-code-setup/main/install.ps1))) -DryRun
.NOTES
    환경변수로 대상 레포/브랜치를 바꿀 수 있다: $env:CLAUDE_SETUP_REPO, $env:CLAUDE_SETUP_REF
#>

$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$repo = if ($env:CLAUDE_SETUP_REPO) { $env:CLAUDE_SETUP_REPO } else { "thsvkd/claude-code-setup" }
$ref  = if ($env:CLAUDE_SETUP_REF)  { $env:CLAUDE_SETUP_REF }  else { "main" }

$tmp = Join-Path $env:TEMP ("claude-code-setup-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
    $zip = Join-Path $tmp "repo.zip"
    $url = "https://github.com/$repo/archive/refs/heads/$ref.zip"
    Write-Host "⬇️  claude-code-setup 다운로드 중 ($repo@$ref)..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp -Force

    $dir = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
    $setup = Join-Path $dir.FullName "scripts\setup.ps1"
    if (-not (Test-Path $setup)) {
        throw "다운로드한 아카이브에서 scripts\setup.ps1 을 찾지 못했습니다."
    }

    # setup_agentsmd 는 현재 작업 디렉터리에 AGENTS.md 를 설치하므로 cwd 를 유지한 채 실행한다.
    & $setup @args
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

<#
.SYNOPSIS
    ai-setup 원격 설치 부트스트랩 (Windows PowerShell)
.DESCRIPTION
    GitHub 에서 레포 전체를 임시 디렉터리로 내려받아 scripts\setup.ps1 을 실행한다.
    (setup.ps1 은 res\ 와 scripts\lib\ 등 형제 파일이 있어야 동작하므로 이 부트스트랩이 필요하다.)
    전체 로직을 Invoke-Install 함수에 넣고 마지막 줄에서만 호출한다 — irm 다운로드가 중간에
    끊기면 잘린 스크립트가 iex 로 파싱될 때 함수 정의만 있고 호출부가 없어 아무것도 실행되지 않는다.
    플래그(-DryRun 등)는 최상위 param 블록에서 [switch] 로 받아 해시테이블 스플랫으로 setup.ps1
    에 넘긴다 — 배열 스플랫(@Rest)은 '-DryRun' 을 위치 인자로 취급해 스위치 바인딩이 안 된다.
    스위치를 새로 추가할 때는 param 블록, 긴 표기(--dry-run) 해석 테이블, 아래 $fwd 목록
    **셋 다** 에 넣어야 한다. 한 곳만 빠뜨려도 조용히 무시된다
    (install.sh 는 "$@" 로 전부 넘기므로 이 비대칭이 POSIX 쪽에선 안 보인다).
.EXAMPLE
    irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1 | iex
.EXAMPLE
    # 플래그를 넘기려면 scriptblock 형태로:
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/thsvkd/ai-setup/main/install.ps1))) -DryRun
.NOTES
    환경변수로 대상 레포/브랜치를 바꿀 수 있다: $env:CLAUDE_SETUP_REPO, $env:CLAUDE_SETUP_REF
#>

# PositionalBinding 을 끄지 않으면 scriptblock 형태로 직접 실행할 때 `--help` 나
# `--dry-run` 같은 토큰이 파라미터가 아닌 '위치 인자' 로 들어와 첫 번째 비-스위치
# 파라미터인 -Newline 에 통째로 바인딩된다. 그러면 아래 $Rest 검사는 아무것도 보지
# 못한 채 setup.ps1 에 Newline='--help' 가 넘어가 엉뚱한 오류가 났다.
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Hooks,
    [switch]$AgentsMd,
    [switch]$Keybinds,
    [switch]$Skills,
    [string]$Tools,
    [switch]$Omc,
    [switch]$OutputStyle,
    [switch]$Mods,
    [string]$Newline,
    [string[]]$Harness,
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$NoOnboard,
    [switch]$Doctor,
    [Alias("h")]
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments = $true)] [object[]]$Rest = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# PS 7.4+ 는 네이티브 명령의 0이 아닌 종료 코드를 종료 오류로 승격시킬 수 있다 ($true 가 기본인
# 빌드/프로필이 있음). 하위 setup.ps1/setup_hooks.ps1 은 실패를 $LASTEXITCODE 로 직접 판정하므로
# 이 부트스트랩에서도 명시적으로 끈다 (자식 프로세스로 실행되는 setup.ps1 에는 전파되지 않지만,
# 이 프로세스 안에서 직접 실행하는 Invoke-WebRequest 등에는 영향을 준다).
$PSNativeCommandUseErrorActionPreference = $false
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

function Show-DownloadFailureDiagnosis {
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$Ref,
        [Parameter(Mandatory)][string]$Tarball
    )
    Write-Host ""
    Write-Host "❌ Download failed: $Tarball" -ForegroundColor Red
    Write-Host "  Check CLAUDE_SETUP_REPO ('$Repo'), CLAUDE_SETUP_REF ('$Ref') and your network/proxy." -ForegroundColor Yellow
    Write-Host "  A branch name can also be given in the fully qualified form:"
    Write-Host "    `$env:CLAUDE_SETUP_REF = 'refs/heads/feature/my-branch'"
}

function Invoke-Install {
    param(
        [switch]$Hooks,
        [switch]$AgentsMd,
        [switch]$Keybinds,
        [switch]$Skills,
        [string]$Tools,
        [switch]$Omc,
        [switch]$OutputStyle,
        [switch]$Mods,
        [string]$Newline,
        [string[]]$Harness,
        [switch]$Uninstall,
        [switch]$DryRun,
        [switch]$NoOnboard,
        [switch]$Doctor,
        [Alias("h")]
        [switch]$Help,
        [Parameter(ValueFromRemainingArguments = $true)] [object[]]$Rest = @()
    )

    # 남은 토큰을 install.sh 와 같은 긴 표기로 해석한다. PowerShell 은 이름에 하이픈이
    # 들어간 플래그(--dry-run)를 파라미터로 인식하지 못하므로 여기서 직접 읽는다.
    # 인자가 없으면 $Rest 는 빈 배열이다 — 타입 없이 받으면 @($null) 이 원소 하나짜리가 되어
    # 빈 문자열이 "알 수 없는 옵션" 으로 걸리고, 인자 없는 `irm | iex` 가 매번 죽었다.
    $restTokens = $Rest
    $newlineGiven = $PSBoundParameters.ContainsKey("Newline")
    $harnessGiven = $PSBoundParameters.ContainsKey("Harness")
    $toolsGiven = $PSBoundParameters.ContainsKey("Tools")
    $unknownArgs = @()
    $stageRun = $false
    $stagesValue = ""
    $jarvisRole = ""
    $herdrFlag = $false
    $ssCaps = $false
    $orcaDesktop = $false
    for ($i = 0; $i -lt $restTokens.Count; $i++) {
        switch -Regex ([string]$restTokens[$i]) {
            '^(--help|-help|/[?h])$' { $Help = $true }
            '^--hooks$'              { $Hooks = $true }
            '^--agents-?md$'         { $AgentsMd = $true }
            '^--skills$'             { $Skills = $true }
            '^--keybinds$'           { $Keybinds = $true }
            '^--omc$'                { $Omc = $true }
            '^--output-style$'       { $OutputStyle = $true }
            '^--mods$'               { $Mods = $true }
            '^--tools(=.*)?$'        { $toolsGiven = $true }
            '^--uninstall$'          { $Uninstall = $true }
            '^--dry-run$'            { $DryRun = $true }
            '^--no-onboard$'         { $NoOnboard = $true }
            '^--doctor$'             { $Doctor = $true }
            '^--newline=(.*)$'       { $Newline = $Matches[1]; $newlineGiven = $true }
            '^--harness=(.*)$'       { $Harness = @($Matches[1]); $harnessGiven = $true }
            '^--harness$' {
                $harnessGiven = $true
                # PowerShell 명령줄의 `a,b` 는 배열로 온다. 쉼표 목록으로 되돌린다.
                $Harness = if ($i + 1 -lt $restTokens.Count) { @(@($restTokens[++$i]) -join ",") } else { @("") }
            }
            '^--newline$' {
                $newlineGiven = $true
                $Newline = if ($i + 1 -lt $restTokens.Count) { [string]$restTokens[++$i] } else { "" }
            }
            '^--stages=(.*)$' { $stagesValue = $Matches[1]; $stageRun = $true }
            '^--stages$' {
                $stageRun = $true
                $stagesValue = if ($i + 1 -lt $restTokens.Count) { @($restTokens[++$i]) -join "," } else { "" }
            }
            '^--jarvis-role=(.*)$' { $jarvisRole = $Matches[1] }
            '^--jarvis-role$' {
                $jarvisRole = if ($i + 1 -lt $restTokens.Count) { [string]$restTokens[++$i] } else { "" }
            }
            '^--herdr$' { $herdrFlag = $true }
            '^--ss-caps$' { $ssCaps = $true }
            '^--orca-desktop$' { $orcaDesktop = $true }
            default { $unknownArgs += $restTokens[$i] }
        }
    }

    # Orca 관리는 jarvis 로 옮겨 갔다. 레포를 받기 전에 안내만 내고 끝낸다.
    if ($toolsGiven -or $orcaDesktop) {
        Write-Host "Orca is now managed by jarvis; ai-setup no longer installs, updates or removes it. From a jarvis checkout run: py -3 -m jarvis module orca plan --json (uninstall: module orca uninstall --json --dry-run)." -ForegroundColor Red
        if ($PSCommandPath) { exit 1 }
        $global:LASTEXITCODE = 1
        return
    }
    if ($stageRun -and -not $stagesValue) { throw "--stages requires all or a comma-separated list." }
    if ($jarvisRole -and $jarvisRole -notin @("gateway", "core")) { throw "--jarvis-role must be gateway or core." }
    if (($jarvisRole -or $herdrFlag -or $ssCaps) -and -not $stageRun) { throw "--jarvis-role, --herdr, and --ss-caps require --stages." }

    if ($Help) {
        Write-Host @"
ai-setup remote install bootstrap (Windows)

Usage:
  irm .../install.ps1 | iex                                              # interactive onboarding → install what you pick
  & ([scriptblock]::Create((irm .../install.ps1))) -Hooks                 # global guards/permissions only
  & ([scriptblock]::Create((irm .../install.ps1))) -AgentsMd             # AGENTS.md in the current folder
  & ([scriptblock]::Create((irm .../install.ps1))) -AgentsMd -Harness codex  # choose the harness
  & ([scriptblock]::Create((irm .../install.ps1))) -Skills               # bundled skills only
  & ([scriptblock]::Create((irm .../install.ps1))) -DryRun               # preview
  & ([scriptblock]::Create((irm .../install.ps1))) -Doctor               # read-only health report
  & ([scriptblock]::Create((irm .../install.ps1))) -NoOnboard            # old default install without onboarding
  & ([scriptblock]::Create((irm .../install.ps1))) --stages all --dry-run

The same long options as install.sh (--hooks / --agentsmd / --harness L / --skills / --keybinds / --omc / --output-style / --mods / --newline VAL /
--stages L / --jarvis-role gateway|core / --herdr / --ss-caps /
--uninstall / --dry-run / --no-onboard / --doctor / --help) are accepted too.

Run without flags on a TTY to walk the stages. Skip, or no console, installs nothing.
Without a console (CI, etc.) nothing is installed. -NoOnboard keeps the old default install.

Environment variables:
  `$env:CLAUDE_SETUP_REPO (default thsvkd/ai-setup), `$env:CLAUDE_SETUP_REF (default main)
"@
        return
    }

    # 남은 인자는 setup 으로 넘어가지 않는다. 조용히 버리면 오타(--keybind)가 '전체 설치' 로
    # 둔갑한다 — POSIX install.sh 는 알 수 없는 옵션에서 exit 1 이므로 여기서도 거절한다.
    # 다운로드 전에 판정한다: 오타 하나 때문에 레포를 통째로 받을 이유가 없다.
    if ($unknownArgs.Count -gt 0) {
        throw "Unknown option: $($unknownArgs -join ' ')"
    }

    $repo = if ($env:CLAUDE_SETUP_REPO) { $env:CLAUDE_SETUP_REPO } else { "thsvkd/ai-setup" }
    $ref = if ($env:CLAUDE_SETUP_REF) { $env:CLAUDE_SETUP_REF } else { "main" }

    $tmp = Join-Path $env:TEMP ("ai-setup-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $code = 0
    try {
        $zip = Join-Path $tmp "repo.zip"
        $url = "https://github.com/$repo/archive/$ref.zip"
        Write-Host "⬇️  ai-setup downloading ($repo@$ref)..." -ForegroundColor Cyan
        $iwr = @{ Uri = $url; OutFile = $zip; UseBasicParsing = $true }
        try {
            Invoke-WebRequest @iwr
        } catch {
            Show-DownloadFailureDiagnosis -Repo $repo -Ref $ref -Tarball $url
            exit 1
        }
        Expand-Archive -Path $zip -DestinationPath $tmp -Force

        $dir = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
        if (-not $dir) { throw "Failed to extract the downloaded archive." }
        $setup = Join-Path $dir.FullName "scripts\setup.ps1"
        if (-not (Test-Path $setup)) {
            throw "scripts\setup.ps1 was not found in the downloaded archive."
        }

        # setup_agentsmd 는 현재 작업 디렉터리에 AGENTS.md 를 설치하므로 cwd 를 유지한 채 실행한다.
        # 스위치는 반드시 해시테이블 스플랫으로 넘긴다 (배열 스플랫 @Rest 는 스위치 바인딩 실패).
        # $PSBoundParameters 가 아니라 변수에서 읽는다 — 위 긴 표기(--dry-run) 해석 결과는
        # $PSBoundParameters 에 남지 않는다.
        $fwd = @{}
        foreach ($k in 'Hooks', 'AgentsMd', 'Uninstall', 'DryRun', 'NoOnboard', 'Keybinds', 'Skills', 'Omc', 'OutputStyle', 'Mods', 'Doctor') {
            if (Get-Variable -Name $k -ValueOnly) { $fwd[$k] = $true }
        }
        if ($newlineGiven) {
            $fwd['Newline'] = $Newline
        }
        if ($harnessGiven) {
            $fwd['Harness'] = $Harness
        }
        $extra = @()
        if ($stageRun) { $extra += @('--stages', $stagesValue) }
        if ($jarvisRole) { $extra += @('--jarvis-role', $jarvisRole) }
        if ($herdrFlag) { $extra += '--herdr' }
        if ($ssCaps) { $extra += '--ss-caps' }
        # irm | iex 는 메모리에서 돌지만 setup.ps1 은 내려받은 파일이라, Windows 기본 실행 정책
        # (Restricted)에서 막힌다. 이 프로세스에만 Bypass 를 걸고 끝나면 원래 값으로 돌린다.
        # Linux·macOS 의 pwsh 는 실행 정책이 없고 Set-ExecutionPolicy 가 예외를 낸다.
        $onWindows = ($PSVersionTable.PSEdition -eq 'Desktop') -or $IsWindows
        $previousPolicy = $null
        if ($onWindows) {
            $previousPolicy = Get-ExecutionPolicy -Scope Process
            try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force } catch {}
        }
        try {
            & $setup @fwd @extra
            $code = $LASTEXITCODE
        } finally {
            if ($onWindows) {
                try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy $previousPolicy -Force } catch {}
            }
        }
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
    # 파일로 실행됐으면 setup 의 종료 코드를 그대로 넘긴다 — 온보딩이 깨져 중단돼도 exit 0 이면
    # 자동화는 성공으로 본다. irm | iex·scriptblock 으로 실행되면 exit 가 사용자의 셸을 닫으므로
    # $LASTEXITCODE 로만 남긴다.
    if ($PSCommandPath) { exit $code }
    $global:LASTEXITCODE = $code
}

Invoke-Install @PSBoundParameters

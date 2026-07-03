<#
.SYNOPSIS
    Claude Code 사용자 레벨(user-level) 훅/권한 설정 (Windows) — v4
.DESCRIPTION
    대상은 "사용자 홈"의 %USERPROFILE%\.claude\settings.json 입니다. Claude Code는
    v2.1.142부터 프로젝트 settings.json/settings.local.json 안의
    permissions.defaultMode: "auto" 를 무시합니다 (신뢰할 수 없는 리포가 권한을 몰래
    완화시키지 못하게 하는 보호장치). auto 모드를 기본값으로 켜려면 반드시 유저 레벨
    settings.json 이어야 하므로, 이 스크립트가 관리하는 모든 것(defaultMode, allow 목록,
    PreToolUse 훅, 훅용 파이썬 파일)을 유저 레벨로 옮겼습니다.

    ⚠️ 범위: 이 훅들은 "이 프로젝트"가 아니라 이 사용자가 여는 모든 프로젝트에 적용됩니다.

    병합은 철저히 외과적(surgical)입니다 — permissions.allow/deny/defaultMode 와
    hooks.PreToolUse 만 건드리고, 기존 settings.json 의 다른 모든 내용(model, env,
    statusLine, 다른 훅 등)은 100% 그대로 보존합니다. res/hooks/merge_and_diff.py 가
    이를 담당하며, -DryRun 으로 실제 적용 전에 정확히 무엇이 바뀔지 미리 볼 수 있습니다.

    이 스크립트는 scripts/setup.ps1 디스패처가 -Hooks 로 호출하는 워커입니다. 실제
    로직은 scripts/lib/SetupCommon.ps1 (공용 함수)과 res/hooks/*.py, res/settings.json
    (설치될 내용) 에 있습니다.
.USAGE
    powershell -ExecutionPolicy Bypass -File setup_hooks.ps1              # 실제 적용
    powershell -ExecutionPolicy Bypass -File setup_hooks.ps1 -DryRun      # 미리보기만
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ResDir = Join-Path $RepoRoot "res"
. (Join-Path $PSScriptRoot "lib\SetupCommon.ps1")

Write-Host "🔧 Claude Code 사용자 레벨 훅/권한 설정 시작..." -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "  🧪 DRY RUN 모드 — 실제 파일은 전혀 변경/설치되지 않습니다." -ForegroundColor Magenta
}

$RealUserHome = $env:USERPROFILE
$RealClaudeDir = Join-Path $RealUserHome ".claude"
$RealHooksDir = Join-Path $RealClaudeDir "hooks"
$RealSettingsPath = Join-Path $RealClaudeDir "settings.json"

$installHome = Resolve-InstallHome -DryRun:$DryRun -RealHome $RealUserHome -SeedFiles @("settings.json")
$WorkHome = $installHome.WorkHome
$hooksDir = Join-Path $WorkHome ".claude\hooks"
$settingsPath = Join-Path $WorkHome ".claude\settings.json"

try {

# --- 1. Python 실행 파일 탐지 ---
$py = Resolve-PythonCommand
if (-not $py) {
    throw "Python을 찾을 수 없습니다. Python 3을 설치한 뒤 다시 실행하세요."
}
$pyInvoke = (@($py.Exe) + $py.Args) -join " "
Write-Host "  🐍 Python 실행 명령: $pyInvoke" -ForegroundColor DarkGray

# --- 2. send2trash 설치 확인 (Windows 전용 의존성) ---
Write-Host ""
Write-Host "[1/4] send2trash 설치 확인..." -ForegroundColor Yellow

& $py.Exe @($py.Args) -c "import send2trash" *> $null
$hasSend2Trash = ($LASTEXITCODE -eq 0)

if ($hasSend2Trash) {
    Write-Host "  ✅ send2trash 이미 설치됨" -ForegroundColor Green
} elseif ($DryRun) {
    Write-Host "  ℹ️ send2trash 미설치 상태입니다. (dry-run 이라 설치는 시도하지 않음)" -ForegroundColor DarkGray
} else {
    Write-Host "  📦 send2trash 설치 중..."
    & $py.Exe @($py.Args) -m pip install --quiet --disable-pip-version-check send2trash
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ send2trash 설치 완료" -ForegroundColor Green
        $hasSend2Trash = $true
    } else {
        Write-Host "  ⚠️ send2trash 설치 실패 — 수동 설치 필요: $pyInvoke -m pip install send2trash" -ForegroundColor Red
        Write-Host "     (설치 전까지 rm/del 은 휴지통으로 치환되지 못하고 안전을 위해 '차단'됩니다 — fail closed)" -ForegroundColor Yellow
        $hasSend2Trash = $false
    }
}

# --- 3. 훅 파일 설치 (res/hooks/*.py 를 WorkHome 기준 hooksDir로 복사) ---
Write-Host ""
$hookMsg = "[2/4] PreToolUse Hook 설치"
if ($DryRun) { $hookMsg += " (임시 사본에만 — 실제 위치엔 안 씀)" }
Write-Host "$hookMsg..." -ForegroundColor Yellow

Install-HookFiles -HooksDir $hooksDir -Files @(
    @{ Source = (Join-Path $ResDir "hooks\danger_guard.windows.py"); DestName = "danger_guard.py" },
    @{ Source = (Join-Path $ResDir "hooks\secrets_guard.py");        DestName = "secrets_guard.py" },
    @{ Source = (Join-Path $ResDir "hooks\send_to_trash.py");        DestName = "send_to_trash.py" }
) | Out-Null
Write-Host "  ✅ Hook 파일 준비 완료: danger_guard.py, secrets_guard.py, send_to_trash.py" -ForegroundColor Green

# --- 4. settings.json 병합 계획 수립 및 실행 ---
Write-Host ""
Write-Host "[3/4] settings.json 병합 계획 수립 및 실행..." -ForegroundColor Yellow

$mergeExit = Invoke-SettingsMerge `
    -FragmentPath (Join-Path $ResDir "settings.json") `
    -SettingsPath $settingsPath `
    -DryRun:$DryRun `
    -PyInvoke $pyInvoke `
    -RealHooksDir $RealHooksDir `
    -MergeScriptPath (Join-Path $ResDir "hooks\merge_and_diff.py") `
    -PyExe $py.Exe -PyArgs $py.Args
if ($mergeExit -ne 0) {
    throw "병합 검증 실패 — 예상치 못한 최상위 키 변경이 감지되었습니다. 수동 확인이 필요합니다."
}

# --- 5. 셀프테스트 ---
Write-Host ""
Write-Host "[4/4] 셀프테스트 실행..." -ForegroundColor Yellow

Invoke-HookSelfTest -HookPath (Join-Path $hooksDir "danger_guard.py") -PyExe $py.Exe -PyArgs $py.Args -Cases @(
    @{ Label = "rm -rf temp/  → 휴지통 치환 기대"; Json = '{"tool_name":"Bash","tool_input":{"command":"rm -rf temp/"}}' },
    @{ Label = "git push --force → deny 기대";      Json = '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' },
    @{ Label = "PowerShell + git push --force → deny 기대"; Json = '{"tool_name":"PowerShell","tool_input":{"command":"git push --force origin main"}}' },
    @{ Label = "Remove-Item -Recurse -Force C:\ → deny 기대"; Json = '{"tool_name":"PowerShell","tool_input":{"command":"Remove-Item -Recurse -Force C:\\"}}' },
    @{ Label = "ls -la → 통과(무판단) 기대";          Json = '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' }
)

# --- 6. 리포트 ---
$depWarning = $null
if (-not $hasSend2Trash) {
    $depWarning = "send2trash 가 설치되지 않아, 설치 전까지 rm/del 계열 명령은 '차단'됩니다 (안전을 위한 기본값)."
}
Write-SetupReport -DryRun:$DryRun -InstalledFiles @(
    (Join-Path $RealHooksDir "danger_guard.py"),
    (Join-Path $RealHooksDir "secrets_guard.py"),
    (Join-Path $RealHooksDir "send_to_trash.py")
) -SettingsPath $RealSettingsPath -GuardLogPath (Join-Path $RealHooksDir "guard.log") -DependencyWarning $depWarning

$script:ExitCode = 0

} catch {
    Write-Host "❌ $($_.Exception.Message)" -ForegroundColor Red
    $script:ExitCode = 1
} finally {
    if ($installHome.CleanupDir -and (Test-Path $installHome.CleanupDir)) {
        Remove-Item -Recurse -Force $installHome.CleanupDir -ErrorAction SilentlyContinue
    }
}

exit $script:ExitCode

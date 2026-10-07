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
    powershell -ExecutionPolicy Bypass -File setup_hooks.ps1 -DefaultMode bypassPermissions
                                                                          # 권한 모드 지정
#>

param(
    [switch]$DryRun,
    [switch]$Uninstall,
    # 온보딩이 고른 permissions.defaultMode. 안 주면 res/settings.json 의 값(auto)을 쓴다.
    [ValidateSet("", "auto", "bypassPermissions", "default", "acceptEdits", "plan")]
    [string]$DefaultMode = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# PS 7.4+ 는 네이티브 명령의 0이 아닌 종료 코드를 종료 오류로 승격시킬 수 있다 ($true 가 기본인
# 빌드/프로필이 있음). send2trash 미설치 탐지 등은 $LASTEXITCODE 로 직접 판정하므로 명시적으로 끈다.
$PSNativeCommandUseErrorActionPreference = $false
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ResDir = Join-Path $RepoRoot "res"
. (Join-Path $PSScriptRoot "lib\SetupCommon.ps1")

# $env:USERPROFILE 는 Windows 에만 있다. POSIX 의 pwsh 에서 null 이 되면 아래 Join-Path 가
# 통째로 깨져 스크립트가 시작도 못 한다 — setup_keybinds.ps1 과 같은 폴백을 쓴다.
$RealUserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$RealClaudeDir = Join-Path $RealUserHome ".claude"
$RealHooksDir = Join-Path $RealClaudeDir "hooks"
$RealSettingsPath = Join-Path $RealClaudeDir "settings.json"

# --- uninstall 은 설치 로직을 타지 않고 실제 ~/.claude 를 대상으로 즉시 처리한다 ---
if ($Uninstall) {
    Write-Host "🧹 Claude Code 가드 훅 제거..." -ForegroundColor Cyan
    if ($DryRun) { Write-Host "  🧪 DRY RUN 모드 — 실제 파일은 전혀 제거되지 않습니다." -ForegroundColor Magenta }
    $py = Resolve-PythonCommand
    if (-not $py) { Write-Host "❌ Python을 찾을 수 없습니다." -ForegroundColor Red; Write-PythonInstallHint; exit 1 }
    Write-Host ""
    Uninstall-Hooks -ClaudeDir $RealClaudeDir -HooksDir $RealHooksDir -SettingsPath $RealSettingsPath `
        -DryRun:$DryRun -MergeScriptPath (Join-Path $ResDir "hooks\merge_and_diff.py") -PyExe $py.Exe -PyArgs $py.Args
    Write-Host ""
    if ($DryRun) {
        Write-Host "🧪 DRY RUN 완료 — 실제로 제거하려면 -DryRun 없이 다시 실행하세요." -ForegroundColor Magenta
    } else {
        Write-Host "✅ 제거 완료 — 설치가 건드린 부분만 정밀하게 되돌렸습니다 (사용자가 원래 갖고 있던 설정은 보존)." -ForegroundColor Green
    }
    exit 0
}

Write-Host "🔧 Claude Code 사용자 레벨 훅/권한 설정 시작..." -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "  🧪 DRY RUN 모드 — 실제 파일은 전혀 변경/설치되지 않습니다." -ForegroundColor Magenta
}

$installHome = Resolve-InstallHome -DryRun:$DryRun -RealHome $RealUserHome -SeedFiles @("settings.json")
$WorkHome = $installHome.WorkHome
$hooksDir = Join-Path $WorkHome ".claude\hooks"
$settingsPath = Join-Path $WorkHome ".claude\settings.json"
$pythonMissing = $false

try {

# --- 1. Python 실행 파일 탐지 ---
$py = Resolve-PythonCommand
if (-not $py) {
    $pythonMissing = $true
    throw "Python을 찾을 수 없습니다."
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
        Write-Host "     (설치 전까지 Git Bash 의 rm 은 경고만 남기고 '실제로' 삭제됩니다 — 되돌릴 수 없습니다)" -ForegroundColor Yellow
        $hasSend2Trash = $false
    }
}

# --- 3. 훅 파일 설치 (res/hooks/*.py 를 WorkHome 기준 hooksDir로 복사) ---
Write-Host ""
$hookMsg = "[2/4] PreToolUse Hook 설치"
if ($DryRun) { $hookMsg += " (임시 사본에만 — 실제 위치엔 안 씀)" }
Write-Host "$hookMsg..." -ForegroundColor Yellow

Install-HookFiles -HooksDir $hooksDir -Files @(
    @{ Source = (Join-Path $ResDir "hooks/danger_guard.py");   DestName = "danger_guard.py" },
    @{ Source = (Join-Path $ResDir "hooks/send_to_trash.py");  DestName = "send_to_trash.py" },
    @{ Source = (Join-Path $ResDir "hooks/shims/rm");          DestName = "shims/rm" },
    @{ Source = (Join-Path $ResDir "hooks/shims/RmShim.psm1"); DestName = "shims/RmShim.psm1" },
    @{ Source = (Join-Path $ResDir "hooks/graft_sync_hidden.cjs"); DestName = "graft_sync_hidden.cjs" }
) | Out-Null
# 구버전이 심어둔 훅 파일을 걷어낸다. settings.json 쪽 등록 해제는 merge 가 한다.
$retired = Join-Path $hooksDir "secrets_guard.py"
if (-not $DryRun -and (Test-Path $retired)) {
    Microsoft.PowerShell.Management\Remove-Item -Force $retired
    Write-Host "  🗑️  구버전 훅 제거: secrets_guard.py (더 이상 배포하지 않습니다)" -ForegroundColor DarkGray
}
Write-Host "  ✅ Hook 파일 준비 완료: danger_guard.py, send_to_trash.py, shims/rm, shims/RmShim.psm1, graft_sync_hidden.cjs" -ForegroundColor Green

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
    -PyExe $py.Exe -PyArgs $py.Args `
    -ManifestPath (Join-Path $WorkHome ".claude\$MANIFEST_NAME") `
    -HookFilesCsv "danger_guard.py,send_to_trash.py,shims/rm,shims/RmShim.psm1,graft_sync_hidden.cjs" `
    -DefaultMode $DefaultMode
if ($mergeExit -ne 0) {
    throw "병합 검증 실패 — 예상치 못한 최상위 키 변경이 감지되었습니다. 수동 확인이 필요합니다."
}

# --- 5. 셀프테스트 ---
Write-Host ""
Write-Host "[4/4] 셀프테스트 실행..." -ForegroundColor Yellow

# git 관련 판정(스냅샷 백업, 기본 브랜치 force push 확인)은 여기서 돌리지 않는다. 둘 다 cwd 가
# git 저장소인지에 따라 결과가 달라지는데, 설치는 저장소 밖에서도 실행된다. 스냅샷은 cwd
# 저장소에 실제로 백업 ref 를 만들어 dry-run 도 깨뜨린다. 두 경로 모두
# tests/test_git_snapshot.py 가 임시 저장소를 만들어 검증한다.
$selfTestFailures = Invoke-HookSelfTest -HookPath (Join-Path $hooksDir "danger_guard.py") -PyExe $py.Exe -PyArgs $py.Args -Cases @(
    @{ Label = "rm -rf temp/ → 통과(무판단) 기대 — 셰임 PATH 는 SessionStart 가 설정"; Json = '{"tool_name":"Bash","tool_input":{"command":"rm -rf temp/"}}' },
    # PowerShell 툴로도 반드시 한 번 돌린다. Bash 케이스는 선행 줄을 내지 않으므로, 이게 없으면
    # Windows 설치본에서 실제로 쓰일 Import-Module 선행 줄이 한 번도 생성되지 않은 채 통과한다.
    @{ Label = "PowerShell + Remove-Item → RmShim Import 선행 기대"; Json = '{"tool_name":"PowerShell","tool_input":{"command":"Remove-Item -Recurse -Force .\\build"}}' },
    @{ Label = "rm -rf ~ → deny 기대 (홈 디렉터리 전체)"; Json = '{"tool_name":"Bash","tool_input":{"command":"rm -rf ~"}}' },
    @{ Label = "Remove-Item -Recurse -Force C:\ → deny 기대"; Json = '{"tool_name":"PowerShell","tool_input":{"command":"Remove-Item -Recurse -Force C:\\"}}' },
    @{ Label = "ls -la → 통과(무판단) 기대";          Json = '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' }
)

# 셀프테스트가 판정을 못 내면 가드가 설치는 됐어도 실제로는 동작하지 않는 상태다. 훅이
# 유일한 방어선이므로(permissions 에 git deny 규칙을 두지 않는다) 조용히 넘기지 않는다.
if ($selfTestFailures -gt 0) {
    throw "셀프테스트 $selfTestFailures 건 실패 — 가드 훅이 정상 동작하지 않습니다. 위 ❌ 항목을 확인하세요."
}

# --- 6. 리포트 ---
$depWarning = $null
if (-not $hasSend2Trash) {
    $depWarning = "send2trash 가 설치되지 않아, Git Bash 의 rm 은 경고만 남기고 실제로 삭제됩니다 (복구 불가)."
}
Write-SetupReport -DryRun:$DryRun -InstalledFiles @(
    (Join-Path $RealHooksDir "danger_guard.py"),
    (Join-Path $RealHooksDir "send_to_trash.py"),
    (Join-Path $RealHooksDir "shims/rm"),
    (Join-Path $RealHooksDir "shims/RmShim.psm1"),
    (Join-Path $RealHooksDir "graft_sync_hidden.cjs")
) -SettingsPath $RealSettingsPath -GuardLogPath (Join-Path $RealHooksDir "guard.log") -DependencyWarning $depWarning -DefaultMode $DefaultMode
# 설치 영수증(매니페스트)은 위 Invoke-SettingsMerge 안에서 merge 가 기록한다.

$script:ExitCode = 0

} catch {
    Write-Host "❌ $($_.Exception.Message)" -ForegroundColor Red
    if ($pythonMissing) { Write-PythonInstallHint }
    $script:ExitCode = 1
} finally {
    if ($installHome.CleanupDir -and (Test-Path $installHome.CleanupDir)) {
        Remove-Item -Recurse -Force $installHome.CleanupDir -ErrorAction SilentlyContinue
    }
}

exit $script:ExitCode

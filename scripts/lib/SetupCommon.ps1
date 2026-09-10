<#
.SYNOPSIS
    scripts/setup_hooks.ps1, scripts/setup_agentsmd.ps1 이 dot-source 하는 공용 오케스트레이션 함수 모음.
.DESCRIPTION
    dry-run 홈 스캐폴딩, 훅 파일 설치, settings.json 조각(res/settings.json) 병합 실행,
    훅 셀프테스트, 매니페스트 기록/제거(uninstall), 최종 리포트 출력을 담당한다. OS 전용
    의존성 설치(send2trash 등)는 호출부가 하나뿐이라 setup_hooks.ps1 에 그대로 둔다.
#>

# 설치가 무엇을 남겼는지 기록하는 매니페스트 파일명 (~/.claude/ 아래).
$MANIFEST_NAME = ".claude-code-setup.json"

function Resolve-PythonCommand {
    # 호출부가 이미 설정했더라도, 이 함수가 단독으로(dot-source 후 직접) 쓰이는 경우까지 방어한다
    # (S1: PS 7.4+ 에서 네이티브 명령의 0이 아닌 종료 코드가 종료 오류로 승격되는 것을 방지 —
    # 아래 프로브는 $LASTEXITCODE 로 성패를 판정하도록 설계돼 있다).
    $PSNativeCommandUseErrorActionPreference = $false
    $candidates = @(
        @{ Exe = "python";  Args = @() },
        @{ Exe = "python3"; Args = @() },
        @{ Exe = "py";      Args = @("-3") },
        @{ Exe = "py";      Args = @() }   # 런처가 아닌 py.exe (= CPython) 는 -3 을 모른다
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
        if ($cmd) {
            $ok = $false
            try {
                & $c.Exe @($c.Args) -c "print(1)" *> $null
                $ok = ($LASTEXITCODE -eq 0)
            } catch {
                $ok = $false
            }
            if ($ok) {
                return @{ Exe = $c.Exe; Args = $c.Args }
            }
        }
    }
    return $null
}

function Resolve-InstallHome {
    param(
        [switch]$DryRun,
        [Parameter(Mandatory)][string]$RealHome,
        [string[]]$SeedFiles = @()   # $RealHome\.claude 기준 상대경로들 (dry-run 시 임시 사본으로 복사)
    )
    $result = [ordered]@{
        RealHome   = $RealHome
        WorkHome   = $RealHome
        CleanupDir = $null
    }
    if ($DryRun) {
        $work = Join-Path ([System.IO.Path]::GetTempPath()) ("claude-setup-dryrun-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
        New-Item -ItemType Directory -Force -Path (Join-Path $work ".claude") | Out-Null
        foreach ($seed in $SeedFiles) {
            $src = Join-Path $RealHome ".claude\$seed"
            if (Test-Path $src) {
                $dst = Join-Path $work ".claude\$seed"
                New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
                Copy-Item $src $dst
            }
        }
        $result.WorkHome = $work
        $result.CleanupDir = $work
    }
    return $result
}

function Install-HookFiles {
    param(
        [Parameter(Mandatory)][string]$HooksDir,
        [Parameter(Mandatory)][hashtable[]]$Files  # @{ Source = "..."; DestName = "..." }
    )
    New-Item -ItemType Directory -Force -Path $HooksDir | Out-Null
    $installed = @()
    foreach ($f in $Files) {
        $dest = Join-Path $HooksDir $f.DestName
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        Copy-Item -Path $f.Source -Destination $dest -Force
        $installed += $dest
    }
    return $installed
}

function Invoke-SettingsMerge {
    param(
        [Parameter(Mandatory)][string]$FragmentPath,   # res/settings.json (실제 형식 조각, SSoT)
        [Parameter(Mandatory)][string]$SettingsPath,   # 병합 대상 (dry-run 이면 임시 사본)
        [switch]$DryRun,
        [Parameter(Mandatory)][string]$PyInvoke,       # {{PY}} 치환값
        [Parameter(Mandatory)][string]$RealHooksDir,   # {{HOOKS_DIR}} 치환값 (항상 실제 설치 위치)
        [Parameter(Mandatory)][string]$MergeScriptPath,
        [Parameter(Mandatory)][string]$PyExe,
        [string[]]$PyArgs = @(),
        [string]$ManifestPath = "",     # 주면 (비 dry-run) merge 가 설치 영수증을 기록
        [string]$HookFilesCsv = "",
        [string]$DefaultMode = ""       # 온보딩이 고른 permissions.defaultMode (비면 조각의 auto)
    )
    $PSNativeCommandUseErrorActionPreference = $false   # S1 방어 — 아래 exit code 는 $LASTEXITCODE 로 판정
    $dry = if ($DryRun) { "1" } else { "0" }
    $modeFlag = if ($DefaultMode) { @("--default-mode", $DefaultMode) } else { @() }
    # 출력을 변수로 캡처해서 다시 Write-Host 로 찍는다 — 그냥 & 로 호출하면 stdout 줄들이
    # 이 함수의 파이프라인 출력에 섞여 들어가서 호출부가 $exitCode 로 받는 값이 오염된다.
    $output = & $PyExe @($PyArgs) -X utf8 $MergeScriptPath @modeFlag $FragmentPath $SettingsPath $dry $PyInvoke $RealHooksDir $ManifestPath $HookFilesCsv
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    return $exitCode
}

function Invoke-HookProbe {
    <#
    .SYNOPSIS
        훅에 JSON 이벤트를 stdin 으로 넣고 stdout 을 문자열로 돌려준다.
    .DESCRIPTION
        `$json | & python hook.py` 형태의 파이프는 Windows PowerShell 5.1 에서 stdin 에
        아무것도 전달하지 못하고 빈 결과를 낸다 (pwsh 7 에서는 정상 동작). 설치 스크립트는
        `powershell` 로 실행되므로 5.1 경로를 타고, 그래서 셀프테스트가 판정을 한 줄도
        출력하지 못한 채 '통과'처럼 보였다 — 가드가 죽어도 알 수 없는 상태였다.
        PowerShell 은 `<` 입력 리다이렉트를 지원하지 않으므로 ProcessStartInfo 로 직접
        stdin 을 연다. 양쪽 버전에서 동일하게 동작한다.
    #>
    param(
        [Parameter(Mandatory)][string]$HookPath,
        [Parameter(Mandatory)][string]$PyExe,
        [string[]]$PyArgs = @(),
        [Parameter(Mandatory)][string]$Json
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $PyExe
    # ArgumentList 는 .NET Core 2.1+ 전용이라 Windows PowerShell 5.1(.NET Framework)에는 없다.
    # 양쪽에서 도는 Arguments 문자열을 직접 만든다 (경로에 공백이 있을 수 있으므로 따옴표).
    $psi.Arguments = (@($PyArgs) + @("-X", "utf8", $HookPath) |
        ForEach-Object { '"' + ($_ -replace '"', '\"') + '"' }) -join ' '
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    # 훅은 -X utf8 로 UTF-8 을 내보낸다. 콘솔 기본 코드페이지(949)로 읽으면 한국어 사유
    # 문구가 깨지므로 명시적으로 UTF-8 로 읽는다.
    $psi.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $psi.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)

    $proc = [System.Diagnostics.Process]::Start($psi)
    # 보낼 바이트를 UTF-8 로 못박는다 — StreamWriter 로 쓰면 인코딩이 콘솔 코드페이지에
    # 딸려가, 한글 경로가 섞인 이벤트에서 무엇이 전달될지 보장할 수 없다.
    #
    # 이것이 BOM 을 없애주지는 '않는다'. .NET Framework 의 Process.StandardInput 은 AutoFlush
    # StreamWriter 라 스트림에 접근하는 순간 인코딩 preamble 을 이미 흘려보내고, 그걸 끄는
    # StandardInputEncoding 은 .NET Core 2.1+ 전용이라 5.1 에는 없다. 실측으로 확인했다:
    # BaseStream 으로 바꾼 뒤에도 훅이 받는 첫 글자는 여전히 U+FEFF 였다. BOM 은 받는 쪽에서
    # 처리한다(각 훅의 read_event_json). 여기를 고쳐서 해결하려 들지 말 것.
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Json)
    $proc.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $proc.StandardInput.BaseStream.Flush()
    $proc.StandardInput.Close()
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    return [pscustomobject]@{
        Stdout   = $stdout.Trim()
        Stderr   = $stderr.Trim()
        ExitCode = $proc.ExitCode
    }
}

function Invoke-HookSelfTest {
    <#
    .SYNOPSIS
        훅 케이스들을 실행하고 판정을 출력한다. 실패한 케이스 수를 돌려준다.
    .DESCRIPTION
        '출력이 비어 있음' 을 성공으로 읽지 않는다. 훅이 죽었거나 stdin 이 전달되지 않으면
        판정이 없는데, 그걸 조용히 넘기면 셀프테스트가 존재할 이유가 없다. 통과(무판단)를
        기대하는 케이스는 라벨에 '통과' 를 넣어 구분한다.
    #>
    param(
        [Parameter(Mandatory)][string]$HookPath,
        [Parameter(Mandatory)][string]$PyExe,
        [string[]]$PyArgs = @(),
        [Parameter(Mandatory)][hashtable[]]$Cases   # @{ Label; Json }
    )
    $failures = 0
    foreach ($c in $Cases) {
        Write-Host "  🧪 $($c.Label)" -ForegroundColor DarkCyan
        $r = Invoke-HookProbe -HookPath $HookPath -PyExe $PyExe -PyArgs $PyArgs -Json $c.Json
        $expectsPass = $c.Label -match '통과'

        if ($r.ExitCode -ne 0) {
            $failures++
            Write-Host "     ❌ 훅이 비정상 종료했습니다 (exit $($r.ExitCode)): $($r.Stderr)" -ForegroundColor Red
            continue
        }
        if (-not $r.Stdout) {
            if ($expectsPass) {
                Write-Host "     ✅ 판정 없음 (통과)" -ForegroundColor DarkGray
            } else {
                $failures++
                Write-Host "     ❌ 판정이 비어 있습니다 — 가드가 이 명령을 그대로 흘려보냅니다." -ForegroundColor Red
            }
            continue
        }

        $decision = $null
        try { $decision = ($r.Stdout | ConvertFrom-Json).hookSpecificOutput.permissionDecision } catch { }
        if (-not $decision) {
            $failures++
            Write-Host "     ❌ 판정을 파싱할 수 없습니다: $($r.Stdout)" -ForegroundColor Red
            continue
        }
        Write-Host "     ✅ $decision" -ForegroundColor DarkGray
        Write-Host "        $($r.Stdout)" -ForegroundColor DarkGray
    }
    return $failures
}

function Write-SetupReport {
    param(
        [switch]$DryRun,
        [string[]]$InstalledFiles = @(),
        [Parameter(Mandatory)][string]$SettingsPath,
        [Parameter(Mandatory)][string]$GuardLogPath,
        [string]$DependencyWarning = $null,
        [string]$DefaultMode = "auto"
    )
    if (-not $DefaultMode) { $DefaultMode = "auto" }
    Write-Host ""
    if ($DryRun) {
        Write-Host "🧪 DRY RUN 완료 — 실제 파일은 하나도 바뀌지 않았습니다." -ForegroundColor Magenta
        Write-Host "   실제로 적용하려면 -DryRun 옵션 없이 다시 실행하세요."
        return
    }

    Write-Host "🎉 초기화 완료!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  생성/수정된 파일 (유저 레벨):" -ForegroundColor White
    foreach ($f in $InstalledFiles) { Write-Host "    $f" }
    Write-Host "    $SettingsPath"
    Write-Host ""
    if ($DependencyWarning) {
        Write-Host "  ⚠️ $DependencyWarning" -ForegroundColor Yellow
    }
    Write-Host "  🔁 중요: 방금 바뀐 권한/모드는 '새 Claude Code 세션'부터 적용됩니다. 실행 중인" -ForegroundColor Yellow
    Write-Host "     세션은 시작 시점의 권한 스냅샷을 그대로 쓰므로(실시간 재로드 안 함), 방금 allow" -ForegroundColor Yellow
    Write-Host "     목록에 넣은 Artifact 등이 이 세션에서는 계속 확인 프롬프트를 띄울 수 있습니다." -ForegroundColor Yellow
    Write-Host "     Claude Code 를 종료 후 다시 실행(새 세션)하면 프롬프트가 사라집니다." -ForegroundColor Yellow
    Write-Host "  ⚠️ 범위 변경 안내: 이 훅과 defaultMode($DefaultMode)는 이제 이 사용자가 여는 모든" -ForegroundColor DarkGray
    Write-Host "     프로젝트에 적용됩니다 (특정 프로젝트 한정이 아님)." -ForegroundColor DarkGray
    if ($DefaultMode -eq "auto") {
        Write-Host "  ℹ️ defaultMode를 'auto'로 설정했지만, 실제로 auto 모드가 켜지려면 계정이" -ForegroundColor DarkGray
        Write-Host "     Claude Code v2.1.83+, Team/Enterprise/API 플랜, Sonnet 4.6 이상 모델 등" -ForegroundColor DarkGray
        Write-Host "     자격 요건을 충족해야 합니다 (아직 research preview, PowerShell 툴에서는" -ForegroundColor DarkGray
        Write-Host "     auto 모드가 아직 지원되지 않는다는 보고도 있습니다). Shift+Tab 으로 모드를" -ForegroundColor DarkGray
        Write-Host "     순환시켜 auto 가 뜨는지 직접 확인해보세요." -ForegroundColor DarkGray
    } elseif ($DefaultMode -eq "bypassPermissions") {
        Write-Host "  ⚠️ defaultMode를 'bypassPermissions'로 설정했습니다 — Claude Code 의 권한 확인이" -ForegroundColor Yellow
        Write-Host "     모두 생략됩니다. 방금 설치한 가드 훅(rm 휴지통 치환, git 백업, 시크릿 확인)은" -ForegroundColor Yellow
        Write-Host "     그대로 동작하지만, 훅이 판단하지 않는 명령은 확인 없이 실행됩니다." -ForegroundColor Yellow
        Write-Host "     되돌리려면 $SettingsPath 의 permissions.defaultMode 를 'auto' 로 바꾸세요." -ForegroundColor Yellow
    }
    Write-Host "  감사 로그: $GuardLogPath"
}

function Uninstall-Hooks {
    param(
        [Parameter(Mandatory)][string]$ClaudeDir,
        [Parameter(Mandatory)][string]$HooksDir,
        [Parameter(Mandatory)][string]$SettingsPath,
        [switch]$DryRun,
        [Parameter(Mandatory)][string]$MergeScriptPath,
        [Parameter(Mandatory)][string]$PyExe,
        [string[]]$PyArgs = @()
    )
    $manifestPath = Join-Path $ClaudeDir $MANIFEST_NAME
    $files = @()
    if (Test-Path $manifestPath) {
        try {
            $m = Get-Content $manifestPath -Raw | ConvertFrom-Json
            if ($m.PSObject.Properties.Name -contains "hook_files") { $files = @($m.hook_files) }
        } catch {}
    }
    if (-not $files -or $files.Count -eq 0) {
        $files = @("danger_guard.py", "secrets_guard.py", "send_to_trash.py",
                   "shims/rm", "shims/RmShim.psm1")
    }

    Write-Host "[1/2] settings.json 정밀 복원 (설치가 건드린 것만)..."
    $dry = if ($DryRun) { "1" } else { "0" }
    $output = & $PyExe @($PyArgs) -X utf8 $MergeScriptPath --uninstall $SettingsPath $dry $manifestPath
    $output | ForEach-Object { Write-Host $_ }

    Write-Host ""
    Write-Host "[2/2] 훅 파일 + guard.log + 매니페스트 제거..."
    $targets = @()
    foreach ($f in $files) { $targets += (Join-Path $HooksDir $f) }
    $targets += (Join-Path $HooksDir "guard.log")   # 설치 셀프테스트가 생성
    $shimsDir = Join-Path $HooksDir "shims"
    foreach ($target in $targets) {
        if (Test-Path $target) {
            if ($DryRun) {
                Write-Host "  🧪 (dry-run) 제거 예정: $target"
            } else {
                Remove-Item -Force $target -ErrorAction SilentlyContinue
                Write-Host "  🗑️  제거: $target"
            }
        }
    }

    # 셰임 디렉터리는 파일을 다 걷어낸 뒤 비어 있을 때만 지운다.
    if (-not $DryRun -and (Test-Path $shimsDir) -and
        -not (Get-ChildItem -LiteralPath $shimsDir -Force)) {
        Remove-Item -Force $shimsDir -ErrorAction SilentlyContinue
    }

    # 매니페스트: keybinds 영수증이 남아 있으면 그 섹션만 남기고 훅 흔적만 지운다.
    # 통째로 지우면 키바인드 uninstall 이 '우리가 넣은 tmux 줄' 을 식별할 근거를 잃는다.
    if (Test-Path $manifestPath) {
        if ($DryRun) {
            Write-Host "  🧪 (dry-run) 제거 예정: $manifestPath"
        } else {
            $keptKeybinds = $null
            try {
                $m = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($m -and $m.PSObject.Properties.Name -contains "keybinds" -and $m.keybinds) {
                    $keptKeybinds = $m.keybinds
                }
            } catch { $keptKeybinds = $null }
            if ($null -ne $keptKeybinds) {
                $payload = [ordered]@{ keybinds = $keptKeybinds }
                Set-Content -Path $manifestPath -Value ($payload | ConvertTo-Json -Depth 20) -Encoding UTF8
                Write-Host "  🧾 유지: $manifestPath (키바인드 영수증만 남김)"
            } else {
                Remove-Item -Force $manifestPath -ErrorAction SilentlyContinue
                Write-Host "  🗑️  제거: $manifestPath"
            }
        }
    }
}

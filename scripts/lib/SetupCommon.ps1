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

# Resolve-PythonCommand 가 실패했을 때 이 환경에서 Python 3 을 설치하는 명령을 안내한다.
# 설치는 하지 않는다 — 런타임 설치는 되돌리기 어렵고 uninstall 대칭 밖이라 사용자가 직접 한다.
function Write-PythonInstallHint {
    $onMac = (Test-Path variable:IsMacOS) -and $IsMacOS
    $onLinux = (Test-Path variable:IsLinux) -and $IsLinux
    Write-Host "   How to install Python 3:" -ForegroundColor Yellow
    if ($onMac) {
        Write-Host "     brew install python"
    } elseif ($onLinux) {
        Write-Host "     sudo apt-get install -y python3   # Debian/Ubuntu"
        Write-Host "     sudo dnf install -y python3       # Fedora/RHEL"
    } else {
        Write-Host "     winget install -e --id Python.Python.3.14"
        Write-Host "   Without winget, install it from https://www.python.org/downloads/windows/."
        Write-Host "   After installing, run again in a new terminal. If the Microsoft Store still opens,"
        Write-Host "   turn off python.exe / python3.exe under Settings > Apps > Advanced app settings > App execution aliases."
    }
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
    $modeFlag = @("--windows")   # Windows 전용 env 키(graft 래퍼 경로)도 병합한다
    if ($DefaultMode) { $modeFlag += @("--default-mode", $DefaultMode) }
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
        기대하는 케이스는 라벨에 'expect pass' 를 넣어 구분한다. 성공한 케이스는 한 줄 요약으로 접고,
        실패한 케이스만 사유와 함께 보여 준다 (setup_common.sh 의 run_hook_self_test 와 같다).
    #>
    param(
        [Parameter(Mandatory)][string]$HookPath,
        [Parameter(Mandatory)][string]$PyExe,
        [string[]]$PyArgs = @(),
        [Parameter(Mandatory)][hashtable[]]$Cases   # @{ Label; Json }
    )
    $failures = 0
    foreach ($c in $Cases) {
        $r = Invoke-HookProbe -HookPath $HookPath -PyExe $PyExe -PyArgs $PyArgs -Json $c.Json
        $expectsPass = $c.Label -match 'expect pass'

        if ($r.ExitCode -ne 0) {
            $failures++
            Write-Host "  ❌ $($c.Label)" -ForegroundColor Red
            Write-Host "     Hook exited abnormally (exit $($r.ExitCode)): $($r.Stderr)" -ForegroundColor Red
            continue
        }
        if (-not $r.Stdout) {
            if (-not $expectsPass) {
                $failures++
                Write-Host "  ❌ $($c.Label)" -ForegroundColor Red
                Write-Host "     Empty decision — the guard lets this command through unchecked." -ForegroundColor Red
            }
            continue
        }

        $decision = $null
        try {
            $props = ($r.Stdout | ConvertFrom-Json).hookSpecificOutput.PSObject.Properties
            # 셰임 선행 줄은 판정 없이 updatedInput 만 낸다 — allow 를 붙이면 권한 프롬프트를
            # 건너뛴다. StrictMode 에서 없는 속성을 읽으면 예외이므로 존재 여부로 고른다.
            if ($props['permissionDecision']) { $decision = $props['permissionDecision'].Value }
            elseif ($props['updatedInput']) { $decision = 'updatedInput' }
        } catch { }
        if (-not $decision) {
            $failures++
            Write-Host "  ❌ $($c.Label)" -ForegroundColor Red
            Write-Host "     Could not parse the decision: $($r.Stdout)" -ForegroundColor Red
        }
    }
    if ($failures -eq 0) {
        Write-Host "  ✅ Self-test $($Cases.Count)/$($Cases.Count) passed" -ForegroundColor Green
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
        Write-Host "🧪 DRY RUN complete — no real files were changed." -ForegroundColor Magenta
        Write-Host "   To actually apply, run again without the -DryRun option."
        return
    }

    Write-Host "🎉 Setup complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Created/modified files (user level):" -ForegroundColor White
    foreach ($f in $InstalledFiles) { Write-Host "    $f" }
    Write-Host "    $SettingsPath"
    Write-Host ""
    if ($DependencyWarning) {
        Write-Host "  ⚠️ $DependencyWarning" -ForegroundColor Yellow
    }
    Write-Host "  🔁 Important: the permissions/mode just changed apply from a 'new Claude Code session'. A running" -ForegroundColor Yellow
    Write-Host "     session keeps the permission snapshot from its start (no live reload), so items just added to the allow" -ForegroundColor Yellow
    Write-Host "     list, such as Artifact, may keep showing confirmation prompts in this session." -ForegroundColor Yellow
    Write-Host "     Quit and restart Claude Code (new session) and the prompts go away." -ForegroundColor Yellow
    Write-Host "  ⚠️ Scope change notice: these hooks and defaultMode($DefaultMode) now apply to every" -ForegroundColor DarkGray
    Write-Host "     project this user opens (not limited to one project)." -ForegroundColor DarkGray
    if ($DefaultMode -eq "auto") {
        Write-Host "  ℹ️ defaultMode is set to 'auto', but for auto mode to actually turn on, the account must meet" -ForegroundColor DarkGray
        Write-Host "     eligibility requirements such as Claude Code v2.1.83+, a Team/Enterprise/API plan, and Sonnet 4.6" -ForegroundColor DarkGray
        Write-Host "     or later (still a research preview, and there are reports that the PowerShell tool" -ForegroundColor DarkGray
        Write-Host "     does not support auto mode yet). Cycle modes with Shift+Tab" -ForegroundColor DarkGray
        Write-Host "     to check that auto shows up." -ForegroundColor DarkGray
    } elseif ($DefaultMode -eq "bypassPermissions") {
        Write-Host "  ⚠️ defaultMode is set to 'bypassPermissions' — all Claude Code permission checks" -ForegroundColor Yellow
        Write-Host "     are skipped. The guard hooks just installed (rm to trash, git backup, secret checks)" -ForegroundColor Yellow
        Write-Host "     still work, but commands the hooks do not judge run without confirmation." -ForegroundColor Yellow
        Write-Host "     To revert, set permissions.defaultMode in $SettingsPath to 'auto'." -ForegroundColor Yellow
    }
    Write-Host "  Audit log: $GuardLogPath"
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
        # 영수증은 하네스·도구·Orca 설치 기록도 함께 담는다. 읽지 못하면 아무것도 건드리지 않고 멈춘다.
        # 객체가 아닌 JSON 은 기록을 담을 수 없으므로 merge_and_diff.py 처럼 빈 영수증으로 본다.
        $parsed = $true
        try { $m = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $parsed = $false }
        if ($parsed -and $m -isnot [pscustomobject]) { $m = [pscustomobject]@{} }
        if (-not $parsed) {
            Write-Host "❌ Cannot parse the install receipt: $manifestPath" -ForegroundColor Red
            Write-Host "   Nothing was changed. Fix or move the file, then run the uninstall again." -ForegroundColor Red
            exit 1
        }
        # StrictMode 에서 빈 객체의 .Properties.Name 은 예외다. 인덱서로 조회한다.
        if ($null -ne $m.PSObject.Properties["hook_files"]) { $files = @($m.hook_files) }
    }
    if (-not $files -or $files.Count -eq 0) {
        $files = @("danger_guard.py", "secrets_guard.py", "send_to_trash.py",
                   "shims/rm", "shims/RmShim.psm1", "graft_sync_hidden.cjs")
    }

    Write-Host "[1/2] Precisely restoring settings.json (only what the install touched)..."
    $dry = if ($DryRun) { "1" } else { "0" }
    $output = & $PyExe @($PyArgs) -X utf8 $MergeScriptPath --uninstall $SettingsPath $dry $manifestPath
    $output | ForEach-Object { Write-Host $_ }

    Write-Host ""
    Write-Host "[2/2] Removing hook files + guard.log + manifest..."
    $targets = @()
    foreach ($f in $files) { $targets += (Join-Path $HooksDir $f) }
    $targets += (Join-Path $HooksDir "guard.log")   # 설치 셀프테스트가 생성
    $shimsDir = Join-Path $HooksDir "shims"
    foreach ($target in $targets) {
        if (Test-Path $target) {
            if ($DryRun) {
                Write-Host "  🧪 (dry-run) would remove: $target"
            } else {
                Remove-Item -Force $target -ErrorAction SilentlyContinue
                Write-Host "  🗑️  Removed: $target"
            }
        }
    }

    # 셰임 디렉터리는 파일을 다 걷어낸 뒤 비어 있을 때만 지운다.
    if (-not $DryRun -and (Test-Path $shimsDir) -and
        -not (Get-ChildItem -LiteralPath $shimsDir -Force)) {
        Remove-Item -Force $shimsDir -ErrorAction SilentlyContinue
    }

    # 매니페스트: 다른 워커의 영수증(keybinds, omc_hud, output_style, mods)이 남아 있으면 그 섹션만 남기고 훅 흔적만 지운다.
    # 단계식 설치의 하네스·플러그인·MCP·Jarvis 유닛·AGENTS.md·스킬 기록도 남긴다. 이 제거는 앞의 것들을
    # 되돌리지 않고, 스킬은 범위에 따라 지우지 않을 수도 있다(스킬 소유는 스킬 영수증과 교차 확인). 그래서
    # 지우면 --uninstall --stages all 이 무엇을 이 셋업이 깔았는지 알 수 없다.
    # 통째로 지우면 키바인드 uninstall 이 '우리가 넣은 tmux 줄' 을, OMC uninstall 이 '우리가 넣은
    # refreshInterval' 을 식별할 근거를 잃는다.
    if (Test-Path $manifestPath) {
        if ($DryRun) {
            Write-Host "  🧪 (dry-run) would remove: $manifestPath"
        } else {
            # $m 은 위에서 이미 읽고 검증한 영수증이다. 읽지 못한 영수증은 여기까지 오지 않는다.
            $payload = [ordered]@{}
            foreach ($key in @("keybinds", "omc_hud", "output_style", "mods", "tool_installs", "tool_attempts", "harness_installs", "plugins", "mcp", "jarvis_unit", "agentsmd", "skills", "marketplaces")) {
                # 빈 객체({})도 PowerShell 에서는 참이다. bash 쪽과 같게 빈 값은 버린다.
                $value = if ($null -ne $m.PSObject.Properties[$key]) { $m.$key } else { $null }
                $present = if ($value -is [pscustomobject]) { @($value.PSObject.Properties).Count -gt 0 } else { [bool]$value }
                if ($present) {
                    $payload[$key] = $m.$key
                }
            }
            if ($payload.Count -gt 0) {
                # BOM 없이 쓴다. Windows PowerShell 5.1 의 Set-Content -Encoding UTF8 은 BOM 을 붙인다.
                [IO.File]::WriteAllText($manifestPath, ($payload | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding $false))
                Write-Host "  🧾 Kept: $manifestPath (only other workers' manifests remain)"
            } else {
                Remove-Item -Force $manifestPath -ErrorAction SilentlyContinue
                Write-Host "  🗑️  Removed: $manifestPath"
            }
        }
    }
}

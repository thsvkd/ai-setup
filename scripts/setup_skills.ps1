<#
.SYNOPSIS
    Bundled Claude Code skills worker (Windows).
#>
param([switch]$DryRun, [switch]$Uninstall)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
. (Join-Path $PSScriptRoot "lib\SetupCommon.ps1")
$py = Resolve-PythonCommand
if (-not $py) { Write-Host "Python 3 is required." -ForegroundColor Red; Write-PythonInstallHint; exit 1 }
$homeDir = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
$worker = Join-Path (Split-Path -Parent $PSScriptRoot) "res\skills\apply.py"
$pyArgs = @("-X", "utf8", $worker, "--home", $homeDir)
if ($DryRun) { $pyArgs += "--dry-run" }
if ($Uninstall) { $pyArgs += "--uninstall" }
& $py.Exe @($py.Args) @pyArgs
exit $LASTEXITCODE

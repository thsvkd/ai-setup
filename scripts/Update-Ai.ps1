<#
.SYNOPSIS
    update-ai — 설치된 AI 하네스·도구·플러그인을 한 번에 최신으로 (Windows).
.DESCRIPTION
    구현은 res/update/update_ai.py 하나다. 이 파일은 Python 을 찾아 인자를 넘기기만 한다.
.USAGE
    powershell -ExecutionPolicy Bypass -File scripts\Update-Ai.ps1 [-Check] [-Only a,b] [-AllowInterrupt]
    (setup.sh 와 같은 --check --only a,b --allow-interrupt 표기도 받는다)
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Check,
    [string[]]$Only = @(),
    [switch]$AllowInterrupt,
    [Alias("h")]
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @()
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot "lib\SetupCommon.ps1")

$py = Resolve-PythonCommand
if (-not $py) { Write-Host "Python 3 is required." -ForegroundColor Red; Write-PythonInstallHint; exit 2 }
$pyArgs = @("-X", "utf8", (Join-Path (Split-Path -Parent $PSScriptRoot) "res\update\update_ai.py"))
if ($Help) { $pyArgs += "--help" }
if ($Check) { $pyArgs += "--check" }
if ($AllowInterrupt) { $pyArgs += "--allow-interrupt" }
foreach ($o in $Only) { $pyArgs += @("--only", $o) }
# 긴 표기(--check 등)와 대상 이름은 Python 이 그대로 해석한다.
$pyArgs += $Rest
& $py.Exe @($py.Args) @pyArgs
exit $LASTEXITCODE

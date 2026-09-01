<#
.SYNOPSIS
    Install the project instruction files into the current working directory,
    which is assumed to be the target project root (Windows)
.DESCRIPTION
    Which files get written depends on the selected harnesses. Codex, Grok and
    OpenCode read the root AGENTS.md directly, so AGENTS.md is always written.
    Claude Code does not read AGENTS.md -- it reads CLAUDE.md -- so a one-line
    CLAUDE.md importing @AGENTS.md is written as well when claude is selected.
    A symlink would also work but needs Administrator rights on Windows, so the
    import is used on every platform for parity.

    An existing file is never overwritten; it is skipped. These files are meant
    to be customised per project, so there is no surgical merge as there is for
    settings.json -- the policy is simply "install when absent".

    -Force overwrites, and is only used when the user explicitly chose to
    overwrite during onboarding. The original is kept as .bak.<timestamp>.

    This is the worker that the scripts/setup.ps1 dispatcher calls with
    -AgentsMd. It can also be run directly from a project root.
.USAGE
    setup_agentsmd.ps1                            # install (skip existing files)
    setup_agentsmd.ps1 -Harness claude,codex      # only those harnesses
    setup_agentsmd.ps1 -Force                     # back up, then overwrite
    setup_agentsmd.ps1 -DryRun                    # preview, touch nothing
#>

param(
    [switch]$DryRun,
    [switch]$Force,
    # Every supported harness by default: this installer exists to set up
    # whichever agent the user runs, and each artefact is additive and skipped
    # when present. Accepts a comma-separated string or an array.
    [string[]]$Harness = @("all")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ProjectDir = (Get-Location).Path

# Expand the selection, rejecting names we do not know rather than silently
# installing something the user did not ask for.
function Resolve-Harnesses {
    param([string[]]$Requested)

    $selected = [System.Collections.Generic.List[string]]::new()
    foreach ($entry in $Requested) {
        foreach ($raw in ($entry -split ",")) {
            $name = $raw.Trim().ToLowerInvariant()
            if (-not $name) { continue }

            $expanded = switch ($name) {
                "all"         { @("claude", "codex", "grok", "opencode") }
                "claude"      { @("claude") }
                "claude-code" { @("claude") }
                "codex"       { @("codex") }
                "grok"        { @("grok") }
                "opencode"    { @("opencode") }
                default {
                    Write-Error "알 수 없는 하네스: $name (claude|codex|grok|opencode|all)"
                    exit 1
                }
            }
            foreach ($item in $expanded) {
                if (-not $selected.Contains($item)) { $selected.Add($item) }
            }
        }
    }

    if ($selected.Count -eq 0) {
        Write-Error "하네스를 최소 하나는 골라야 합니다 (claude|codex|grok|opencode|all)"
        exit 1
    }
    return $selected
}

# Install one file, honouring skip/force/backup/dry-run identically for every
# file so a second artefact cannot acquire weaker guarantees than AGENTS.md.
function Install-InstructionFile {
    param([string]$Source, [string]$Target)

    if (-not (Test-Path $Source)) {
        Write-Error "❌ 소스 파일을 찾을 수 없습니다: $Source"
        exit 1
    }

    $exists = Test-Path $Target

    if ($exists -and -not $Force) {
        Write-Host "  ℹ️ 이미 $Target 가 존재합니다 — 덮어쓰지 않고 건너뜁니다." -ForegroundColor DarkGray
        return
    }

    if ($DryRun) {
        if ($exists) {
            Write-Host "  🧪 DRY RUN — 기존 $Target 를 백업 후 덮어쓸 예정입니다 (실제로 쓰지 않음)." -ForegroundColor Magenta
        } else {
            Write-Host "  🧪 DRY RUN — $Target 에 설치될 예정입니다 (실제로 쓰지 않음)." -ForegroundColor Magenta
        }
        return
    }

    # Overwriting destroys user content, so the original is always kept.
    if ($exists) {
        $backup = "$Target.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Copy-Item -Path $Target -Destination $backup
        Write-Host "  💾 기존 파일 백업: $backup" -ForegroundColor DarkGray
    }
    Copy-Item -Path $Source -Destination $Target -Force
    Write-Host "  ✅ 설치 완료: $Target" -ForegroundColor Green
}

$selected = Resolve-Harnesses -Requested $Harness

Write-Host "🔧 프로젝트 지침 설치... (하네스: $($selected -join ','))" -ForegroundColor Cyan

# AGENTS.md is the shared source for every harness, including Claude Code, which
# reaches it through the CLAUDE.md import.
Install-InstructionFile -Source (Join-Path $RepoRoot "res\AGENTS.md") -Target (Join-Path $ProjectDir "AGENTS.md")

if ($selected.Contains("claude")) {
    $claudeTarget = Join-Path $ProjectDir "CLAUDE.md"
    $hadClaudeMd = Test-Path $claudeTarget

    Install-InstructionFile -Source (Join-Path $RepoRoot "res\CLAUDE.md") -Target $claudeTarget

    # Skipping an existing CLAUDE.md is the right default -- it is user content.
    # But if that file does not import AGENTS.md, Claude Code never reads the
    # instructions we just installed, and staying silent would report success
    # for an install that did nothing for the harness the user selected.
    if ($hadClaudeMd -and -not $Force -and
        -not (Select-String -Path $claudeTarget -Pattern "@AGENTS\.md" -Quiet)) {
        Write-Host "  ⚠️ 기존 $claudeTarget 에 '@AGENTS.md' 가 없습니다 — Claude Code 는 방금 설치한 AGENTS.md 를 읽지 않습니다." -ForegroundColor Yellow
        Write-Host "     기존 내용을 지우지 않으려면 그 파일 맨 위에 '@AGENTS.md' 한 줄을 직접 추가하세요." -ForegroundColor Yellow
    }
}

exit 0

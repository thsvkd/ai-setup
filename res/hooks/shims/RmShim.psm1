# Remove-Item 셰임 — 삭제를 휴지통 이동으로 바꾼다.
#
# 훅이 명령 문자열을 재작성하는 대신 이 모듈을 Import-Module 하는 한 줄만 앞에 붙인다.
# PowerShell 의 명령 우선순위는 별칭 > 함수 > cmdlet 이라, 같은 이름의 함수가 cmdlet 을
# 가린다. rm / del / erase / ri / rd / rmdir 은 전부 Remove-Item 을 가리키는 별칭이므로
# 이 함수 하나로 모두 덮인다. 인자 파싱은 PowerShell 이 하므로 훅이 따옴표를 다시 씌우다
# 확장을 깨뜨리는 사고가 원리적으로 일어나지 않는다.

Set-StrictMode -Off

$script:RealRemoveItem = Microsoft.PowerShell.Core\Get-Command `
    -Name Microsoft.PowerShell.Management\Remove-Item -CommandType Cmdlet

function Test-ClaudeRootPath {
    param([string]$FullPath)
    $p = $FullPath.TrimEnd('\', '/')
    if ([string]::IsNullOrEmpty($p)) { return $true }
    $home_ = $env:USERPROFILE
    if (-not $home_) { $home_ = $HOME }
    if ($home_ -and $p -eq $home_.TrimEnd('\', '/')) { return $true }
    # C:\ , D:\ 같은 드라이브 루트와 POSIX 루트.
    if ($p -match '^[A-Za-z]:$') { return $true }
    if ($p -eq '') { return $true }
    return $false
}

function Send-ClaudeTrash {
    <#
      .SYNOPSIS
      경로들을 휴지통으로 옮긴다. 옮길 수단이 없으면 예외를 던져 호출자가 원본 cmdlet 으로
      넘기게 한다 — 삭제 자체를 막아버리는 쪽이 더 해롭기 때문이다.
    #>
    param([Parameter(Mandatory = $true)][string[]]$Paths)

    if ($env:OS -eq 'Windows_NT') {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop
        foreach ($p in $Paths) {
            if (Test-Path -LiteralPath $p -PathType Container) {
                [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
                    $p, 'OnlyErrorDialogs', 'SendToRecycleBin')
            }
            else {
                [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
                    $p, 'OnlyErrorDialogs', 'SendToRecycleBin')
            }
        }
        return
    }

    # SilentlyContinue 는 못 찾은 기록을 $Error 에 남겨, 삭제가 성공해도 원본 cmdlet 과 달라진다(macOS).
    $trash = Microsoft.PowerShell.Core\Get-Command trash-put -ErrorAction Ignore
    if ($trash) {
        & $trash.Source -- @Paths
    }
    elseif ($IsMacOS -and ($trash = Microsoft.PowerShell.Core\Get-Command trash -ErrorAction Ignore)) {
        # macOS 14.4+ 기본 /usr/bin/trash (shims/rm 과 같은 우선순위). `--` 지원이 문서화돼
        # 있지 않지만 $Paths 는 Get-Item 의 FullName(절대경로)이라 대시로 시작하지 않는다.
        & $trash.Source @Paths
    }
    else { throw 'No trash tool found.' }
    if ($LASTEXITCODE -ne 0) { throw "$($trash.Name) failed with exit code $LASTEXITCODE." }
}

function Remove-Item {
    [CmdletBinding(DefaultParameterSetName = 'Path', SupportsShouldProcess = $true,
        ConfirmImpact = 'Medium')]
    param(
        [Parameter(ParameterSetName = 'Path', Mandatory = $true, Position = 0,
            ValueFromPipeline = $true, ValueFromPipelineByPropertyName = $true)]
        [string[]]$Path,

        [Parameter(ParameterSetName = 'LiteralPath', Mandatory = $true,
            ValueFromPipelineByPropertyName = $true)]
        [Alias('PSPath', 'LP')]
        [string[]]$LiteralPath,

        [string]$Filter,
        [string[]]$Include,
        [string[]]$Exclude,
        [switch]$Recurse,
        [switch]$Force,
        [System.Management.Automation.PSCredential]$Credential,
        [switch]$Stream
    )

    begin { $collected = New-Object System.Collections.Generic.List[string] }

    process {
        if ($PSCmdlet.ParameterSetName -eq 'LiteralPath') { $collected.AddRange([string[]]$LiteralPath) }
        else { $collected.AddRange([string[]]$Path) }
    }

    end {
        $literal = $PSCmdlet.ParameterSetName -eq 'LiteralPath'

        # 원본 cmdlet 에게 그대로 넘겨야 하는 경우들. 셰임이 흉내 내면 의미가 달라진다.
        #  - -WhatIf/-Confirm: 확인 흐름은 cmdlet 이 내는 그대로여야 한다.
        #  - -Stream/-Credential/-Filter/-Include/-Exclude: 휴지통으로는 표현할 수 없다.
        $delegate = $WhatIfPreference -or $PSBoundParameters.ContainsKey('Confirm') -or
                    $Stream -or $Credential -or $Filter -or $Include -or $Exclude
        if (-not $delegate) {
            $items = @()
            foreach ($p in $collected) {
                $got = if ($literal) {
                    Get-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
                }
                else {
                    Get-Item -Path $p -Force -ErrorAction SilentlyContinue
                }
                if ($got) { $items += $got }
            }
            # 아무것도 못 찾았다(오탈자·없는 파일) → 오류 문구까지 cmdlet 것을 그대로 쓴다.
            # 파일시스템이 아닌 공급자(Env:, HKLM:, Variable:)도 휴지통 대상이 아니다.
            if (-not $items -or ($items | Where-Object { $_.PSProvider.Name -ne 'FileSystem' })) {
                $delegate = $true
            }
        }

        if ($delegate) {
            & $script:RealRemoveItem @PSBoundParameters
            return
        }

        $targets = @()
        foreach ($i in $items) {
            $full = $i.FullName
            if (Test-ClaudeRootPath $full) {
                Write-Error "Remove-Item(shim): refusing to delete the entire root/home directory ($full)."
                return
            }
            if ($targets -notcontains $full) { $targets += $full }
        }

        try {
            Send-ClaudeTrash -Paths $targets
        }
        catch {
            Write-Warning "Remove-Item(shim): could not move to the trash; deleting for real - $($_.Exception.Message)"
            & $script:RealRemoveItem @PSBoundParameters
        }
    }
}

Export-ModuleMember -Function Remove-Item

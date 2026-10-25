"""Change only the current user's Orca scheduled task through Windows consent."""
import base64
import ctypes
import json
from functools import lru_cache
from pathlib import Path
import subprocess


WORKER = r'''
$ErrorActionPreference = 'Stop'
$data = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PAYLOAD__')) | ConvertFrom-Json
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if ($identity.User.Value -ne $data.callerSid) {
        throw 'The administrator account must match the original Windows user.'
    }
    $scheduler = New-Object -ComObject 'Schedule.Service'
    $scheduler.Connect()
    $folder = $scheduler.GetFolder('\')
    $reference = $scheduler.NewTask(0)
    $reference.XmlText = [regex]::Replace([IO.File]::ReadAllText($data.service), '<\?xml[^?]*\?>', '')
    if ($reference.Actions.Count -ne 1 -or $reference.Actions.Item(1).Type -ne 0) {
        throw 'The Orca service action changed; preserving existing tasks.'
    }
    $expected = $reference.Actions.Item(1)
    if (-not $expected.Arguments.Contains($data.runner)) { throw 'Invalid Orca runner action.' }
    if ($data.operation -eq 'create') {
        $definition = $scheduler.NewTask(0)
        $xml = [IO.File]::ReadAllText($data.service)
        $definition.XmlText = [regex]::Replace($xml, '<\?xml[^?]*\?>', '')
        if ($definition.Actions.Count -ne 1 -or $definition.Actions.Item(1).Type -ne 0 -or
            $definition.Actions.Item(1).Path -ne $expected.Path -or
            $definition.Actions.Item(1).Arguments -cne $expected.Arguments -or
            $definition.Actions.Item(1).WorkingDirectory -ne $expected.WorkingDirectory) {
            throw 'The Orca service action changed; preserving existing tasks.'
        }
        $definition.Principal.UserId = $data.callerSid
        $definition.Principal.LogonType = 2
        $definition.Principal.RunLevel = 0
        $null = $folder.RegisterTaskDefinition($data.task, $definition, 2, $data.callerSid, $null, 2)
    } elseif ($data.operation -eq 'delete') {
        try { $definition = $folder.GetTask($data.task).Definition } catch {
            if ($_.Exception.HResult -eq -2147024894) { exit 0 }
            throw
        }
        if ($definition.Actions.Count -ne 1 -or $definition.Actions.Item(1).Type -ne 0 -or
            $definition.Actions.Item(1).Path -ne $expected.Path -or
            $definition.Actions.Item(1).Arguments -cne $expected.Arguments -or
            $definition.Actions.Item(1).WorkingDirectory -ne $expected.WorkingDirectory -or
            $definition.Principal.RunLevel -ne 0 -or $definition.Principal.LogonType -ne 2) {
            throw 'The registered Orca service action changed; preserving it.'
        }
        $account = [Security.Principal.NTAccount]::new($definition.Principal.UserId)
        $sid = if ($definition.Principal.UserId.StartsWith('S-1-')) {
            $definition.Principal.UserId
        } else { $account.Translate([Security.Principal.SecurityIdentifier]).Value }
        if ($sid -ne $data.callerSid) { throw 'The registered Orca task belongs to another user.' }
        $folder.DeleteTask($data.task, 0)
    } else {
        throw 'Unsupported Orca task operation.'
    }
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit $_.Exception.HResult
}
'''


def powershell_path():
    system = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(system, len(system)):
        raise OSError('Could not locate Windows PowerShell')
    return Path(system.value) / 'WindowsPowerShell/v1.0/powershell.exe'


@lru_cache(maxsize=1)
def current_user_sid():
    result = subprocess.run(
        [str(powershell_path()), '-NoProfile', '-NonInteractive', '-Command',
         '[Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],
        check=True, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    value = result.stdout.strip()
    if not value.startswith('S-1-') or any(char not in 'S-0123456789' for char in value):
        raise RuntimeError('Could not identify the Windows user')
    return value


def protect_file(path):
    path.chmod(0o600)
    system = powershell_path().parents[2]
    subprocess.run(
        [str(system / 'icacls.exe'), str(path), '/grant:r', '*' + current_user_sid() + ':(F)'],
        check=True, capture_output=True, timeout=30,
    )


def change_task(plan, operation):
    if operation not in ('create', 'delete'):
        raise ValueError('Unsupported Orca task operation')
    powershell = powershell_path()
    template = base64.b64encode(WORKER.encode('utf-8')).decode('ascii')
    script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$data | Add-Member -NotePropertyName callerSid -NotePropertyValue $identity.User.Value -Force
$payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($data | ConvertTo-Json -Compress)))
$worker = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__TEMPLATE__')).Replace('__PAYLOAD__', $payload)
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    & ([scriptblock]::Create($worker))
} else {
    try {
        $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($worker))
        $process = Start-Process -FilePath $data.powershell -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList @('-NoProfile', '-NonInteractive', '-EncodedCommand', $encoded)
        exit $process.ExitCode
    } catch {
        if ($_.Exception.NativeErrorCode -eq 1223) { exit 1223 }
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 1
    }
}
'''.replace('__TEMPLATE__', template)
    result = subprocess.run(
        [str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
        input=json.dumps({'task': plan['task'], 'service': str(plan['service']),
                          'runner': str(plan['runner']), 'operation': operation,
                          'powershell': str(powershell)}),
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120,
    )
    if result.returncode == 1223:
        result.stderr = 'Administrator consent was cancelled; the setup checkpoint was preserved'
    elif result.returncode and not result.stderr.strip():
        result.stderr = 'Windows task {} failed (0x{:08x})'.format(operation, result.returncode & 0xffffffff)
    return result

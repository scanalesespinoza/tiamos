param(
    [string]$PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
)

$ErrorActionPreference = 'Stop'
$appPath = Join-Path $PSScriptRoot 'tiamos.py'
$launcherDirectory = Join-Path $HOME 'bin'
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    throw "Application not found: $appPath"
}
& $PythonPath -c 'import tkinter; import PIL; import psutil'
if ($LASTEXITCODE -ne 0) {
    throw 'Python needs Tkinter, Pillow, and psutil. Install requirements.txt using this interpreter.'
}
New-Item -ItemType Directory -Path $launcherDirectory -Force | Out-Null
$providerCheck = @'
import sys
sys.path.insert(0, sys.argv[1])
from cli_sessions import cli_executable
from claude_sessions import claude_executable
found = []
for check in (cli_executable, claude_executable):
    try:
        found.append(check())
    except RuntimeError:
        pass
print('tiamos providers: ' + str(len(found)))
sys.exit(0 if found else 1)
'@
& $PythonPath -c $providerCheck $PSScriptRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Install Codex CLI or Claude CLI and make it available to this user.'
}
$launcher = "@echo off`r`n`"$PythonPath`" `"$appPath`" %*`r`n"
foreach ($launcherName in @('tiamos.cmd', 'agentlings.cmd', 'codex-float.cmd')) {
    $launcherPath = Join-Path $launcherDirectory $launcherName
    [IO.File]::WriteAllText($launcherPath, $launcher, [Text.Encoding]::Default)
    Write-Output "Installed launcher: $launcherPath"
}
Write-Output 'Use tiamos on. The launcher directory must be on PATH. codex-float remains an alias.'

param(
    [string]$PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
)

$ErrorActionPreference = 'Stop'
$appPath = Join-Path $PSScriptRoot 'codex_float.py'
$launcherDirectory = Join-Path $HOME 'bin'
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    throw "Application not found: $appPath"
}
& $PythonPath -c 'import tkinter; import PIL'
if ($LASTEXITCODE -ne 0) {
    throw 'Python needs Tkinter and Pillow. Install requirements.txt using this interpreter.'
}
New-Item -ItemType Directory -Path $launcherDirectory -Force | Out-Null
$launcherPath = Join-Path $launcherDirectory 'codex-float.cmd'
$launcher = "@echo off`r`n`"$PythonPath`" `"$appPath`" %*`r`n"
[IO.File]::WriteAllText($launcherPath, $launcher, [Text.Encoding]::Default)
Write-Output "Installed launcher: $launcherPath"
Write-Output 'Use codex-float on. The launcher directory must be on PATH.'

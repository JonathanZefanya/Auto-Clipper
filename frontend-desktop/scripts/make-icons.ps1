$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot "..\..\backend\.venv\Scripts\python.exe"
& $py (Join-Path $PSScriptRoot "make_icons.py")

param(
  [string]$Root = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
$rootPath = (Resolve-Path -LiteralPath $Root).Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Sonario.lnk"
$wscript = Join-Path $env:WINDIR "System32\wscript.exe"
$launcher = Join-Path $rootPath "sonario_launcher.vbs"
$icon = Join-Path $rootPath "sonario.ico"
$favicon = Join-Path $rootPath "static\favicon.ico"
$sourcePng = Join-Path $rootPath "static\icon-512.png"
$python = Join-Path $rootPath "venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $launcher)) { throw "Missing launcher: $launcher" }

# ICO files are generated locally and intentionally excluded from Git. This
# preserves a crisp multi-resolution desktop/taskbar icon without tracking a
# duplicate binary asset in the repository.
if (-not (Test-Path -LiteralPath $icon)) {
  if (-not (Test-Path -LiteralPath $python)) { throw "Missing Python environment: $python" }
  if (-not (Test-Path -LiteralPath $sourcePng)) { throw "Missing icon source: $sourcePng" }
  $script = @'
from pathlib import Path
from PIL import Image
import sys
src, desktop, favicon = map(Path, sys.argv[1:4])
image = Image.open(src).convert("RGBA")
sizes = [(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)]
image.save(desktop, format="ICO", sizes=sizes)
image.save(favicon, format="ICO", sizes=sizes)
'@
  & $python -c $script $sourcePng $icon $favicon
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $icon)) {
    throw "Could not generate the Sonario icon."
  }
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wscript
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $rootPath
$shortcut.IconLocation = $icon + ",0"
$shortcut.Description = "Open Sonario"
$shortcut.Save()

Write-Host ""
Write-Host "[OK] Sonario shortcut created on your desktop." -ForegroundColor Green
Write-Host "     $shortcutPath"

param([string]$Root = $PSScriptRoot)
$ErrorActionPreference = "SilentlyContinue"
$profile = Join-Path $Root ".sonario-browser-profile"
$pidFile = Join-Path $Root ".sonario.pid"

try {
  Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($profile.ToLowerInvariant()) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}

$stopped = $false
if (Test-Path -LiteralPath $pidFile) {
  $serverPid = 0
  try { $serverPid = [int](Get-Content -LiteralPath $pidFile -First 1) } catch {}
  if ($serverPid -gt 0) {
    try { & taskkill.exe /PID $serverPid /T /F | Out-Null; $stopped = $true } catch {}
  }
}

if (-not $stopped) {
  try {
    $line = netstat -ano | Select-String ":5005\s+.*LISTENING" | Select-Object -First 1
    if ($line -and ($line.ToString() -match "\s(\d+)\s*$")) {
      $portPid = [int]$Matches[1]
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$portPid"
      if ($proc.CommandLine -match "app\.py") {
        & taskkill.exe /PID $portPid /T /F | Out-Null
        $stopped = $true
      }
    }
  } catch {}
}

Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $Root ".sonario.browser.pid") -Force -ErrorAction SilentlyContinue
if ($stopped) { Write-Host "Sonario stopped." } else { Write-Host "Sonario was not running." }

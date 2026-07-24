param(
  [string]$Url = "http://127.0.0.1:5005",
  [string]$Root = $PSScriptRoot,
  [int]$Port = 5005
)

$ErrorActionPreference = "SilentlyContinue"
$profile = Join-Path $Root ".sonario-browser-profile"
$pidFile = Join-Path $Root ".sonario.pid"
$browserPidFile = Join-Path $Root ".sonario.browser.pid"

function Find-Browser {
  $candidates = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
  )
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
  }
  return $null
}

function Initialize-PrivateProfile {
  New-Item -ItemType Directory -Force -Path $profile | Out-Null
  # This profile belongs only to Sonario. These preferences and launch flags
  # suppress browser account sign-in, password saving, and browser sync.
  $default = Join-Path $profile "Default"
  New-Item -ItemType Directory -Force -Path $default | Out-Null
  $preferences = Join-Path $default "Preferences"
  if (-not (Test-Path -LiteralPath $preferences)) {
    $json = @{
      browser = @{ check_default_browser = $false }
      credentials_enable_service = $false
      credentials_enable_autosignin = $false
      signin = @{ allowed = $false }
      sync = @{ suppress_start = $true }
      profile = @{ password_manager_enabled = $false }
    } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($preferences, $json, [System.Text.UTF8Encoding]::new($false))
  }
  New-Item -ItemType File -Force -Path (Join-Path $profile "First Run") | Out-Null
}

function Get-SonarioBackendPids {
  param([int]$ListenerPort)

  # Capture the exact process already listening for Sonario before opening the
  # browser. Closing X stops only these recorded PIDs, never a later process
  # that happens to reuse port 5005.
  $ids = [System.Collections.Generic.HashSet[int]]::new()

  try {
    Get-NetTCPConnection -LocalPort $ListenerPort -State Listen -ErrorAction Stop |
      ForEach-Object {
        if ($_.OwningProcess -gt 0) {
          [void]$ids.Add([int]$_.OwningProcess)
        }
      }
  } catch {}

  # Fallback for systems where Get-NetTCPConnection is unavailable/restricted.
  if ($ids.Count -eq 0) {
    try {
      $escapedPort = [regex]::Escape([string]$ListenerPort)
      $pattern = "^\s*TCP\s+\S+:$escapedPort\s+\S+\s+LISTENING\s+(\d+)\s*$"
      foreach ($line in (& netstat.exe -ano -p tcp 2>$null)) {
        if ($line -match $pattern) {
          [void]$ids.Add([int]$Matches[1])
        }
      }
    } catch {}
  }

  return @($ids)
}

function Stop-SonarioBackend {
  param([int[]]$ProcessIds)

  foreach ($backendProcessId in $ProcessIds) {
    if ($backendProcessId -le 0 -or $backendProcessId -eq $PID) { continue }
    try {
      Get-Process -Id $backendProcessId -ErrorAction Stop | Out-Null
      & taskkill.exe /PID $backendProcessId /T /F | Out-Null
      try { Wait-Process -Id $backendProcessId -Timeout 5 -ErrorAction SilentlyContinue } catch {}
    } catch {}
  }

  # PID-file fallback if listener discovery was unavailable. The launcher wrote
  # this exact PID after starting Sonario, so this remains process-specific.
  if (($ProcessIds | Measure-Object).Count -eq 0 -and (Test-Path -LiteralPath $pidFile)) {
    $serverPid = 0
    try { $serverPid = [int](Get-Content -LiteralPath $pidFile -First 1) } catch {}
    if ($serverPid -gt 0 -and $serverPid -ne $PID) {
      try { & taskkill.exe /PID $serverPid /T /F | Out-Null } catch {}
    }
  }

  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

function Maximize-SonarioWindow {
  param(
    [System.Diagnostics.Process]$InitialProcess,
    [string]$BrowserPath,
    [datetime]$LaunchTime
  )

  try {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class SonarioNativeWindow {
  [DllImport("user32.dll")]
  public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern bool IsWindow(IntPtr hWnd);
}
"@
  } catch {}

  $browserName = [System.IO.Path]::GetFileNameWithoutExtension($BrowserPath)
  $chosen = $null

  # Chromium may hand the app window to a child process. Wait for the newest
  # visible process created by this launch rather than an ordinary browser window.
  for ($attempt = 0; $attempt -lt 80; $attempt++) {
    Start-Sleep -Milliseconds 250
    $visible = @(
      Get-Process -Name $browserName -ErrorAction SilentlyContinue |
      Where-Object {
        $_.MainWindowHandle -ne 0 -and
        $_.StartTime -ge $LaunchTime.AddSeconds(-5)
      } |
      Sort-Object StartTime -Descending
    )

    if ($visible.Count -gt 0) {
      $chosen = $visible[0]
      break
    }

    try {
      $InitialProcess.Refresh()
      if ($InitialProcess.MainWindowHandle -ne 0) {
        $chosen = $InitialProcess
        break
      }
    } catch {}
  }

  if ($chosen -and $chosen.MainWindowHandle -ne 0) {
    try {
      # SW_MAXIMIZE = 3. Repeat because Chromium can restore remembered sizing
      # immediately after the first frame.
      for ($pass = 0; $pass -lt 5; $pass++) {
        [SonarioNativeWindow]::ShowWindowAsync($chosen.MainWindowHandle, 3) | Out-Null
        [SonarioNativeWindow]::SetForegroundWindow($chosen.MainWindowHandle) | Out-Null
        Start-Sleep -Milliseconds 300
        try { $chosen.Refresh() } catch {}
      }
    } catch {}
    return $chosen
  }

  return $InitialProcess
}

function Wait-SonarioWindowClose {
  param(
    [IntPtr]$WindowHandle,
    [System.Diagnostics.Process]$WindowProcess,
    [int]$PollMilliseconds = 250
  )

  # Chrome/Edge may keep their process alive after an app-mode window closes.
  # Watch the exact native window handle, matching Parroty's reliable X-close fix.
  if ($WindowHandle -ne [IntPtr]::Zero) {
    while ($true) {
      $windowStillExists = $false
      try { $windowStillExists = [SonarioNativeWindow]::IsWindow($WindowHandle) } catch {}
      if (-not $windowStillExists) { break }
      Start-Sleep -Milliseconds ([Math]::Max(10, $PollMilliseconds))
    }
    return
  }

  # Last-resort fallback if Chromium never exposed a usable native handle.
  try { $WindowProcess.WaitForExit() } catch {}
}

function Stop-ProfileProcesses {
  try {
    Get-CimInstance Win32_Process |
      Where-Object { $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($profile.ToLowerInvariant()) } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  } catch {}
}

$browser = Find-Browser
if (-not $browser) {
  Add-Type -AssemblyName PresentationFramework
  [System.Windows.MessageBox]::Show("Microsoft Edge or Google Chrome was not found.", "Sonario") | Out-Null
  Stop-SonarioBackend -ProcessIds @(Get-SonarioBackendPids -ListenerPort $Port)
  exit 1
}

# The launcher has already verified that this listener is Sonario. Record its
# exact backend PID before starting Chromium so X can stop the right process.
$backendPids = @(Get-SonarioBackendPids -ListenerPort $Port)

Initialize-PrivateProfile
$args = @(
  "--app=$Url",
  "--user-data-dir=`"$profile`"",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-background-mode",
  "--disable-sync",
  "--disable-signin-promo",
  "--disable-session-crashed-bubble",
  "--disable-features=SigninIntercept,AccountConsistency,EnableDiceSupport,ChromeSignin,EdgeSignIn,msEdgeSignIn",
  "--start-maximized",
  "--window-position=0,0"
)

$launchTime = Get-Date
$process = Start-Process -FilePath $browser -ArgumentList $args -PassThru
if (-not $process) {
  Stop-SonarioBackend -ProcessIds $backendPids
  exit 1
}

$windowProcess = Maximize-SonarioWindow -InitialProcess $process -BrowserPath $browser -LaunchTime $launchTime
$windowHandle = [IntPtr]$windowProcess.MainWindowHandle
Set-Content -LiteralPath $browserPidFile -Value $windowProcess.Id

# Closing the actual Sonario app window with X is treated exactly like stop.bat,
# even when Chromium keeps a background process alive.
Wait-SonarioWindowClose -WindowHandle $windowHandle -WindowProcess $windowProcess
Remove-Item -LiteralPath $browserPidFile -Force -ErrorAction SilentlyContinue
Stop-ProfileProcesses
Stop-SonarioBackend -ProcessIds $backendPids

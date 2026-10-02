# Creates a "nipulate" desktop shortcut that starts the server and opens the PC page.
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
  Write-Error "No .venv found. Run scripts\setup.bat first."
  exit 1
}
$path = Join-Path ([Environment]::GetFolderPath("Desktop")) "nipulate.lnk"
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "-m nipulate.launcher"
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = (Join-Path $root "nipulate\static\nipulate.ico") + ",0"
$shortcut.Description = "Start nipulate and open the PC page"
$shortcut.Save()
Write-Host "Created $path"

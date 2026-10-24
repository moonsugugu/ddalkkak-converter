$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$appVersion = & '.\.venv\Scripts\python.exe' -c 'from product import VERSION; print(VERSION)'
$setupPath = Join-Path $PSScriptRoot "dist\DdalKkak-Setup-$appVersion.exe"
if (-not (Test-Path -LiteralPath $setupPath)) { throw 'Run build.ps1 first.' }
$setupProcess = Start-Process -FilePath $setupPath -ArgumentList '/S' -WindowStyle Hidden -Wait -PassThru
if ($setupProcess.ExitCode -ne 0) { throw "Installation failed with exit code $($setupProcess.ExitCode)." }
$installedApp = Join-Path $env:LOCALAPPDATA 'Programs\DocQ\DdalKkak.exe'
Start-Process -FilePath $installedApp -ArgumentList '--background' -WindowStyle Hidden
Write-Output $installedApp

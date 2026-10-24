$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$docqPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $docqPython -m unittest -v
if ($LASTEXITCODE -ne 0) { throw 'Conversion tests failed.' }
& $docqPython -c "from app import icon_image; icon_image().save('vendor/docq.ico', sizes=[(16,16),(32,32),(48,48),(128,128),(256,256)])"
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
& $docqPython build_com.py
if ($LASTEXITCODE -ne 0) { throw 'HWP COM interface generation failed.' }
& $docqPython -m PyInstaller --noconfirm --clean --onefile --windowed --name DdalKkak --icon vendor/docq.ico --version-file version-info.txt --add-data 'vendor;vendor' --add-data 'ocr.ps1;.' --collect-submodules comtypes.gen --hidden-import win32timezone --exclude-module matplotlib --exclude-module scipy --exclude-module pandas --exclude-module pytest --exclude-module IPython app.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
$buildVersion = & $docqPython -c 'from product import VERSION; print(VERSION)'
& $docqPython build_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License notice generation failed.' }
$buildTools = Join-Path $PSScriptRoot 'dist\tools'
New-Item -ItemType Directory -Force -Path $buildTools | Out-Null
$ffmpegBuild = & $docqPython -c 'from media import executable; from pathlib import Path; print(Path(executable()).parent)'
Copy-Item -LiteralPath (Join-Path $ffmpegBuild 'ffmpeg.exe') -Destination $buildTools -Force
Copy-Item -LiteralPath (Join-Path $ffmpegBuild 'ffprobe.exe') -Destination $buildTools -Force
Copy-Item -LiteralPath (Join-Path (Split-Path $ffmpegBuild) 'LICENSE') -Destination (Join-Path $buildTools 'FFmpeg-LICENSE.txt') -Force
Copy-Item -LiteralPath 'FFmpeg-SOURCE.txt' -Destination $buildTools -Force
$nsisCompiler = Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'electron-builder\Cache\nsis-3.0.4.1') -Filter makensis.exe -Recurse | Where-Object { $_.Directory.Name -like 'nsis-*' } | Select-Object -First 1
if (-not $nsisCompiler) { throw 'NSIS 3 makensis.exe not found.' }
& $nsisCompiler.FullName /V2 "/DVERSION=$buildVersion" installer.nsi
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
& $docqPython release_manifest.py
if ($LASTEXITCODE -ne 0) { throw 'Release metadata generation failed.' }

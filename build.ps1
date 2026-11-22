# Builds the Windows app and its installer.
#   1. Nuitka compiles app.py and everything it uses into  build\app.dist\HammerSlip.exe
#   2. Inno Setup wraps that folder into  dist\HammerSlip-Setup-<version>.exe
#
# GitHub runs this automatically (see .github\workflows\build.yml). To build on your own PC instead:
#   pip install -r requirements.txt nuitka   (and install Inno Setup 6)
#   powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = (python -c "import paths; print(paths.VERSION)").Trim()
Write-Host "Building HammerSlip $version"

python -m nuitka app.py `
  --standalone `
  --assume-yes-for-downloads `
  --enable-plugin=tk-inter `
  --windows-console-mode=disable `
  --windows-icon-from-ico=icon.ico `
  --include-data-files=config.json=config.json `
  --include-data-files=icon.ico=icon.ico `
  --output-dir=build `
  --output-filename="HammerSlip.exe" `
  --product-name="HammerSlip" `
  --file-description="HammerSlip" `
  --product-version=$version `
  --file-version=$version
if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed" }

$iscc = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found" }

# Test builds (from a branch other than main) get a suffix like "-TEST-new-feature".
$suffix = ($env:INSTALLER_SUFFIX -replace '[^A-Za-z0-9._-]', '-')
& $iscc "/DAppVersion=$version" "/DSuffix=$suffix" "installer\setup.iss"
if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }

Get-ChildItem dist

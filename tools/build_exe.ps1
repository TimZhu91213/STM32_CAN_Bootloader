# Build CAN Bootloader GUI as a Windows folder distribution (onedir).
# Output: tools/dist/CANBootloaderFlasher/

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$hex2bin = Join-Path $PSScriptRoot "..\Hex2bin-2.5\bin\Release\hex2bin.exe"
if (-not (Test-Path $hex2bin)) {
    Write-Error "hex2bin.exe not found: $hex2bin"
}

Write-Host "Installing build dependencies..."
python -m pip install -r requirements.txt pyinstaller --quiet

Write-Host "Running PyInstaller..."
python -m PyInstaller CANBootloaderFlasher.spec --noconfirm --clean

$outDir = Join-Path $PSScriptRoot "dist\CANBootloaderFlasher"
$exe = Join-Path $outDir "CANBootloaderFlasher.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Build failed: $exe not found"
}

# Ensure hex2bin sits beside the main exe (PyInstaller may place it in _internal).
$destHex = Join-Path $outDir "hex2bin.exe"
if (-not (Test-Path $destHex)) {
    Copy-Item $hex2bin $destHex -Force
}

Write-Host ""
Write-Host "Done. Run:" -ForegroundColor Green
Write-Host "  $exe"

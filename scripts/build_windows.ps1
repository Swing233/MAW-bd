param(
  [Parameter(Mandatory=$true)][string]$FFmpegZip,
  [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if ($env:OS -ne 'Windows_NT') { throw 'This build must run on Windows x64.' }
Set-Location (Split-Path -Parent $PSScriptRoot)
$FFmpegZip = (Resolve-Path $FFmpegZip).Path
function Run-UV {
  & uv @args
  if ($LASTEXITCODE -ne 0) { throw "uv failed with exit code $LASTEXITCODE" }
}
Run-UV sync --frozen --group build --group dev
if (-not $SkipTests) {
  Run-UV run --no-sync python -m unittest discover -s tests -p 'test_*.py'
  Run-UV run --no-sync ruff check
}
Run-UV run --no-sync python edit.py --blank
Run-UV run --no-sync pyinstaller MAW.spec --noconfirm --distpath dist/windows --workpath build/windows
$App = Join-Path (Get-Location) 'dist/windows/MAW-bd'
if (-not (Test-Path "$App/MAW-bd.exe")) { throw 'Missing Windows executable.' }
$Unpack = Join-Path $env:TEMP ('maw-ffmpeg-' + [guid]::NewGuid())
try {
  Expand-Archive -LiteralPath $FFmpegZip -DestinationPath $Unpack
  $FFmpeg = Get-ChildItem $Unpack -Recurse -File -Filter ffmpeg.exe | Select-Object -First 1
  if (-not $FFmpeg) { throw 'FFmpeg archive has no ffmpeg.exe.' }
  $Vendor = Split-Path -Parent (Split-Path -Parent $FFmpeg.FullName)
  New-Item -ItemType Directory -Force "$App/ffmpeg/bin" | Out-Null
  Copy-Item "$($FFmpeg.DirectoryName)/ffmpeg.exe","$($FFmpeg.DirectoryName)/ffprobe.exe" "$App/ffmpeg/bin/"
  Get-ChildItem $Vendor -File | Where-Object { $_.Name -match '^(LICENSE|COPYING|README)' } | Copy-Item -Destination "$App/ffmpeg/"
  if (-not (Get-ChildItem "$App/ffmpeg" -File | Where-Object { $_.Name -match '^(LICENSE|COPYING)' })) { throw 'FFmpeg license missing.' }
} finally { Remove-Item $Unpack -Recurse -Force -ErrorAction SilentlyContinue }
Copy-Item LICENSE,THIRD_PARTY_NOTICES.md,docs/WINDOWS_GUIDE.md $App
Run-UV run --no-sync python scripts/smoke_windows_bundle.py $App
$Version = (Get-Content pyproject.toml | Select-String '^version = "([^"]+)"').Matches.Groups[1].Value
New-Item -ItemType Directory -Force dist/releases | Out-Null
$Zip = Join-Path (Get-Location) "dist/releases/MAW-bd-$Version-Windows-x64.zip"
Compress-Archive -Path $App -DestinationPath $Zip -Force
Write-Host "Windows portable package: $Zip"

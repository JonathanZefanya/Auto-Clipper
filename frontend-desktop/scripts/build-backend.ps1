# F-20: build bundel backend Python untuk aplikasi desktop.
#   1. build UI (frontend/dist) — ikut dibundel & disajikan backend
#   2. PyInstaller onedir → backend/dist/autoclip-backend/
#   3. salin FFmpeg/FFprobe (+ Deno bila ada) ke backend/dist/autoclip-backend/bin (didahulukan di PATH oleh Tauri)
$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$backend = Join-Path $repo "backend"
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv backend tidak ada: $py (lihat README: pip install -e `".[dev,cuda,desktop]`")" }

Write-Host "== 1/3 build UI (frontend)"
npm --prefix (Join-Path $repo "frontend") run build
if ($LASTEXITCODE) { throw "build frontend gagal" }

Write-Host "== 2/3 PyInstaller"
& $py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE) { throw "PyInstaller belum terpasang. Jalankan: $py -m pip install -e `"$backend[desktop]`"" }
Push-Location $backend
try {
  & $py -m PyInstaller packaging\autoclip-backend.spec --noconfirm --clean --distpath dist --workpath build
  if ($LASTEXITCODE) { throw "PyInstaller gagal" }
} finally { Pop-Location }

Write-Host "== 3/3 salin FFmpeg/FFprobe/Deno"
$out = Join-Path $backend "dist\autoclip-backend"
$bin = Join-Path $out "bin"
New-Item -ItemType Directory -Force $bin | Out-Null
foreach ($tool in @("ffmpeg", "ffprobe", "deno")) {
  $cmd = Get-Command $tool -ErrorAction SilentlyContinue
  if (-not $cmd) {
    if ($tool -eq "deno") { Write-Host "  (deno tidak ditemukan — dilewati; yt-dlp tetap jalan dengan format terbatas)"; continue }
    throw "$tool tidak ditemukan di PATH (winget install Gyan.FFmpeg)"
  }
  $src = Get-Item $cmd.Source
  if ($src.LinkType -and $src.Target) { $src = Get-Item ($src.Target | Select-Object -First 1) }  # winget memasang symlink
  Copy-Item $src.FullName (Join-Path $bin "$tool.exe") -Force
  Write-Host "  $tool → bin\$tool.exe"
}

$size = (Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1GB
Write-Host ("Selesai: {0} ({1:N2} GB)" -f $out, $size)

# Auto Clipper — aplikasi desktop (Tauri v2)

Shell desktop untuk Auto Clipper. **UI-nya sama dengan versi web** (`../frontend`), backend Python
dibundel dengan PyInstaller dan dijalankan otomatis oleh aplikasi.

```
buka aplikasi → splash → backend (127.0.0.1, port bebas) → /api/health OK → jendela memuat http://127.0.0.1:<port>/
tutup aplikasi → backend + proses anaknya (FFmpeg) dihentikan
```

| Bagian | Lokasi |
|---|---|
| Shell Rust (spawn/health/stop backend, single instance) | `src-tauri/src/lib.rs` |
| Splash (status & error + lokasi log) | `splash/index.html` |
| Konfigurasi dev / tambahan untuk installer | `src-tauri/tauri.conf.json` / `src-tauri/tauri.bundle.conf.json` |
| Bundel backend (UI + FFmpeg/FFprobe/Deno ikut) | `scripts/build-backend.ps1`, `../backend/packaging/autoclip-backend.spec` |
| Ikon (Pillow, tanpa Tauri CLI) | `scripts/make_icons.py` → `src-tauri/icons/` |

## Prasyarat (sekali)

```powershell
winget install Rustlang.Rustup                       # lalu buka ulang terminal
winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
# WebView2 sudah ada di Windows 11
cd frontend-desktop
npm install                                          # Tauri CLI
..\backend\.venv\Scripts\python.exe -m pip install -e "..\backend[desktop]"   # PyInstaller (untuk build installer)
```

## Menjalankan

```powershell
npm run dev      # build UI, lalu jendela desktop memakai backend/.venv + folder data/ repo
npm run build    # bundel backend (PyInstaller) + installer NSIS → src-tauri/target/release/bundle/nsis/
npm run icons    # buat ulang ikon
```

## Catatan

- **Data job** versi terpasang ada di `%APPDATA%\dev.autoclip.desktop\data` (bukan folder instalasi);
  log backend di `%LOCALAPPDATA%\dev.autoclip.desktop\logs\backend.log`.
- **Tidak dibundel**: model Whisper (diunduh saat transkripsi pertama), model MediaPipe (`data/models/`),
  dan Ollama (aplikasi terpisah, opsional — tanpa Ollama saran judul memakai metode sederhana).
- Bundel backend besar (±1–2 GB: CUDA cuBLAS, CTranslate2, MediaPipe, SciPy). Onedir dipakai (bukan onefile)
  agar aplikasi tidak mengekstrak ratusan MB ke `%TEMP%` setiap dibuka.
- UI dimuat dari backend lokal (`http://127.0.0.1`), bukan aset Tauri, sehingga `/api`, SSE, video Range, dan
  unduhan ZIP bekerja tanpa perubahan UI. Halaman itu tidak punya akses IPC Tauri.

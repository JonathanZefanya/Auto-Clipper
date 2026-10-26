# -*- mode: python ; coding: utf-8 -*-
# F-20: bundel backend Python untuk aplikasi desktop (Tauri) — PyInstaller onedir.
#   cd backend
#   .\.venv\Scripts\python.exe -m PyInstaller packaging\autoclip-backend.spec --noconfirm
# Hasil: backend\dist\autoclip-backend\autoclip-backend.exe (+ _internal\)
# Onedir (bukan onefile) agar start cepat: onefile mengekstrak ratusan MB ke %TEMP% setiap kali dibuka.
import glob
import os
import site

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))          # backend/
REPO = os.path.abspath(os.path.join(ROOT, ".."))               # repo
FRONTEND_DIST = os.path.join(REPO, "frontend", "dist")
if not os.path.isfile(os.path.join(FRONTEND_DIST, "index.html")):
    raise SystemExit("frontend/dist belum ada — jalankan `npm run build` di folder frontend dulu.")

datas = [(FRONTEND_DIST, "frontend_dist")]
binaries = []
hiddenimports = []

# Paket yang memuat file data / DLL / modul dinamis saat runtime
for pkg in ("librosa", "mediapipe", "faster_whisper", "ctranslate2", "onnxruntime", "yt_dlp",
            "soundfile", "certifi"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("uvicorn") + collect_submodules("app") + collect_submodules("clipper")

# cuBLAS dari pip (extra [cuda]) → <bundle>/nvidia/<lib>/bin (dicari oleh subtitle._register_cuda_dlls)
for sp in site.getsitepackages():
    for dll in glob.glob(os.path.join(sp, "nvidia", "*", "bin", "*.dll")):
        lib = os.path.basename(os.path.dirname(os.path.dirname(dll)))
        binaries.append((dll, os.path.join("nvidia", lib, "bin")))

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="autoclip-backend",
    console=True,           # jendela disembunyikan oleh Tauri (CREATE_NO_WINDOW); stdout → file log
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="autoclip-backend", upx=False)

"""Entry point backend untuk aplikasi desktop (F-20, PyInstaller).

Dijalankan oleh shell Tauri: `autoclip-backend.exe serve --host 127.0.0.1 --port <N>`.
Argumen lain diteruskan ke CLI `clipper` (detect/render/titles juga bisa dipakai dari bundel).
"""
import multiprocessing
import sys

from clipper.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

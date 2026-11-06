"""Build dist/ByteBroom.exe (single file, no console) with PyInstaller.

Usage:  pip install -e ".[dev]"
        python scripts/build_exe.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "bytebroom"

# Heavy packages ByteBroom never uses. PyInstaller can drag them in from a busy global
# Python install; excluding them keeps the exe small. (A clean venv avoids this too.)
EXCLUDE = ["numpy", "PIL", "pygame", "cv2", "matplotlib", "pandas", "scipy", "torch",
           "IPython", "jedi", "pytest", "setuptools", "pkg_resources"]


def main() -> None:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        sys.exit('PyInstaller is missing. Run:  pip install -e ".[dev]"')

    icon = PKG / "assets" / "bytebroom.ico"
    pyinstaller.run([
        str(PKG / "__main__.py"),
        "--name", "ByteBroom",
        "--onefile", "--windowed", "--noconfirm", "--clean",
        "--paths", str(ROOT / "src"),
        "--icon", str(icon),
        "--add-data", f"{PKG / 'assets'}{os.pathsep}bytebroom/assets",
        "--collect-data", "customtkinter",  # themes + fonts
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        *(arg for mod in EXCLUDE for arg in ("--exclude-module", mod)),
    ])
    print(f"\nBuilt: {ROOT / 'dist' / 'ByteBroom.exe'}")


if __name__ == "__main__":
    main()

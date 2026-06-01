#!/usr/bin/env python3
"""
Build Pokepad into a standalone desktop app for the current OS.

Usage
-----
    python scripts/build.py          # build
    python scripts/build.py --clean  # wipe build/ and dist/ first, then build

Output
------
    macOS  : dist/Pokepad.app
    Windows: dist/Pokepad.exe

Requirements
------------
    pip install pyinstaller
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(*cmd: str) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    result = subprocess.run(list(cmd), cwd=ROOT)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    if "--clean" in sys.argv:
        for d in ("build", "dist"):
            target = ROOT / d
            if target.exists():
                print(f"  Removing {target}")
                shutil.rmtree(target)

    if not shutil.which("pyinstaller"):
        sys.exit(
            "\npyinstaller not found.\n"
            "Install it first:  pip install pyinstaller\n"
        )

    _run(sys.executable, "-m", "PyInstaller", "--noconfirm", "pokepad.spec")

    expected = (
        ROOT / "dist" / "Pokepad.app"
        if sys.platform == "darwin"
        else ROOT / "dist" / "Pokepad.exe"
    )

    if expected.exists():
        print(f"\n  Build succeeded  →  {expected}\n")
    else:
        print(f"\n  WARNING: expected output not found at {expected}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

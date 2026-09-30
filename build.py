"""Build the Windows distribution with PyInstaller.

Usage:
    python build.py
    python build.py --no-clean
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_ROOT / "build.spec"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"


def remove_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Digital Twin Finland with PyInstaller")
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep existing build and dist directories before packaging",
    )
    args = parser.parse_args()

    if not SPEC_FILE.exists():
        print(f"Missing spec file: {SPEC_FILE}", file=sys.stderr)
        return 1

    dist_path = DIST_DIR
    if not args.no_clean:
        remove_directory(BUILD_DIR)
        try:
            remove_directory(DIST_DIR)
        except (PermissionError, OSError) as error:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dist_path = PROJECT_ROOT / f"dist_build_{timestamp}"
            print(
                f"Could not remove {DIST_DIR} because it is locked: {error}\n"
                f"Building into {dist_path} instead.",
                file=sys.stderr,
            )

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_path),
        str(SPEC_FILE),
    ]
    print("Running:", " ".join(f'"{part}"' if " " in part else part for part in command))

    result = subprocess.run(command, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        return result.returncode

    executable = dist_path / "DigitalTwinFinland" / "DigitalTwinFinland.exe"
    if not executable.exists():
        print(f"Build completed but executable was not found: {executable}", file=sys.stderr)
        return 1

    print(f"Build complete: {executable}")
    print("Keep .env beside the executable when deploying.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

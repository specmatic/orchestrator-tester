#!/usr/bin/env python3

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "Main.java"
BUILD_DIR = ROOT / "build"
CLASSES_DIR = BUILD_DIR / "classes"
JAR_PATH = BUILD_DIR / "orchestrator-tester.jar"
MAIN_CLASS = "com.specmatic.orchestratortester.Main"


def main() -> int:
    javac = shutil.which("javac")
    jar = shutil.which("jar")
    if not javac or not jar:
        raise SystemExit("javac and jar must be available on PATH")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if CLASSES_DIR.exists():
        shutil.rmtree(CLASSES_DIR)
    CLASSES_DIR.mkdir(parents=True, exist_ok=True)

    subprocess.run([javac, "-d", str(CLASSES_DIR), str(SRC)], check=True)
    manifest = BUILD_DIR / "MANIFEST.MF"
    manifest.write_text(f"Main-Class: {MAIN_CLASS}\n", encoding="utf-8")

    if JAR_PATH.exists():
        JAR_PATH.unlink()

    subprocess.run([jar, "cfm", str(JAR_PATH), str(manifest), "-C", str(CLASSES_DIR), "."], check=True)
    print(JAR_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

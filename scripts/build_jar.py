#!/usr/bin/env python3

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "Main.java"
BUILD_DIR = Path(os.environ.get("ORCHESTRATOR_TESTER_BUILD_DIR", str(ROOT / "build")))
JAR_PATH = BUILD_DIR / "orchestrator-tester.jar"
MAIN_CLASS = "com.specmatic.orchestratortester.Main"


def main() -> int:
    javac = shutil.which("javac")
    jar = shutil.which("jar")
    if not javac or not jar:
        raise SystemExit("javac and jar must be available on PATH")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="orchestrator-tester-classes-") as classes_dir:
        subprocess.run([javac, "-d", classes_dir, str(SRC)], check=True)
        subprocess.run([jar, "cfe", str(JAR_PATH), MAIN_CLASS, "-C", classes_dir, "."], check=True)
    print(JAR_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

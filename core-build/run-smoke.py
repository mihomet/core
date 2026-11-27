#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    root = Path(sys.argv[1])
    adb = str(Path(os.environ["ANDROID_HOME"]) / "platform-tools/adb")
    for filename in ("app-x86_64-debug.apk", "app-debug-androidTest.apk"):
        candidates = list(root.rglob(filename))
        if len(candidates) != 1:
            raise ValueError(f"Expected one {filename}; got {candidates}")
        subprocess.run([adb, "install", "-r", str(candidates[0])], check=True)
    result = subprocess.run([adb, "shell", "am", "instrument", "-w",
        "org.mihomet.app.test/androidx.test.runner.AndroidJUnitRunner"], text=True, capture_output=True, check=True)
    output = result.stdout + result.stderr
    Path("core-smoke.log").write_text(output)
    print(output)
    if "OK (" not in output or any(marker in output for marker in ("FAILURES!!!", "INSTRUMENTATION_FAILED", "Process crashed")):
        raise SystemExit("Android core smoke tests failed")

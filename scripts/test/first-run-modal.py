#!/usr/bin/env python3
"""Mac AppKit regression: modal disk creation must receive main-queue results.

The second build deliberately uses the previous scheduling implementation. It
must fail, so this check verifies the original deadlock as well as the fix.
Requires an interactive macOS WindowServer; no VM, download or account used.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
environment = {**os.environ, "DEVELOPER_DIR": os.environ.get("DEVELOPER_DIR", "/Library/Developer/CommandLineTools")}
with tempfile.TemporaryDirectory(prefix="steamac-modal-") as tmp:
    tmp = Path(tmp)
    old = tmp/"old.swift"
    old.write_text("""import Foundation
enum FirstRunScheduling {
    static func schedule(_ body: @escaping @Sendable () -> Void) {
        DispatchQueue.main.async(execute: body)
    }
}
""")
    results = []
    for name, implementation, expected in (
        ("fixed", ROOT/"host/launcher/Sources/steamac-vm/FirstRunScheduling.swift", 0),
        ("previous", old, 1),
    ):
        executable = tmp/name
        subprocess.run(["swiftc", "-swift-version", "5", "-parse-as-library", str(implementation),
                        str(ROOT/"scripts/test/first-run-modal.swift"), "-o", str(executable)],
                       env=environment, check=True)
        try:
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=12)
        except subprocess.TimeoutExpired:
            # A nested modal can also stall its run-loop timer in the broken
            # implementation. The parent process still bounds that deadlock.
            if name != "previous":
                raise
            results.append({"implementation": name, "timed_out": True,
                            "output": "first-run-modal: FAIL (negative control blocked)"})
            continue
        results.append({"implementation": name, "exit_code": result.returncode, "output": result.stdout.strip()})
        assert result.returncode == expected, results[-1]
    print(json.dumps(results, ensure_ascii=False))

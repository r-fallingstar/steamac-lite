#!/usr/bin/env python3
"""Validate the pinned redistributable runtime before placing it in an app."""
import hashlib
import json
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[2]/"fex-eac/runtime"
receipt = json.loads((root/"manifest.json").read_text())
assert receipt["commit"] == "6effd2384085818345ec32e6abb4181c7135a9a7"
assert receipt["tag"] == "eac-2610.5"
archive = root/receipt["archive"]
assert hashlib.sha256(archive.read_bytes()).hexdigest() == receipt["sha256"]
with tarfile.open(archive) as tar:
    for name, digest in receipt["files"].items():
        member = tar.getmember("stage/"+name)
        assert member.isfile() and hashlib.sha256(tar.extractfile(member).read()).hexdigest() == digest, name
    for member in tar.getmembers():
        if member.name.startswith("licenses/") and member.isfile():
            assert (root/member.name).read_bytes() == tar.extractfile(member).read(), member.name
assert (root/"licenses/LICENSE").is_file()
print("fex-runtime: pinned commit, archive, 10 runtime files and licenses PASS")

#!/usr/bin/python3
"""Prepare an independent, reflink-only camera Proton snapshot before Steam starts.

Installed Proton is read-only input. A published tool is never updated in place:
its receipt validates the private snapshot even after Steam updates the source.
All entry points accept paths/callbacks so tests need neither Steam nor Btrfs.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
NAME = "steamac_camera"
DIRECTORY = "steamac-camera"
RECEIPT = ".steamac-camera.json"
MAPPING = ("InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping", "438100")
PE = "files/lib/wine/x86_64-windows/qcap.dll"
UNIX = "files/lib/wine/x86_64-unix/qcap.so"
PINS = {"version": "stock_version_sha256", PE: "stock_pe_sha256", UNIX: "stock_unix_sha256"}
CORE = ("version", PE, UNIX, "proton", "toolmanifest.vdf", "compatibilitytool.vdf")
DESCRIPTOR = '''"compatibilitytools"
{
    "compat_tools"
    {
        "steamac_camera"
        {
            "install_path" "."
            "display_name" "Proton Experimental (steamac Camera)"
            "from_oslist" "windows"
            "to_oslist" "linux"
        }
    }
}
'''


def log(message):
    print("camera-proton: " + message, file=sys.stderr)


def digest(path):
    with path.open("rb") as stream:
        # Also works on the guest's Python versions without hashlib.file_digest.
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
        return result.hexdigest()


def helpers():
    return runpy.run_path("/usr/lib/steamac/steam-title-defaults")


def processes_busy():
    try:
        result = subprocess.run(
            ["pgrep", "-i", "-x", "steam|steamwebhelper|FEX.*|wine.*|proton.*"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return result.returncode != 1  # Failure to inspect is not permission to write.
    except OSError:
        return True


def clone_reflink(source, destination):
    """No copy fallback, hardlinks, mounts, or writes through the installed tree."""
    if source.stat().st_dev != destination.stat().st_dev:
        raise ValueError("stock Proton and private staging are on different filesystems")
    try:
        subprocess.run(["cp", "-a", "--reflink=always", str(source) + "/.", str(destination)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as error:
        raise ValueError("reflink clone unavailable; no copy fallback") from error


def contained(root, relative):
    path = root / relative
    path.resolve(strict=True).relative_to(root.resolve(strict=True))
    return path


def check_links(root, source=None):
    """Reject escaping symlinks, special files, and accidental source hardlinks.

    cp -a retains symlinks; an absolute link into stock must not turn the private
    tool back into an alias of Steam's installation. Internal relative links work.
    """
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(root, onerror=walk_error):
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(root)
            resolved = contained(root, relative)
            if not (resolved.is_dir() or resolved.is_file()):
                raise ValueError("unsupported Proton file: " + str(relative))
            if source is not None and not path.is_symlink() and path.is_file():
                original = source / relative
                if original.exists() and os.path.samestat(path.stat(), original.stat()):
                    raise ValueError("clone shares a source inode: " + str(relative))


def validate_pins(pins):
    if not isinstance(pins, dict):
        raise ValueError("bundled pins are not an object")
    for key in (*PINS.values(), "patched_pe_sha256"):
        if not isinstance(pins.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", pins[key]):
            raise ValueError("invalid bundled pin: " + key)
    if pins["stock_pe_sha256"] == pins["patched_pe_sha256"]:
        raise ValueError("camera payload is unchanged stock")


def read_pins(bundle):
    pins = json.loads((bundle / "proton-camera.json").read_text())
    validate_pins(pins)
    if digest(contained(bundle, "proton/qcap.dll")) != pins["patched_pe_sha256"]:
        raise ValueError("bundled qcap.dll checksum mismatch")
    return {key: pins[key] for key in (*PINS.values(), "patched_pe_sha256")}


def verify_stock(stock, pins):
    if "x86_64" not in contained(stock, "version").read_text():
        raise ValueError("stock Proton is not x86_64")
    for relative, key in PINS.items():
        if digest(contained(stock, relative)) != pins[key]:
            raise ValueError("unknown stock Proton checksum: " + relative)
    for relative in ("proton", "toolmanifest.vdf"):
        if not contained(stock, relative).is_file():
            raise ValueError("incomplete stock Proton: " + relative)


def valid_snapshot(target):
    """Validate ownership using the snapshot's own receipt, never today's stock."""
    try:
        if target.is_symlink() or not target.is_dir():
            return False
        receipt = json.loads(contained(target, RECEIPT).read_text())
        if receipt["schema"] != 1 or receipt["tool"] != NAME:
            return False
        pins, files = receipt["pins"], receipt["files"]
        validate_pins(pins)
        if set(files) != set(CORE):
            return False
        expected = {"version": pins["stock_version_sha256"], PE: pins["patched_pe_sha256"],
                    UNIX: pins["stock_unix_sha256"]}
        if any(files[key] != checksum for key, checksum in expected.items()):
            return False
        if any(digest(contained(target, key)) != checksum for key, checksum in files.items()):
            return False
        if (target / "compatibilitytool.vdf").read_text() != DESCRIPTOR:
            return False
        check_links(target)
        return True
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False


def ready_tool(steam):
    return valid_snapshot(Path(steam) / "compatibilitytools.d" / DIRECTORY)


def prepare(steam, stock, *, bundle=HERE, vdf=None, clone=clone_reflink,
            is_busy=processes_busy, report=log):
    """Return the managed tool name when ready; failure always leaves stock usable."""
    steam, bundle = Path(steam), Path(bundle)
    tools = steam / "compatibilitytools.d"
    target = tools / DIRECTORY
    try:
        if is_busy():
            report("Steam/FEX/Wine is running; leaving tools unchanged")
            return None
        if stock is not None:
            stock = Path(stock).resolve(strict=True)
            if tools.resolve().is_relative_to(stock) or stock.is_relative_to(tools.resolve()):
                raise ValueError("stock Proton overlaps private tools")
        tools.mkdir(parents=True, exist_ok=True)
        # The lock is outside the tree that will be atomically published.
        with (tools / ".steamac-camera.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                report("another preparation is active; retaining stock")
                return None
            if ready_tool(steam):
                return NAME
            if target.exists() or target.is_symlink():
                raise ValueError("existing private tool has no valid owned receipt; leaving it unchanged")
            if stock is None:
                raise ValueError("fully installed stock Proton not found")
            pins = read_pins(bundle)
            verify_stock(stock, pins)
            vdf = helpers() if vdf is None else vdf
            with tempfile.TemporaryDirectory(prefix=".steamac-camera-stage-", dir=tools) as temporary:
                stage = Path(temporary) / "tool"
                stage.mkdir()
                if stock.stat().st_dev != stage.stat().st_dev:
                    raise ValueError("stock Proton and staging are on different filesystems")
                clone(stock, stage)
                check_links(stage, stock)
                verify_stock(stage, pins)
                # Check source again after cloning; don't publish a concurrent update.
                verify_stock(stock, pins)
                for relative in ("proton", "toolmanifest.vdf"):
                    if digest(contained(stage, relative)) != digest(contained(stock, relative)):
                        raise ValueError("stock changed during clone: " + relative)
                pe = contained(stage, PE)
                # Replace a private directory entry, never write into a source inode.
                fd, temporary_pe = tempfile.mkstemp(prefix=".qcap.dll.", dir=pe.parent)
                os.close(fd)
                replacement = Path(temporary_pe)
                shutil.copyfile(contained(bundle, "proton/qcap.dll"), replacement)
                replacement.chmod(pe.stat().st_mode & 0o777)
                os.replace(replacement, pe)
                vdf["atomic_write"](stage / "compatibilitytool.vdf", DESCRIPTOR)
                files = {relative: digest(contained(stage, relative)) for relative in CORE}
                if files[PE] != pins["patched_pe_sha256"]:
                    raise ValueError("staged camera payload checksum mismatch")
                receipt = {"schema": 1, "tool": NAME, "pins": pins, "files": files}
                vdf["atomic_write"](stage / RECEIPT, json.dumps(receipt, sort_keys=True) + "\n")
                if not valid_snapshot(stage):
                    raise ValueError("staged private snapshot failed validation")
                if is_busy():
                    raise ValueError("Steam/FEX/Wine started during preparation")
                if target.exists() or target.is_symlink():
                    raise ValueError("private tool appeared during preparation")
                os.rename(stage, target)
            report("private camera Proton ready")
            return NAME
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        report("retaining stock Proton: " + str(error))
        return None


def libraries(steam, vdf):
    result = [Path(steam)]
    path = Path(steam) / "steamapps/libraryfolders.vdf"
    if path.exists():
        for key, (value, *_) in vdf["vdf_entries"](path.read_text())[0].items():
            if len(key) == 3 and key[0] == "libraryfolders" and key[1].isdigit() and key[2] == "path":
                library = Path(value)
                if library.is_absolute() and library not in result:
                    result.append(library)
    return result


def installed_stock(steam, vdf):
    for library in libraries(steam, vdf):
        manifest = library / "steamapps/appmanifest_1493710.acf"
        if not manifest.is_file():
            continue
        values, _ = vdf["vdf_entries"](manifest.read_text())
        def get(field):
            return values.get(("appstate", field), (None,))[0]
        directory = get("installdir")
        if (get("stateflags") == "4" and directory and directory not in (".", "..")
                and Path(directory).name == directory):
            stock = library / "steamapps/common" / directory
            if stock.is_dir():
                return stock
    return None


def mapping_name(text, vdf):
    return vdf["vdf_entries"](text)[0].get(tuple(x.lower() for x in (*MAPPING, "name")), (None,))[0]


def auto(steam, *, bundle=HERE, vdf=None, clone=clone_reflink,
         is_busy=processes_busy, report=log):
    """Pre-Steam entry point: preserve custom choices and every localconfig byte."""
    steam = Path(steam)
    try:
        if is_busy():
            report("Steam/FEX/Wine is running; leaving settings unchanged")
            return None
        vdf = helpers() if vdf is None else vdf
        config = steam / "config/config.vdf"
        original = config.read_text()
        name = mapping_name(original, vdf)
        if name not in (None, "", "proton_experimental", NAME):
            report("keeping user-selected VRChat compatibility tool")
            return None
        if name == NAME and not ready_tool(steam):
            report("unowned camera mapping; leaving settings unchanged")
            return None
        stock = installed_stock(steam, vdf)
        if stock is None:
            report("stock Proton download is not ready; leaving settings unchanged")
            return None
        managed = prepare(steam, stock, bundle=bundle, vdf=vdf, clone=clone,
                          is_busy=is_busy, report=report)
        if not managed or is_busy():
            return None
        # Never overwrite a change made since the initial read.
        if config.read_text() != original:
            report("Steam config changed during preparation; leaving mapping unchanged")
            return None
        text = original
        for field, value in (("name", managed), ("config", ""), ("priority", "250")):
            text = vdf["vdf_set"](text, (*MAPPING, field), value)
        if text != original:
            backup = steam / "config/steamac-camera-config-before.vdf"
            if not backup.exists():
                vdf["atomic_write"](backup, original)
            if is_busy() or config.read_text() != original:
                return None
            vdf["atomic_write"](config, text)
        return managed
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        report("leaving Steam settings unchanged: " + str(error))
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auto", action="store_true", required=True,
                        help="prepare and safely select the private tool before Steam starts")
    parser.parse_args()
    steam = Path(os.environ.get("STEAMAC_STEAM_ROOT", str(Path.home() / ".local/share/Steam")))
    auto(steam)
    # Optional preparation must never prevent Steam from starting.


if __name__ == "__main__":
    main()

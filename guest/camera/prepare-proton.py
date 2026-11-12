#!/usr/bin/python3
"""Prepare an independent camera Proton snapshot before Steam starts.

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
BACKUP = ".steamac-camera-backup"
CLEANUP = ".steamac-camera-cleanup.json"
MAPPING = ("InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping", "438100")
PE = "files/lib/wine/x86_64-windows/qcap.dll"
UNIX = "files/lib/wine/x86_64-unix/qcap.so"
PINS = {"version": "stock_version_sha256", PE: "stock_pe_sha256", UNIX: "stock_unix_sha256"}
CORE = ("version", PE, UNIX, "proton", "toolmanifest.vdf", "compatibilitytool.vdf")
VIDEO = tuple("files/lib/x86_64-linux-gnu/" + name for name in (
    "libavcodec.so.58", "libavformat.so.58", "libavfilter.so.7", "libavutil.so.56"))
VIDEO_ANCHOR = (
    b'            # add Steam ffmpeg libraries to path\n'
    b'            prepend_to_env_str(g_session.env, ld_path_var, steam_linux_path + "/ubuntu12_64/video/:" + steam_linux_path + "/ubuntu12_32/video/:" + steam_linux_path + "/steamrtarm64/video/", ":")\n')
VIDEO_PRIORITY = (
    b'            # steamac private codec priority (policy 1)\n'
    b'            prepend_to_env_str(g_session.env, ld_path_var, g_proton.lib_dir + "x86_64-linux-gnu", ":")\n')
RUNTIME_LIMIT = 4 * 1024**3
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


def clone_budget(source, destination, extra=0):
    if source.stat().st_dev != destination.stat().st_dev:
        raise ValueError("stock Proton and private staging are on different filesystems")
    total = sum(path.stat().st_size for path in source.rglob("*")
                if not path.is_symlink() and path.is_file())
    if total + extra > RUNTIME_LIMIT or shutil.disk_usage(destination).free < total + extra + 512 * 1024**2:
        raise ValueError("not enough space for the camera runtime")


def clone_reflink(source, destination):
    """Prefer shared extents; ext4 gets a bounded, independent ordinary copy."""
    clone_budget(source, destination)
    try:
        subprocess.run(["cp", "-a", "--reflink=auto", str(source) + "/.", str(destination)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as error:
        raise ValueError("independent camera runtime copy failed") from error


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
    source_inodes = {(path.stat().st_dev, path.stat().st_ino)
                     for path in source.rglob("*") if path.is_file()} if source is not None else set()
    for directory, dirs, files in os.walk(root, onerror=walk_error):
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(root)
            resolved = contained(root, relative)
            if not (resolved.is_dir() or resolved.is_file()):
                raise ValueError("unsupported Proton file: " + str(relative))
            if source is not None and not path.is_symlink() and path.is_file():
                if (path.stat().st_dev, path.stat().st_ino) in source_inodes:
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


def validate_video(manifest):
    """The receipt embeds this same manifest; no dependency on today's bundle."""
    if (not isinstance(manifest, dict) or set(manifest) != {"schema", "files"}
            or type(manifest["schema"]) is not int or manifest["schema"] != 1):
        raise ValueError("invalid video manifest schema")
    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != set(VIDEO):
        raise ValueError("video manifest must contain exactly the four supported codecs")
    for checksum in files.values():
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("invalid video checksum")


def read_video(bundle):
    path = bundle / "proton-video.json"
    if not path.exists() and not path.is_symlink():
        return None
    manifest = json.loads(contained(bundle, "proton-video.json").read_text())
    validate_video(manifest)
    payloads = [contained(bundle, "proton-video/" + Path(key).name) for key in VIDEO]
    if any(not path.is_file() or path.is_symlink() for path in payloads):
        raise ValueError("video payload must be regular files")
    if sum(path.stat().st_size for path in payloads) > RUNTIME_LIMIT:
        raise ValueError("video payload exceeds runtime size limit")
    for relative, path in zip(VIDEO, payloads):
        if digest(path) != manifest["files"][relative]:
            raise ValueError("bundled video checksum mismatch: " + relative)
    return manifest


def validate_launcher_policy(policy):
    if (not isinstance(policy, dict) or set(policy) != {"schema", "policy_version", "source_sha256"}
            or type(policy["schema"]) is not int or policy["schema"] != 1
            or type(policy["policy_version"]) is not int or policy["policy_version"] != 1
            or not isinstance(policy["source_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", policy["source_sha256"])):
        raise ValueError("invalid video launcher policy")


def read_launcher_policy(bundle):
    path = contained(bundle, "video-launcher.json")
    if path.is_symlink() or not path.is_file():
        raise ValueError("video launcher policy must be a regular file")
    policy = json.loads(path.read_text())
    validate_launcher_policy(policy)
    return policy


def patch_video_launcher(source, policy):
    """Only this exact, pinned launcher may receive the version-1 insertion."""
    validate_launcher_policy(policy)
    if hashlib.sha256(source).hexdigest() != policy["source_sha256"]:
        raise ValueError("unknown video launcher source checksum")
    if source.count(VIDEO_ANCHOR) != 1 or b"# steamac private codec priority" in source:
        raise ValueError("missing or ambiguous Steam video library anchor")
    return source.replace(VIDEO_ANCHOR, VIDEO_ANCHOR + VIDEO_PRIORITY, 1)


def original_video_launcher(patched, launcher):
    """Validate a schema-3 receipt independently of the currently bundled policy."""
    if not isinstance(launcher, dict) or set(launcher) != {"policy", "patched_sha256"}:
        raise ValueError("invalid private launcher receipt")
    validate_launcher_policy(launcher["policy"])
    checksum = launcher["patched_sha256"]
    if (not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            or hashlib.sha256(patched).hexdigest() != checksum
            or patched.count(VIDEO_ANCHOR + VIDEO_PRIORITY) != 1):
        raise ValueError("private launcher checksum or policy mismatch")
    source = patched.replace(VIDEO_ANCHOR + VIDEO_PRIORITY, VIDEO_ANCHOR, 1)
    if patch_video_launcher(source, launcher["policy"]) != patched:
        raise ValueError("private launcher does not match its policy")
    return source


def verify_stock(stock, pins):
    if "x86_64" not in contained(stock, "version").read_text():
        raise ValueError("stock Proton is not x86_64")
    for relative, key in PINS.items():
        if digest(contained(stock, relative)) != pins[key]:
            raise ValueError("unknown stock Proton checksum: " + relative)
    for relative in ("proton", "toolmanifest.vdf"):
        if not contained(stock, relative).is_file():
            raise ValueError("incomplete stock Proton: " + relative)


def snapshot_receipt(target):
    """Validate ownership using the snapshot's own receipt, never today's stock.

    Schema 1 owns CORE only (legacy camera). Schema 2 adds the four codecs.
    Schema 3 also binds the private launcher insertion to its pinned source.
    These hashes detect damage; receipts are local ownership markers, not signed
    attestations of authenticity.
    """
    if target.is_symlink() or not target.is_dir():
        raise ValueError("private tool is not an owned directory")
    receipt = json.loads(contained(target, RECEIPT).read_text())
    if (not isinstance(receipt, dict) or type(receipt.get("schema")) is not int
            or receipt["schema"] not in (1, 2, 3) or receipt.get("tool") != NAME):
        raise ValueError("invalid private receipt identity")
    pins, files = receipt["pins"], receipt["files"]
    validate_pins(pins)
    expected = {"version": pins["stock_version_sha256"], PE: pins["patched_pe_sha256"],
                UNIX: pins["stock_unix_sha256"]}
    keys = set(CORE)
    if receipt["schema"] >= 2:
        validate_video(receipt["video"])
        keys.update(VIDEO)
        expected.update(receipt["video"]["files"])
    if not isinstance(files, dict) or set(files) != keys:
        raise ValueError("invalid private receipt file set")
    if any(files[key] != checksum for key, checksum in expected.items()):
        raise ValueError("private receipt disagrees with its manifests")
    for key, checksum in files.items():
        if (not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum)
                or digest(contained(target, key)) != checksum):
            raise ValueError("private snapshot checksum mismatch: " + key)
    if (target / "compatibilitytool.vdf").read_text() != DESCRIPTOR:
        raise ValueError("private descriptor changed")
    if receipt["schema"] == 3:
        original_video_launcher(contained(target, "proton").read_bytes(), receipt["launcher"])
        if files["proton"] != receipt["launcher"]["patched_sha256"]:
            raise ValueError("private launcher receipt disagrees with file manifest")
    check_links(target)
    return receipt


def valid_snapshot(target):
    try:
        snapshot_receipt(target)
        return True
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False


def verify_owned(target, receipt):
    if snapshot_receipt(target) != receipt:
        raise ValueError("owned snapshot changed during preparation")


def present(path):
    return path.exists() or path.is_symlink()


def directory_identity(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError("cleanup backup is not an owned directory")
    info = path.stat()
    return [info.st_dev, info.st_ino]


def cleanup_record(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("cleanup marker must be a regular file")
    record = json.loads(path.read_text())
    if (not isinstance(record, dict) or set(record) != {
            "schema", "tool", "backup_id", "backup_receipt", "target_receipt"}
            or type(record["schema"]) is not int or record["schema"] != 1
            or record["tool"] != NAME
            or not isinstance(record["backup_id"], list) or len(record["backup_id"]) != 2
            or any(type(value) is not int or value < 0 for value in record["backup_id"])
            or not isinstance(record["backup_receipt"], dict)
            or not isinstance(record["target_receipt"], dict)):
        raise ValueError("invalid cleanup marker")
    return record


def cleanup_backup(target, backup, vdf, guard, *, previous=None, published=None):
    """Delete only a tracked backup, retaining ownership across partial cleanup.

    The inner marker survives recursive deletion of every other entry. If a stop
    occurs after removing that marker, only an empty directory may be removed.
    The outer record binds retries to the original directory and valid successor.
    """
    journal, sentinel = backup.parent / CLEANUP, backup / CLEANUP
    if present(journal):
        record = cleanup_record(journal)
    else:
        previous = snapshot_receipt(backup) if previous is None else previous
        published = snapshot_receipt(target) if published is None else published
        backup_id = directory_identity(backup)
        verify_owned(backup, previous)
        guard()
        verify_owned(target, published)  # Validate the published path, not just staging.
        if directory_identity(backup) != backup_id:
            raise ValueError("cleanup backup directory changed")
        if present(sentinel):
            raise ValueError("untracked backup cleanup marker")
        record = {"schema": 1, "tool": NAME, "backup_id": backup_id,
                  "backup_receipt": previous, "target_receipt": published}
        vdf["atomic_write"](journal, json.dumps(record, sort_keys=True) + "\n")
        if cleanup_record(journal) != record:
            raise ValueError("cleanup journal was not written correctly")

    guard()
    verify_owned(target, record["target_receipt"])
    if not present(backup):
        journal.unlink()  # Interrupted after rmdir, before removing the journal.
        return
    if directory_identity(backup) != record["backup_id"]:
        raise ValueError("cleanup backup directory changed")
    if present(sentinel):
        if cleanup_record(sentinel) != record:
            raise ValueError("backup cleanup marker changed")
    elif any(backup.iterdir()):
        # Journal creation may have succeeded before the inner marker was written.
        # A nonempty tree without that marker still needs its complete old receipt.
        verify_owned(backup, record["backup_receipt"])
        vdf["atomic_write"](sentinel, json.dumps(record, sort_keys=True) + "\n")
        if cleanup_record(sentinel) != record:
            raise ValueError("backup cleanup marker was not written correctly")

    guard()
    verify_owned(target, record["target_receipt"])
    if directory_identity(backup) != record["backup_id"]:
        raise ValueError("cleanup backup directory changed")
    for entry in backup.iterdir():
        if entry.name == CLEANUP:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    guard()
    verify_owned(target, record["target_receipt"])
    if directory_identity(backup) != record["backup_id"]:
        raise ValueError("cleanup backup directory changed")
    if present(sentinel) and cleanup_record(sentinel) != record:
        raise ValueError("backup cleanup marker changed")
    sentinel.unlink(missing_ok=True)
    backup.rmdir()
    journal.unlink()


def replace_payload(stage, relative, source, checksum):
    """Replace a private directory entry, including symlinks, never its referent."""
    path = stage / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    contained(stage, str(path.parent.relative_to(stage)))
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix=".steamac-payload-", dir=path.parent)
    os.close(fd)
    replacement = Path(temporary)
    try:
        shutil.copyfile(source, replacement)
        if digest(replacement) != checksum:
            raise ValueError("staged payload checksum mismatch: " + relative)
        replacement.chmod(mode)
        os.replace(replacement, path)
    finally:
        replacement.unlink(missing_ok=True)


def ready_tool(steam):
    """Camera presence/ownership predicate; prepare also checks desired codecs."""
    return valid_snapshot(Path(steam) / "compatibilitytools.d" / DIRECTORY)


def prepare(steam, stock, *, bundle=HERE, vdf=None, clone=clone_reflink,
            is_busy=processes_busy, report=log):
    """Return the managed tool name when ready; failure always leaves stock usable."""
    steam, bundle = Path(steam), Path(bundle)
    tools = steam / "compatibilitytools.d"
    target = tools / DIRECTORY
    backup = tools / BACKUP
    try:
        if is_busy():
            report("Steam/FEX/Wine is running; leaving tools unchanged")
            return None
        if stock is not None:
            stock = Path(stock).resolve()
            if tools.resolve().is_relative_to(stock) or stock.is_relative_to(tools.resolve()):
                raise ValueError("stock Proton overlaps private tools")
        if tools.is_symlink():
            raise ValueError("private tools directory is a symlink")
        tools.mkdir(parents=True, exist_ok=True)
        # The lock is outside the tree that will be atomically published.
        with (tools / ".steamac-camera.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                report("another preparation is active; retaining stock")
                return None
            # Recovery and replacement may touch only owned paths, with the same
            # selected mapping and stopped processes checked again at each rename.
            upgrading = present(target) or present(backup)
            vdf = helpers() if vdf is None else vdf
            config = steam / "config/config.vdf"
            original_config = config.read_text() if upgrading and config.exists() else None

            def upgrade_guard():
                if is_busy():
                    raise ValueError("Steam/FEX/Wine started during preparation")
                current = config.read_text() if config.exists() else None
                if (current != original_config or (current is not None and
                        mapping_name(current, vdf) not in (None, "", "proton_experimental", NAME))):
                    raise ValueError("Steam mapping changed or selects a custom tool")

            if present(tools / CLEANUP):
                cleanup_backup(target, backup, vdf, upgrade_guard)
            if present(backup):
                old_backup = snapshot_receipt(backup)  # Never remove an unowned backup.
                upgrade_guard()
                if present(target):
                    published = snapshot_receipt(target)  # A conflicting/unowned target wins.
                    cleanup_backup(target, backup, vdf, upgrade_guard,
                                   previous=old_backup, published=published)
                else:
                    os.rename(backup, target)
                    report("recovered owned camera Proton backup")
            owned = snapshot_receipt(target) if valid_snapshot(target) else None
            if present(target) and owned is None:
                raise ValueError("existing private tool has no valid owned receipt; leaving it unchanged")
            video = read_video(bundle)
            policy = read_launcher_policy(bundle) if video else None
            # Absence preserves camera-only behavior; never downgrade an existing
            # valid video snapshot merely because a later bundle omits the option.
            if owned and (video is None or (owned["schema"] == 3 and owned["video"] == video
                                           and owned["launcher"]["policy"] == policy)):
                return NAME
            if owned:
                upgrade_guard()
                source, pins = target, owned["pins"]
            elif stock is None:
                raise ValueError("fully installed stock Proton not found")
            else:
                source, pins = stock, read_pins(bundle)
                verify_stock(source, pins)
            check_links(source)
            patched_launcher = None
            if video:
                launcher_input = contained(source, "proton").read_bytes()
                original_launcher = launcher_input
                if owned and owned["schema"] == 3:
                    original_launcher = original_video_launcher(original_launcher, owned["launcher"])
                patched_launcher = patch_video_launcher(original_launcher, policy)
            with tempfile.TemporaryDirectory(prefix=".steamac-camera-stage-", dir=tools) as temporary:
                stage = Path(temporary) / "tool"
                stage.mkdir()
                extra = sum((bundle / "proton-video" / Path(key).name).stat().st_size
                            for key in VIDEO) if video else 0
                clone_budget(source, stage, extra)
                clone(source, stage)
                check_links(stage, source)
                if owned:
                    verify_owned(stage, owned)
                    verify_owned(source, owned)
                else:
                    verify_stock(stage, pins)
                    # Check source again after cloning; don't publish a concurrent update.
                    verify_stock(source, pins)
                    for relative in ("proton", "toolmanifest.vdf"):
                        if digest(contained(stage, relative)) != digest(contained(source, relative)):
                            raise ValueError("stock changed during clone: " + relative)
                    replace_payload(stage, PE, contained(bundle, "proton/qcap.dll"), pins["patched_pe_sha256"])
                    vdf["atomic_write"](stage / "compatibilitytool.vdf", DESCRIPTOR)
                if video:
                    for relative, checksum in video["files"].items():
                        replace_payload(stage, relative,
                                        contained(bundle, "proton-video/" + Path(relative).name), checksum)
                files = {relative: digest(contained(stage, relative)) for relative in CORE}
                if owned and any(files[key] != owned["files"][key] for key in CORE):
                    raise ValueError("camera core changed during video upgrade")
                if video:
                    # Replace only the staged entry; preserve mode and never write
                    # through a source hardlink/symlink or an installed Proton path.
                    if contained(stage, "proton").read_bytes() != launcher_input:
                        raise ValueError("video launcher source changed during clone")
                    launcher_payload = Path(temporary) / "proton"
                    launcher_payload.write_bytes(patched_launcher)
                    files["proton"] = hashlib.sha256(patched_launcher).hexdigest()
                    replace_payload(stage, "proton", launcher_payload, files["proton"])
                if files[PE] != pins["patched_pe_sha256"]:
                    raise ValueError("staged camera payload checksum mismatch")
                receipt = {"schema": 1, "tool": NAME, "pins": pins, "files": files}
                if video:
                    receipt.update(schema=3, video=video,
                                   launcher={"policy": policy, "patched_sha256": files["proton"]})
                    files.update({relative: digest(contained(stage, relative)) for relative in VIDEO})
                vdf["atomic_write"](stage / RECEIPT, json.dumps(receipt, sort_keys=True) + "\n")
                verify_owned(stage, receipt)
                check_links(stage, source)
                if owned:
                    verify_owned(source, owned)
                    upgrade_guard()
                    if present(backup):
                        raise ValueError("private backup appeared during preparation")
                    os.rename(target, backup)
                    try:
                        upgrade_guard()
                        if present(target):
                            raise ValueError("private tool appeared during replacement")
                        os.rename(stage, target)
                    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
                        # A failed rollback leaves the validated backup for startup
                        # recovery. Never overwrite a path that appeared meanwhile.
                        if not present(target):
                            verify_owned(backup, owned)
                            os.rename(backup, target)
                        raise
                    cleanup_backup(target, backup, vdf, upgrade_guard,
                                   previous=owned, published=receipt)
                else:
                    if is_busy():
                        raise ValueError("Steam/FEX/Wine started during preparation")
                    if present(target) or present(backup):
                        raise ValueError("private tool or backup appeared during preparation")
                    os.rename(stage, target)
                    verify_owned(target, receipt)
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
        target = steam / "compatibilitytools.d" / DIRECTORY
        backup = target.parent / BACKUP
        owned = ready_tool(steam) or (not present(target) and valid_snapshot(backup))
        if name == NAME and not owned:
            report("unowned camera mapping; leaving settings unchanged")
            return None
        stock = None if owned else installed_stock(steam, vdf)
        if stock is None and not owned:
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

#!/usr/bin/python3
"""Repair only the camera tool parent left root-owned by older manual setups.

Never follows a user-controlled symlink or recursively changes existing tools.
Called by the system service before the Steam user session can start.
"""
import os
import stat


def initialize(home='/home/steamos', uid=1000, gid=1000):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    current = os.open(home, flags)
    try:
        for name in ('.local', 'share', 'Steam'):
            try:
                following = os.open(name, flags, dir_fd=current)
            except (FileNotFoundError, NotADirectoryError):
                return
            os.close(current)
            current = following
        try:
            os.mkdir('compatibilitytools.d', 0o755, dir_fd=current)
        except FileExistsError:
            pass
        directory = os.open('compatibilitytools.d', flags, dir_fd=current)
        try:
            if os.fstat(directory).st_uid == 0:
                os.fchown(directory, uid, gid)
            try:
                lock = os.open('.steamac-camera.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                               dir_fd=directory)
            except (FileNotFoundError, OSError):
                return
            try:
                info = os.fstat(lock)
                if stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == 0:
                    os.fchown(lock, uid, gid)
            finally:
                os.close(lock)
        finally:
            os.close(directory)
    finally:
        os.close(current)


if __name__ == '__main__':
    try:
        initialize()
    except OSError as error:
        print('camera home preparation skipped: errno=' + str(error.errno), flush=True)

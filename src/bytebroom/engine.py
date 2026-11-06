"""Scanning and deleting. No UI code here.

Safety rules:
  * symlinks / junctions are never followed (a link is removed, its target is untouched)
  * for a folder only its contents are deleted - the folder itself is kept
  * the home folder, AppData, AppData/Local/Programs and drive roots are refused
  * files in use are skipped and counted, never forced
"""
from __future__ import annotations

import glob
import os
import shutil
import stat
import subprocess
import sys
import time
from typing import Callable

from .caches import HOME, LOCAL, ROAMING, Cache

REPARSE_POINT = 0x400
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DRIVE = (os.path.splitdrive(LOCAL)[0] or "") + os.sep
PROTECTED = frozenset(os.path.normcase(os.path.abspath(p))
                      for p in (HOME, LOCAL, ROAMING, os.path.join(LOCAL, "Programs")))


# ----------------------------------------------------------------------------- helpers
def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def disk_usage() -> tuple[int, int] | None:
    """(free, total) bytes of the drive that holds AppData."""
    try:
        u = shutil.disk_usage(DRIVE)
        return u.free, u.total
    except OSError:
        return None


def is_link(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & REPARSE_POINT)


def is_protected(path: str) -> bool:
    ap = os.path.normcase(os.path.abspath(path))
    return ap in PROTECTED or os.path.dirname(ap) == ap  # dirname(root) == root


def resolve(c: Cache) -> list[str]:
    """Existing paths of a cache: globs expanded, paths nested in another one dropped."""
    found = sorted({os.path.normpath(p) for pat in c.paths for p in glob.glob(pat)},
                   key=str.lower)
    out: list[str] = []
    for p in found:
        if out and p.lower().startswith(out[-1].lower() + os.sep):
            continue
        out.append(p)
    return out


# ----------------------------------------------------------------------------- sizing
def tree_size(path: str, cutoff: float | None = None,
              alive: Callable[[], bool] = lambda: True) -> int:
    """Bytes under ``path`` (links not followed). ``cutoff``: only files older than it."""
    if not os.path.isdir(path):
        try:
            st = os.stat(path)
        except OSError:
            return 0
        return st.st_size if cutoff is None or st.st_mtime < cutoff else 0
    total, stack = 0, [path]
    while stack:
        if not alive():
            return total
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_link(st):
                        continue
                    if stat.S_ISDIR(st.st_mode):
                        stack.append(e.path)
                    elif cutoff is None or st.st_mtime < cutoff:
                        total += st.st_size
        except OSError:
            pass
    return total


def _cutoff(c: Cache) -> float | None:
    return time.time() - c.min_age_hours * 3600 if c.min_age_hours else None


def scan_cache(c: Cache, alive: Callable[[], bool] = lambda: True) -> tuple[bool, int]:
    """(exists on this PC, size in bytes)."""
    paths = resolve(c)
    cutoff = _cutoff(c)
    return bool(paths), sum(tree_size(p, cutoff, alive) for p in paths)


# ----------------------------------------------------------------------------- deleting
class Stats:
    def __init__(self) -> None:
        self.skipped = 0


def _remove_entry(path: str, st: os.stat_result, stats: Stats) -> None:
    """Delete one file / link / folder. Links are removed, never followed."""

    def retry(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)  # clear the read-only flag and try again
            func(p)
        except OSError:
            stats.skipped += 1

    try:
        if is_link(st):
            try:
                os.unlink(path)
            except OSError:
                os.rmdir(path)
        elif stat.S_ISDIR(st.st_mode):
            kw = {"onexc": retry} if sys.version_info >= (3, 12) else {"onerror": retry}
            shutil.rmtree(path, **kw)
        else:
            try:
                os.unlink(path)
            except PermissionError:
                os.chmod(path, stat.S_IWRITE)
                os.unlink(path)
    except OSError:
        stats.skipped += 1


def _purge_old(folder: str, cutoff: float, stats: Stats) -> None:
    """Delete files older than ``cutoff``, then empty old sub-folders."""
    try:
        with os.scandir(folder) as it:
            entries = list(it)
    except OSError:
        stats.skipped += 1
        return
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode) and not is_link(st):
            _purge_old(e.path, cutoff, stats)
            if st.st_mtime < cutoff:
                try:
                    os.rmdir(e.path)  # only succeeds if it is empty now
                except OSError:
                    pass
        elif st.st_mtime < cutoff:
            _remove_entry(e.path, st, stats)


def clear_path(path: str, min_age_hours: float, stats: Stats) -> None:
    """Folder: delete its contents, keep the folder. File: delete it."""
    if is_protected(path):
        stats.skipped += 1
        return
    cutoff = time.time() - min_age_hours * 3600 if min_age_hours else None
    if not os.path.isdir(path):
        try:
            st = os.lstat(path)
        except OSError:
            return
        if cutoff is None or st.st_mtime < cutoff:
            _remove_entry(path, st, stats)
        return
    if cutoff is not None:
        _purge_old(path, cutoff, stats)
        return
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except OSError:
        stats.skipped += 1
        return
    for e in entries:
        try:
            _remove_entry(e.path, e.stat(follow_symlinks=False), stats)
        except OSError:
            stats.skipped += 1


def run_command(cmd: tuple[str, ...]) -> str | None:
    """Run an official clean command. None on success, else an error message."""
    exe = shutil.which(cmd[0])
    if not exe:
        return f"'{cmd[0]}' is not installed or not on PATH"
    try:
        r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, errors="replace",
                           timeout=300, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    if r.returncode != 0:
        out = (r.stderr or r.stdout or "").strip()
        return out.splitlines()[-1] if out else f"exit code {r.returncode}"
    return None


def clear_cache(c: Cache, stats: Stats) -> str | None:
    """Clear one cache. Returns an error message or None."""
    paths = resolve(c)
    folders = [p for p in paths if os.path.isdir(p)]
    if c.command:
        err = run_command(c.command)
        if c.command_only:
            return err
        # command failed or tool missing -> fall through and delete the files directly
    for p in paths:
        clear_path(p, c.min_age_hours, stats)
    for p in folders:  # keep the (now empty) folder so the owning tool still finds it
        try:
            os.makedirs(p, exist_ok=True)
        except OSError:
            pass
    return None


def clear_caches(caches: list[Cache],
                 on_progress: Callable[[int, int, Cache], None] = lambda i, n, c: None,
                 ) -> tuple[int, int, list[str]]:
    """Clear several caches. Returns (bytes freed on disk, items skipped, error messages)."""
    before = (disk_usage() or (0, 0))[0]
    stats, errors = Stats(), []
    for i, c in enumerate(caches):
        on_progress(i, len(caches), c)
        try:
            err = clear_cache(c, stats)
        except Exception as e:  # one broken cache must not stop the rest
            err = str(e)
        if err:
            errors.append(f"{c.name}: {err}")
    after = (disk_usage() or (0, 0))[0]
    return after - before, stats.skipped, errors


def open_in_explorer(c: Cache) -> str | None:
    """Open the first existing path of a cache in Explorer. Returns an error or None."""
    paths = resolve(c)
    if not paths:
        return "This cache does not exist (anymore)."
    target = paths[0]
    try:
        if os.path.isdir(target):
            os.startfile(target)  # type: ignore[attr-defined]  (Windows only)
        else:
            subprocess.Popen(["explorer", "/select,", target])
    except OSError as e:
        return str(e)
    return None

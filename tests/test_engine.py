import os
import stat
import subprocess
import sys
import time

import pytest

from bytebroom import engine
from bytebroom.caches import CACHES, Cache, P


def write(path, size=1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)


def make_cache(*paths, **kw):
    return Cache("t", "test", tuple(P(p) for p in paths), True, "note", **kw)


def test_clear_keeps_folder_and_removes_contents(tmp_path):
    cache = tmp_path / "cache"
    write(str(cache / "a.bin"), 1000)
    write(str(cache / "sub" / "deep" / "b.bin"), 500)
    assert engine.tree_size(str(cache)) == 1500

    stats = engine.Stats()
    engine.clear_path(str(cache), 0, stats)
    assert cache.is_dir()
    assert list(cache.iterdir()) == []
    assert stats.skipped == 0


def test_readonly_files_are_removed(tmp_path):
    f = tmp_path / "cache" / "ro.bin"
    write(str(f))
    os.chmod(f, stat.S_IREAD)
    engine.clear_path(str(tmp_path / "cache"), 0, engine.Stats())
    assert not f.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_junction_target_is_never_touched(tmp_path):
    cache, outside = tmp_path / "cache", tmp_path / "outside"
    cache.mkdir()
    write(str(outside / "precious.txt"), 10)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(cache / "link"), str(outside)],
                   check=True, capture_output=True)

    assert engine.tree_size(str(cache)) == 0  # link not followed
    engine.clear_path(str(cache), 0, engine.Stats())
    assert list(cache.iterdir()) == []
    assert (outside / "precious.txt").exists()


def test_min_age_only_removes_old_files(tmp_path):
    old, new = tmp_path / "old.txt", tmp_path / "new.txt"
    old_dir = tmp_path / "olddir"
    write(str(old))
    write(str(new))
    write(str(old_dir / "x.txt"))
    t = time.time() - 3 * 86400
    for p in (old, old_dir / "x.txt", old_dir):
        os.utime(p, (t, t))

    assert engine.tree_size(str(tmp_path), time.time() - 86400) == 2
    engine.clear_path(str(tmp_path), 24, engine.Stats())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["new.txt"]


def test_protected_paths_are_refused(tmp_path):
    from bytebroom.caches import HOME, LOCAL
    assert engine.is_protected(HOME)
    assert engine.is_protected(LOCAL)
    assert engine.is_protected(os.path.abspath(os.sep))
    assert not engine.is_protected(str(tmp_path))


def test_resolve_drops_nested_paths(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    c = make_cache(str(tmp_path / "a"), str(tmp_path / "a" / "b"), str(tmp_path / "missing"))
    assert engine.resolve(c) == [str(tmp_path / "a")]


def test_scan_and_clear_cache(tmp_path):
    write(str(tmp_path / "c" / "f.bin"), 300)
    c = make_cache(str(tmp_path / "c"))
    assert engine.scan_cache(c) == (True, 300)
    freed, skipped, errors = engine.clear_caches([c])
    assert (skipped, errors) == (0, [])
    assert engine.scan_cache(c) == (True, 0)  # folder kept, now empty
    assert engine.scan_cache(make_cache(str(tmp_path / "nope"))) == (False, 0)


def test_cache_list_is_valid():
    keys = [c.key for c in CACHES]
    assert len(keys) == len(set(keys)), "cache keys must be unique"
    for c in CACHES:
        assert c.paths and c.name and c.note
        assert not (c.command_only and not c.command), c.key

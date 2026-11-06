"""ByteBroom desktop app (CustomTkinter UI)."""
from __future__ import annotations

import os
import queue
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import customtkinter as ctk

from . import __version__
from .caches import CACHES, Cache
from .engine import clear_caches, disk_usage, human, open_in_explorer, scan_cache

APP_NAME = "ByteBroom"
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "bytebroom.ico")

# colour pairs: (light mode, dark mode)
BG = ("#f3f4f6", "#121418")
CARD = ("#ffffff", "#1c1f25")
BORDER = ("#e5e7eb", "#2a2f37")
TEXT = ("#111827", "#f3f4f6")
MUTED = ("#6b7280", "#9ca3af")
SAFE_FG, SAFE_BG = ("#15803d", "#4ade80"), ("#dcfce7", "#12301c")
WARN_FG, WARN_BG = ("#c2410c", "#fb923c"), ("#ffedd5", "#36210f")
DANGER, DANGER_HOVER = ("#dc2626", "#dc2626"), ("#b91c1c", "#b91c1c")


def font(size: int = 13, bold: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight="bold" if bold else "normal")


def set_icon(window) -> None:
    if sys.platform == "win32" and os.path.exists(ICON):
        try:
            window.iconbitmap(ICON)
        except Exception:
            pass


def secondary_button(parent, text: str, command, width: int = 100) -> ctk.CTkButton:
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=36,
                         corner_radius=8, fg_color="transparent", border_width=1,
                         border_color=BORDER, text_color=TEXT, hover_color=BORDER)


# ----------------------------------------------------------------------------- dialog
class Dialog(ctk.CTkToplevel):
    """Small modal dialog. ``items`` = [(left text, right text, is_warning), ...]."""

    def __init__(self, master, title: str, heading: str, message: str = "",
                 items: list[tuple[str, str, bool]] | None = None, warning: str = "",
                 ok_text: str = "OK", cancel_text: str | None = None, danger: bool = False):
        super().__init__(master, fg_color=BG)
        self.result = False
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        set_icon(self)

        ctk.CTkLabel(self, text=heading, font=font(18, True), anchor="w").pack(
            fill="x", padx=24, pady=(22, 4))
        if message:
            ctk.CTkLabel(self, text=message, text_color=MUTED, anchor="w", justify="left",
                         wraplength=460).pack(fill="x", padx=24, pady=(0, 12))
        if items:
            if len(items) > 8:
                box = ctk.CTkScrollableFrame(self, width=460, height=260, fg_color=CARD,
                                             corner_radius=10)
            else:
                box = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
            box.pack(fill="x", padx=24, pady=(0, 12))
            for left, right, warn in items:
                row = ctk.CTkFrame(box, fg_color="transparent")
                row.pack(fill="x", padx=12, pady=3)
                ctk.CTkLabel(row, text=left, anchor="w",
                             text_color=WARN_FG if warn else TEXT).pack(side="left")
                ctk.CTkLabel(row, text=right, font=font(13, True)).pack(side="right")
        if warning:
            w = ctk.CTkFrame(self, fg_color=WARN_BG, corner_radius=10)
            w.pack(fill="x", padx=24, pady=(0, 12))
            ctk.CTkLabel(w, text=warning, text_color=WARN_FG, anchor="w", justify="left",
                         wraplength=440).pack(fill="x", padx=14, pady=10)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(6, 20))
        self.ok = ctk.CTkButton(buttons, text=ok_text, command=self._ok, height=36,
                                corner_radius=8, font=font(13, True),
                                fg_color=DANGER if danger else None,
                                hover_color=DANGER_HOVER if danger else None)
        self.ok.pack(side="right")
        if cancel_text:
            secondary_button(buttons, cancel_text, self._cancel).pack(side="right", padx=(0, 10))

        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._ok())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._center(master)
        self.after(60, self._grab)

    def _center(self, master) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = master.winfo_rootx() + (master.winfo_width() - w) // 2
        y = master.winfo_rooty() + (master.winfo_height() - h) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _grab(self) -> None:
        try:
            self.lift()
            self.grab_set()
            self.ok.focus_set()
        except Exception:
            pass

    def _ok(self) -> None:
        self.result = True
        self.destroy()

    def _cancel(self) -> None:
        self.destroy()

    def show(self) -> bool:
        self.wait_window()
        return self.result


# ----------------------------------------------------------------------------- one row
class CacheRow(ctk.CTkFrame):
    def __init__(self, master, app: "App", cache: Cache):
        super().__init__(master, fg_color=CARD, corner_radius=12, border_width=1,
                         border_color=BORDER)
        self.app, self.cache = app, cache
        self.var = ctk.BooleanVar(value=cache.key in app.checked)
        self.grid_columnconfigure(1, weight=1)

        self.check = ctk.CTkCheckBox(self, text="", width=24, checkbox_width=22,
                                     checkbox_height=22, corner_radius=6, variable=self.var,
                                     command=self._changed)
        self.check.grid(row=0, column=0, rowspan=2, padx=(16, 6), pady=12)
        self.title = ctk.CTkLabel(self, text=cache.name, font=font(14, True), anchor="w")
        self.title.grid(row=0, column=1, sticky="sw", pady=(10, 0))
        self.note = ctk.CTkLabel(self, text=cache.note, font=font(12), text_color=MUTED,
                                 anchor="w", justify="left", wraplength=470)
        self.note.grid(row=1, column=1, sticky="nw", pady=(0, 10))
        self.badge = ctk.CTkLabel(self, text="SAFE" if cache.safe else "CAUTION", width=76,
                                  height=24, corner_radius=8, font=font(11, True),
                                  fg_color=SAFE_BG if cache.safe else WARN_BG,
                                  text_color=SAFE_FG if cache.safe else WARN_FG)
        self.badge.grid(row=0, column=2, rowspan=2, padx=8)
        self.size = ctk.CTkLabel(self, text="scanning...", width=100, anchor="e",
                                 font=font(15, True), text_color=MUTED)
        self.size.grid(row=0, column=3, rowspan=2, padx=(8, 4))
        self.open_btn = secondary_button(self, "Open", lambda: app.open_folder(cache), width=64)
        self.open_btn.configure(height=30)
        self.open_btn.grid(row=0, column=4, rowspan=2, padx=(8, 16))

        for w in (self, self.title, self.note, self.badge, self.size):
            w.bind("<Button-1>", self._click)

    def _click(self, _event=None) -> None:
        if not self.app.busy:
            self.var.set(not self.var.get())
            self._changed()

    def _changed(self) -> None:
        self.app.set_checked(self.cache.key, self.var.get())

    def set_size(self, size: int | None) -> None:
        if size is None:
            self.size.configure(text="scanning...", text_color=MUTED)
        else:
            self.size.configure(text=human(size), text_color=MUTED if size == 0 else TEXT)


# ----------------------------------------------------------------------------- window
class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BG)
        self.title(APP_NAME)
        self.geometry("1060x780")
        self.minsize(920, 600)
        set_icon(self)

        self.caches = {c.key: c for c in CACHES}
        self.info: dict[str, dict] = {}  # key -> {"size": int | None, "found": bool}
        self.checked = {c.key for c in CACHES if c.safe}
        self.q: queue.Queue = queue.Queue()
        self.gen = 0          # bumped on every refresh; stale scan results are ignored
        self.pending = 0
        self.busy = False
        self.pool = ThreadPoolExecutor(max_workers=4)

        self._build()
        self.rows = {c.key: CacheRow(self.list, self, c) for c in CACHES}
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)
        self.refresh()

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 10))
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text=APP_NAME, font=font(26, True)).pack(anchor="w")
        ctk.CTkLabel(left, text="Find the caches eating your disk and clear them safely.",
                     font=font(13), text_color=MUTED).pack(anchor="w")
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", anchor="n")
        theme = ctk.CTkSegmentedButton(right, values=["System", "Light", "Dark"],
                                       command=lambda v: ctk.set_appearance_mode(v.lower()))
        theme.set("System")
        theme.pack(anchor="e")
        ctk.CTkLabel(right, text=f"v{__version__}", font=font(11),
                     text_color=MUTED).pack(anchor="e", pady=(4, 0))

        tiles = ctk.CTkFrame(self, fg_color="transparent")
        tiles.pack(fill="x", padx=24, pady=(0, 12))
        tiles.grid_columnconfigure((0, 1, 2), weight=1, uniform="tile")
        self.free_val, self.free_sub, self.free_bar = self._tile(tiles, 0, "Free space", bar=True)
        self.found_val, self.found_sub, _ = self._tile(tiles, 1, "Cache found")
        self.sel_val, self.sel_sub, _ = self._tile(tiles, 2, "Selected to clear")

        # footer is packed before the list so it always stays visible
        footer = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0)
        footer.pack(side="bottom", fill="x")
        self.progress = ctk.CTkProgressBar(footer, height=4, corner_radius=0)
        self.progress.set(0)
        self.progress.pack(fill="x")
        bar = ctk.CTkFrame(footer, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=14)
        bar.grid_columnconfigure(1, weight=1)
        btns = ctk.CTkFrame(bar, fg_color="transparent")
        btns.grid(row=0, column=0, sticky="w")
        self.buttons = []
        for text, cmd in [("Refresh", self.refresh), ("Select safe", self.select_safe),
                          ("Select all", self.select_all), ("Select none", self.select_none)]:
            b = secondary_button(btns, text, cmd)
            b.pack(side="left", padx=(0, 8))
            self.buttons.append(b)
        self.status = ctk.CTkLabel(bar, text="", font=font(12), text_color=MUTED, anchor="w")
        self.status.grid(row=0, column=1, sticky="ew", padx=12)
        self.clear_btn = ctk.CTkButton(bar, text="Clear selected", command=self.clear_selected,
                                       height=42, width=230, corner_radius=10, font=font(14, True),
                                       fg_color=DANGER, hover_color=DANGER_HOVER)
        self.clear_btn.grid(row=0, column=2, sticky="e")

        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list.pack(fill="both", expand=True, padx=(24, 10), pady=(0, 8))
        self.list.grid_columnconfigure(0, weight=1)
        self.safe_header = ctk.CTkLabel(
            self.list, text="SAFE TO CLEAR  ·  re-downloaded or rebuilt when needed",
            font=font(12, True), text_color=SAFE_FG, anchor="w")
        self.warn_header = ctk.CTkLabel(
            self.list, text="CAUTION  ·  you lose something, read the note",
            font=font(12, True), text_color=WARN_FG, anchor="w")

    def _tile(self, parent, col: int, title: str, bar: bool = False):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, border_width=1,
                         border_color=BORDER)
        f.grid(row=0, column=col, sticky="nsew",
               padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
        ctk.CTkLabel(f, text=title.upper(), font=font(11, True), text_color=MUTED).pack(
            anchor="w", padx=18, pady=(14, 0))
        val = ctk.CTkLabel(f, text="-", font=font(26, True))
        val.pack(anchor="w", padx=18)
        pb = None
        if bar:
            pb = ctk.CTkProgressBar(f, height=6, corner_radius=3)
            pb.set(0)
            pb.pack(fill="x", padx=18, pady=(2, 4))
        sub = ctk.CTkLabel(f, text="", font=font(12), text_color=MUTED)
        sub.pack(anchor="w", padx=18, pady=(0, 14))
        return val, sub, pb

    def _layout(self, sort: bool) -> None:
        visible = [c for c in CACHES if self.info[c.key]["found"]]
        if sort:
            visible.sort(key=lambda c: -(self.info[c.key]["size"] or 0))
        r = 0
        for header, group in ((self.safe_header, [c for c in visible if c.safe]),
                              (self.warn_header, [c for c in visible if not c.safe])):
            if not group:
                header.grid_remove()
                continue
            header.grid(row=r, column=0, sticky="w", padx=4, pady=(16 if r else 2, 6))
            r += 1
            for c in group:
                self.rows[c.key].grid(row=r, column=0, sticky="ew", padx=(0, 8), pady=4)
                r += 1
        for c in CACHES:
            if not self.info[c.key]["found"]:
                self.rows[c.key].grid_remove()

    # ------------------------------------------------------------------ scanning
    def refresh(self) -> None:
        if self.busy:
            return
        self.gen += 1
        gen = self.gen
        self.info = {c.key: {"size": None, "found": True} for c in CACHES}
        self.pending = len(CACHES)
        for c in CACHES:
            self.rows[c.key].set_size(None)
            self.pool.submit(self._scan_worker, gen, c)
        self._layout(sort=False)
        self.status.configure(text="Scanning...")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._update_disk()
        self._update_totals()

    def _scan_worker(self, gen: int, c: Cache) -> None:
        try:
            found, size = scan_cache(c, alive=lambda: self.gen == gen)
        except Exception:
            found, size = True, 0
        self.q.put(("scan", gen, c.key, found, size))

    def _on_scan(self, gen: int, key: str, found: bool, size: int) -> None:
        if gen != self.gen:
            return
        self.pending -= 1
        self.info[key] = {"size": size, "found": found}
        if found:
            self.rows[key].set_size(size)
        else:
            self.rows[key].grid_remove()
        self._update_totals()
        if self.pending:
            self.status.configure(text=f"Scanning...  {self.pending} left")
        else:
            self._scan_done()

    def _scan_done(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self._layout(sort=True)
        self.status.configure(text="Tick what you want, then press Clear.")

    # ------------------------------------------------------------------ selection
    def set_checked(self, key: str, value: bool) -> None:
        (self.checked.add if value else self.checked.discard)(key)
        self._update_totals()

    def _select(self, keys) -> None:
        self.checked = set(keys)
        for k, row in self.rows.items():
            row.var.set(k in self.checked)
        self._update_totals()

    def select_safe(self) -> None:
        self._select(c.key for c in CACHES if c.safe)

    def select_all(self) -> None:
        self._select(self.caches)

    def select_none(self) -> None:
        self._select(())

    def _selected(self) -> list[Cache]:
        return [c for c in CACHES if c.key in self.checked and self.info[c.key]["found"]]

    def _update_totals(self) -> None:
        found = [c for c in CACHES if self.info[c.key]["found"] and not c.command_only]
        total = sum(self.info[c.key]["size"] or 0 for c in found)
        self.found_val.configure(text=human(total))
        self.found_sub.configure(text=f"in {len(found)} places" +
                                 ("  ·  still scanning" if self.pending else ""))
        sel = self._selected()
        sel_total = sum(self.info[c.key]["size"] or 0 for c in sel if not c.command_only)
        self.sel_val.configure(text=human(sel_total))
        self.sel_sub.configure(text=f"{len(sel)} item{'s' if len(sel) != 1 else ''}")
        self.clear_btn.configure(text=f"Clear selected  ·  {human(sel_total)}",
                                 state="normal" if sel and not self.busy else "disabled")

    def _update_disk(self) -> None:
        du = disk_usage()
        if not du:
            return
        free, total = du
        used = (total - free) / total if total else 0
        self.free_val.configure(text=human(free))
        self.free_sub.configure(text=f"of {human(total)}  ·  {used:.0%} used")
        self.free_bar.set(used)
        self.free_bar.configure(progress_color=DANGER if used > 0.9 else
                                ctk.ThemeManager.theme["CTkProgressBar"]["progress_color"])

    def open_folder(self, cache: Cache) -> None:
        err = open_in_explorer(cache)
        if err:
            Dialog(self, APP_NAME, "Can't open folder", err).show()

    # ------------------------------------------------------------------ clearing
    def clear_selected(self) -> None:
        if self.busy:
            return
        if self.pending:
            Dialog(self, APP_NAME, "Still scanning", "Try again when the scan finishes.").show()
            return
        sel = self._selected()
        if not sel:
            return
        items = [(c.name, "prune" if c.command_only else human(self.info[c.key]["size"] or 0),
                  not c.safe) for c in sel]
        notes = []
        apps = sorted({c.close_first for c in sel if c.close_first})
        if apps:
            notes.append(f"Close {', '.join(apps)} first. Files in use get skipped.")
        notes += [f"{c.name}: {c.note}" for c in sel if not c.safe]
        ok = Dialog(self, APP_NAME, "Clear these caches?",
                    "Files are deleted permanently (not moved to the Recycle Bin).",
                    items=items, warning="\n\n".join(notes),
                    ok_text="Clear now", cancel_text="Cancel", danger=True).show()
        if not ok:
            return
        self._set_busy(True)
        threading.Thread(target=self._clear_worker, args=(sel,), daemon=True).start()

    def _clear_worker(self, caches: list[Cache]) -> None:
        def progress(i: int, n: int, c: Cache) -> None:
            self.q.put(("progress", i, n, f"Clearing {c.name}...  ({i + 1}/{n})"))

        freed, skipped, errors = clear_caches(caches, progress)
        self.q.put(("progress", len(caches), len(caches), "Done"))
        self.q.put(("cleared", freed, skipped, errors))

    def _on_progress(self, i: int, n: int, text: str) -> None:
        self.progress.configure(mode="determinate")
        self.progress.set(i / max(n, 1))
        self.status.configure(text=text)

    def _on_cleared(self, freed: int, skipped: int, errors: list[str]) -> None:
        self._set_busy(False)
        msg = ("Measured as the change in free disk space." if not skipped else
               f"{skipped} files/folders were in use and were skipped. "
               f"Close the app that uses them and clear again.")
        Dialog(self, APP_NAME, f"Freed {human(max(freed, 0))}", msg,
               warning="\n".join(errors)).show()
        self.refresh()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in self.buttons:
            b.configure(state=state)
        for row in self.rows.values():
            row.check.configure(state=state)
        self._update_totals()

    # ------------------------------------------------------------------ plumbing
    def _poll(self) -> None:
        try:
            while True:
                name, *args = self.q.get_nowait()
                getattr(self, f"_on_{name}")(*args)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _on_close(self) -> None:
        if self.busy and not Dialog(self, APP_NAME, "Still clearing",
                                    "Quit anyway? What is already deleted stays deleted.",
                                    ok_text="Quit", cancel_text="Keep going").show():
            return
        self.gen += 1  # tells running scans to stop
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.destroy()


def main() -> None:
    if sys.platform == "win32":
        try:  # own taskbar icon instead of the generic python one
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ByteBroom.App")
        except Exception:
            pass
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()

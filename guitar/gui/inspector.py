"""The Problem Details inspector: header + read-only, scrollable diff viewer."""

from __future__ import annotations

import tkinter as tk
from typing import Optional

from ..details import Block, Details
from ..models import FileResult
from ..theme import Theme, status_token
from .widgets import Badge, RoundedCard, ScrollText, TFrame, TLabel, ThemeManager

LABEL_INDENT = 128


# Facts whose values are long unbreakable strings (paths, hashes) wrap by character.
CHAR_WRAP_LABELS = {"Relative path", "SRC path", "DST repo path", "SHA-256 SRC", "SHA-256 HEAD"}


def blocks_to_parts(blocks: list[Block]) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    for b in blocks:
        if b.kind == "fact":
            label, _, value = b.text.partition("\t")
            suffix = "_c" if label in CHAR_WRAP_LABELS else ""
            parts.append((label + "\t", "flabel" + suffix))
            parts.append((value + "\n", "fvalue" + suffix))
        elif b.kind == "blank":
            parts.append(("\n", "blank"))
        else:
            parts.append((b.text + "\n", b.kind))
    return parts


class InspectorPanel(RoundedCard):
    def __init__(self, master, tm: ThemeManager) -> None:
        super().__init__(master, tm, surface="bg", fill="panel", radius=14, pad=0)
        body = self.body
        head = TFrame(body, tm, bg="panel")
        head.pack(fill="x", padx=18, pady=(16, 8))
        row = TFrame(head, tm, bg="panel")
        row.pack(fill="x")
        TLabel(row, tm, "Problem Details", font="section", fg="text_muted").pack(side="left")
        self.badge = Badge(row, tm, surface="panel")
        self.badge.pack(side="right")
        self.name = TLabel(head, tm, "No file selected", font="heading", justify="left", anchor="w")
        self.name.pack(fill="x", pady=(8, 0))
        self.path = TLabel(head, tm, "", font="small", fg="text_muted", justify="left", anchor="w")
        self.path.pack(fill="x", pady=(2, 0))
        head.bind("<Configure>", lambda e: (self.name.configure(wraplength=max(120, e.width - 4)),
                                            self.path.configure(wraplength=max(120, e.width - 4))))
        self.sep = TFrame(body, tm, bg="border", height=1)
        self.sep.pack(fill="x")
        self.viewer = ScrollText(body, tm, font="mono_small", wrap="none")
        self.viewer.pack(fill="both", expand=True, padx=(4, 6), pady=(4, 8))
        tm.register(self, self._themed)
        self.show(None)

    # ------------------------------------------------------------------
    def show(self, details: Optional[Details]) -> None:
        if details is None:
            self.badge.set("", "text_muted")
            self.name.configure(text="No file selected")
            self.path.configure(text="Select a row in the table to inspect it.")
            self.viewer.set_content([
                ("\n", "blank"),
                ("Inspector\n", "heading"),
                ("Pick any file to see its status, paths, sizes, SHA-256 hashes,\n", "muted"),
                ("the first difference and a readable unified diff against Git HEAD.\n", "muted"),
            ])
            return
        r: FileResult = details.result
        self.badge.set(r.status.label, status_token(r.status.value))
        self.name.configure(text=r.name)
        self.path.configure(text=r.rel_path)
        self.viewer.set_content(blocks_to_parts(details.blocks))

    # ------------------------------------------------------------------
    def _themed(self, th: Theme) -> None:
        RoundedCard.apply_theme(self, th)
        f = self.tm.fonts
        t = self.viewer.text
        t.tag_configure("heading", font=f.section, foreground=th.accent_soft if th.name == "dark" else th.primary,
                        spacing1=6, spacing3=5, wrap="word")
        for suffix, wrap in (("", "word"), ("_c", "char")):
            t.tag_configure("flabel" + suffix, font=f.small_bold, foreground=th.text_muted,
                            tabs=(LABEL_INDENT,), lmargin2=LABEL_INDENT, wrap=wrap, spacing1=3)
            t.tag_configure("fvalue" + suffix, font=f.mono_small, foreground=th.text,
                            lmargin2=LABEL_INDENT, wrap=wrap, spacing1=3)
        t.tag_configure("para", font=f.body, foreground=th.text, wrap="word", spacing1=2)
        t.tag_configure("ok", font=f.body_bold, foreground=th.success, wrap="word")
        t.tag_configure("warn", font=f.body, foreground=th.warning, wrap="word", spacing1=2)
        t.tag_configure("err", font=f.body, foreground=th.error, wrap="word")
        t.tag_configure("trace", font=f.mono_small, foreground=th.error, wrap="word")
        t.tag_configure("muted", font=f.small, foreground=th.text_faint, wrap="word")
        t.tag_configure("blank", font=f.caption)
        t.tag_configure("ctx", font=f.mono_small, foreground=th.text_muted)
        t.tag_configure("mono", font=f.mono_small, foreground=th.text)
        t.tag_configure("add", font=f.mono_small, foreground=th.diff_add_fg, background=th.diff_add_bg)
        t.tag_configure("del", font=f.mono_small, foreground=th.diff_del_fg, background=th.diff_del_bg)
        t.tag_configure("hunk", font=f.mono_small, foreground=th.diff_hunk_fg, spacing1=6)
        t.tag_configure("hdr", font=f.mono_small, foreground=th.text_faint)

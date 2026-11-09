"""Zero-dependency PDF text-layer reader for the bundled OIF CMIS specifications.

The upstream jimfred/CMIS rebuild chain uses ``pdfplumber`` to read the spec
PDF table grid.  CMIScope keeps a strict "standard library only" runtime, so
this module implements the small subset of PDF needed for that job:

  * classic ``xref`` tables (with optional ``/Prev`` chains),
  * FlateDecode content streams,
  * the page tree (``/Pages`` -> ``/Kids``),
  * positioned text from ``BT ... ET`` blocks (``Tf`` / ``Tm`` / ``Td`` / ``Tj``
    / ``TJ``), including WinAnsi string escapes and optional ToUnicode CMaps.

Every span keeps its ``(x, y, size)`` coordinates.  That is what makes it
possible to rebuild the Section 8 table columns without a PDF library: the OIF
documents are produced by Word, where each table cell is emitted as its own
positioned text run.  Superscript footnote markers (small font size) can be
filtered by the caller, exactly as the upstream extractor did.

This reader is deliberately read-only and best-effort.  It is not a general PDF
renderer: images, Type3 fonts, rotated text and encrypted documents are out of
scope.  A stream that cannot be decoded yields an empty page instead of an
exception, so one damaged page never aborts a full-document scan.

Derived from the table-extraction approach of jimfred/CMIS (MIT,
Copyright (c) 2026 Jim Frederick).  No OIF specification text is embedded here.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path
from typing import Iterator, NamedTuple

__all__ = ["Span", "Line", "PdfTextDocument", "PdfFormatError"]


class PdfFormatError(ValueError):
    """Raised when the file is not a readable, unencrypted classic-xref PDF."""


class Span(NamedTuple):
    x: float
    y: float
    size: float
    text: str
    font: str


class Line(NamedTuple):
    y: float
    spans: tuple[Span, ...]

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def stripped(self) -> str:
        return self.text.strip()


_STARTXREF = re.compile(rb"startxref\s+(\d+)\s+%%EOF")
_XREF_ENTRY = re.compile(rb"(\d{10})\s+(\d{5})\s+([nf])")
_STREAM = re.compile(rb"stream\r?\n")
_BT = re.compile(rb"BT(.*?)ET", re.S)
_TF = re.compile(rb"/([^\s/<>\[\]]+)\s+([-+]?\d*\.?\d+)\s+Tf")
_TM = re.compile(
    rb"([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s+"
    rb"([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s+Tm"
)
_TD = re.compile(rb"([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s+(?:Td|TD)")
_LITERAL = re.compile(rb"\((?:\\.|[^()\\])*\)", re.S)
_HEX = re.compile(rb"<([0-9A-Fa-f\s]+)>")
_OBJ_REF = re.compile(rb"(\d+)\s+0\s+R")
_NUMBER = re.compile(rb"[-+]?\d*\.?\d+")

_ESCAPES = {
    0x6E: b"\n", 0x72: b"\r", 0x74: b"\t", 0x62: b"\b", 0x66: b"\f",
    0x28: b"(", 0x29: b")", 0x5C: b"\\",
}


def _unescape(raw: bytes) -> bytes:
    """Decode PDF literal-string escapes, including octal sequences."""
    out = bytearray()
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch != 0x5C:  # backslash
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(raw):
            break
        nxt = raw[i]
        if 0x30 <= nxt <= 0x37:  # \ddd
            j = i
            while j < len(raw) and j < i + 3 and 0x30 <= raw[j] <= 0x37:
                j += 1
            out.append(int(raw[i:j], 8) & 0xFF)
            i = j
            continue
        out.extend(_ESCAPES.get(nxt, bytes([nxt])))
        i += 1
    return bytes(out)


def _decode_literal(raw: bytes) -> str:
    """WinAnsi/StandardEncoding text; cp1252 covers the OIF micro/degree signs."""
    return _unescape(raw[1:-1]).decode("cp1252", "replace")


class PdfTextDocument:
    """Read positioned text from an unencrypted classic-xref PDF."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._data = self.path.read_bytes()
        if not self._data.startswith(b"%PDF-"):
            raise PdfFormatError(f"missing PDF header: {self.path.name}")
        if re.search(rb"/Encrypt\b", self._data[-8192:]):
            raise PdfFormatError("encrypted PDFs are not supported")
        self._offsets = self._read_xref()
        self._object_cache: dict[int, bytes] = {}
        self._stream_cache: dict[int, bytes] = {}
        self._cmap_cache: dict[str, dict[int, str]] = {}
        self._pages = self._read_page_tree()
        self._page_cache: dict[int, tuple[Span, ...]] = {}

    # ------------------------------------------------------------------ structure

    def _read_xref(self) -> dict[int, int]:
        """Walk classic xref sections (newest first) and collect object offsets."""
        matches = list(_STARTXREF.finditer(self._data[-2048:]))
        if not matches:
            raise PdfFormatError("no startxref marker found")
        offsets: dict[int, int] = {}
        seen: set[int] = set()
        pos = int(matches[-1].group(1))
        while pos and pos not in seen and pos < len(self._data):
            seen.add(pos)
            chunk = self._data[pos:]
            if not chunk.startswith(b"xref"):
                raise PdfFormatError(
                    f"unsupported cross-reference at byte {pos} (no classic xref table)")
            cursor = chunk.find(b"\n") + 1  # skip the "xref" line
            prev = None
            while cursor < len(chunk):
                while cursor < len(chunk) and chunk[cursor:cursor + 1] in (
                    b"\r", b"\n", b" ", b"\t"
                ):
                    cursor += 1
                nl = chunk.find(b"\n", cursor)
                if nl < 0:
                    break
                header = chunk[cursor:nl].strip()
                cursor = nl + 1
                if header.startswith(b"trailer"):
                    tail = chunk[cursor:cursor + 8192]
                    m = re.search(rb"/Prev\s+(\d+)", tail)
                    prev = int(m.group(1)) if m else None
                    break
                parts = header.split()
                if len(parts) != 2 or not all(part.isdigit() for part in parts):
                    break
                first, count = int(parts[0]), int(parts[1])
                for index in range(count):
                    nl = chunk.find(b"\n", cursor)
                    if nl < 0:
                        break
                    entry = chunk[cursor:nl].strip()
                    cursor = nl + 1
                    m = _XREF_ENTRY.match(entry)
                    if m and m.group(3) == b"n":
                        offsets.setdefault(first + index, int(m.group(1)))
            pos = prev or 0
        if not offsets:
            raise PdfFormatError("cross-reference table contains no objects")
        return offsets

    def _object(self, number: int) -> bytes:
        cached = self._object_cache.get(number)
        if cached is not None:
            return cached
        offset = self._offsets.get(number)
        raw = b""
        if offset is not None and offset < len(self._data):
            end = self._data.find(b"endobj", offset)
            if end >= 0:
                raw = self._data[offset:end]
        if not raw:
            m = re.search(rb"(?<!\d)" + str(number).encode() + rb"\s+0\s+obj", self._data)
            if m:
                end = self._data.find(b"endobj", m.end())
                raw = self._data[m.start():end if end >= 0 else len(self._data)]
        self._object_cache[number] = raw
        return raw

    def _stream(self, number: int) -> bytes:
        cached = self._stream_cache.get(number)
        if cached is not None:
            return cached
        raw = self._object(number)
        m = _STREAM.search(raw)
        data = b""
        if m:
            start = m.end()
            end = raw.rfind(b"endstream")
            blob = raw[start:end if end >= 0 else len(raw)]
            header = raw[:m.start()]
            if b"/FlateDecode" in header:
                try:
                    data = zlib.decompress(blob)
                except zlib.error:
                    # Some producers append a trailing newline; try the trimmed variant.
                    try:
                        data = zlib.decompress(blob.rstrip(b"\r\n"))
                    except zlib.error:
                        data = b""
            elif b"/Filter" not in header:
                data = blob
        self._stream_cache[number] = data
        return data

    def _read_page_tree(self) -> list[int]:
        """Flatten the /Pages tree into physical page object numbers."""
        root_ref = re.search(rb"/Root\s+(\d+)\s+0\s+R", self._data[-8192:])
        catalog = self._object(int(root_ref.group(1)) if root_ref else 1)
        m = re.search(rb"/Pages\s+(\d+)\s+0\s+R", catalog)
        root_num = int(m.group(1)) if m else 2
        pages: list[int] = []
        visited: set[int] = set()

        def walk(number: int) -> None:
            if number in visited:
                return
            visited.add(number)
            raw = self._object(number)
            if b"/Type/Pages" in raw or b"/Type /Pages" in raw:
                kids = raw.split(b"/Kids", 1)[-1]
                close = kids.find(b"]")
                kids = kids[:close if close >= 0 else len(kids)]
                for ref in _OBJ_REF.finditer(kids):
                    walk(int(ref.group(1)))
            else:
                pages.append(number)

        walk(root_num)
        if not pages:  # incremental / unusual catalogs: fall back to xref order
            for number in sorted(self._offsets):
                raw = self._object(number)
                if b"/Type/Page" in raw and b"/Type/Pages" not in raw:
                    pages.append(number)
        return pages

    @property
    def page_count(self) -> int:
        return len(self._pages)

    # ------------------------------------------------------------------ fonts

    def _font_cmaps(self, page_number: int) -> dict[str, dict[int, str]]:
        """Map /F1-style resource names to their ToUnicode CMap (Identity-H fonts)."""
        key = str(page_number)
        if key in self._cmap_cache:
            return self._cmap_cache[key]
        raw = self._object(self._pages[page_number - 1])
        font_block = b""
        marker = raw.find(b"/Font")
        if marker >= 0:
            tail = raw[marker:]
            start = tail.find(b"<<")
            end = tail.find(b">>", start)
            font_block = tail[start:end] if start >= 0 and end >= 0 else b""
        cmaps: dict[str, dict[int, str]] = {}
        for ref in re.finditer(rb"/([^\s/<>\[\]]+)\s+(\d+)\s+0\s+R", font_block):
            name = ref.group(1).decode("latin-1")
            font = self._object(int(ref.group(2)))
            tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", font)
            if not tu:
                continue
            cmap_text = self._stream(int(tu.group(1))).decode("latin-1", "replace")
            mapping: dict[int, str] = {}
            for block in re.finditer(r"beginbfchar(.*?)endbfchar", cmap_text, re.S):
                for pair in re.finditer(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block.group(1)):
                    src = int(pair.group(1), 16)
                    dst = bytes.fromhex(pair.group(2)).decode("utf-16-be", "replace")
                    mapping[src] = dst
            for block in re.finditer(r"beginbfrange(.*?)endbfrange", cmap_text, re.S):
                for triple in re.finditer(
                    r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block.group(1)
                ):
                    lo, hi = int(triple.group(1), 16), int(triple.group(2), 16)
                    try:
                        destination = bytes.fromhex(triple.group(3))
                    except ValueError:
                        continue
                    units = [int.from_bytes(destination[i:i + 2], "big")
                             for i in range(0, len(destination) - 1, 2)]
                    if len(units) == 1:
                        base = units[0]
                        for n in range(lo, min(hi, lo + 255) + 1):
                            code = base + n - lo
                            if code < 0x110000 and not 0xD800 <= code <= 0xDFFF:
                                mapping[n] = chr(code)
                    else:
                        # Surrogate-pair destinations cannot be incremented as a
                        # scalar; map the low bound only.
                        try:
                            mapping[lo] = destination.decode("utf-16-be")
                        except UnicodeDecodeError:
                            pass
            if mapping:
                cmaps[name] = mapping
        self._cmap_cache[key] = cmaps
        return cmaps

    # ------------------------------------------------------------------ content

    def _content(self, page_number: int) -> bytes:
        raw = self._object(self._pages[page_number - 1])
        m = re.search(rb"/Contents\s+(.+)", raw)
        if not m:
            return b""
        spec = m.group(1)
        refs = [int(r.group(1)) for r in _OBJ_REF.finditer(spec.split(b"]", 1)[0] + b"]")]
        return b"\n".join(self._stream(n) for n in refs)

    def _decode_run(self, block: bytes, cmap: dict[int, str]) -> str:
        """Concatenate the strings of one BT..ET block, ignoring kerning numbers."""
        pieces: list[str] = []
        # Walk tokens in order so literal and hex strings keep their sequence.
        token = re.compile(rb"\((?:\\.|[^()\\])*\)|<[0-9A-Fa-f\s]+>|\[|\]", re.S)
        for tok in token.finditer(block):
            value = tok.group(0)
            if value.startswith(b"("):
                pieces.append(_decode_literal(value))
            elif value.startswith(b"<"):
                digits = re.sub(rb"\s+", b"", value[1:-1])
                if not digits or len(digits) % 2:
                    continue
                raw = bytes.fromhex(digits.decode("ascii"))
                if cmap:
                    wide = any(code > 0xFF for code in cmap) and len(raw) % 2 == 0
                    decoded = ("".join(
                        cmap.get(int.from_bytes(raw[i:i + 2], "big"), "")
                        for i in range(0, len(raw), 2)) if wide else
                        "".join(cmap.get(code, "") for code in raw))
                    if not decoded and len(raw) % 2 == 0:
                        decoded = "".join(
                            cmap.get(int.from_bytes(raw[i:i + 2], "big"), "")
                            for i in range(0, len(raw), 2))
                    pieces.append(decoded)
                else:
                    pieces.append(raw.decode("cp1252", "replace"))
        return "".join(pieces)

    def spans(self, page_number: int, *, min_size: float = 0.0) -> tuple[Span, ...]:
        """Return positioned text runs of one physical page (1-based)."""
        if page_number < 1 or page_number > self.page_count:
            raise IndexError(f"page {page_number} out of range (1..{self.page_count})")
        cached = self._page_cache.get(page_number)
        if cached is None:
            content = self._content(page_number)
            cmaps = self._font_cmaps(page_number)
            runs: list[Span] = []
            font, size = "", 0.0
            x = y = 0.0
            for block in _BT.finditer(content):
                body = block.group(1)
                tf = _TF.search(body)
                if tf:
                    font, size = tf.group(1).decode("latin-1"), float(tf.group(2))
                tm = _TM.search(body)
                if tm:
                    x, y = float(tm.group(5)), float(tm.group(6))
                else:
                    td = _TD.search(body)
                    if td:
                        x += float(td.group(1))
                        y += float(td.group(2))
                text = self._decode_run(body, cmaps.get(font, {}))
                if text:
                    runs.append(Span(round(x, 2), round(y, 2), size, text, font))
            cached = tuple(runs)
            self._page_cache[page_number] = cached
        if not min_size:
            return cached
        return tuple(s for s in cached if s.size >= min_size)

    def lines(self, page_number: int, *, min_size: float = 8.0,
              tolerance: float = 2.0) -> list[Line]:
        """Group runs into visual lines, ordered top to bottom, left to right."""
        runs = [s for s in self.spans(page_number, min_size=min_size)]
        runs.sort(key=lambda s: (-s.y, s.x))
        grouped: list[list[Span]] = []
        anchor = None
        for run in runs:
            if anchor is None or abs(run.y - anchor) > tolerance:
                grouped.append([run])
                anchor = run.y
            else:
                grouped[-1].append(run)
        out = []
        for group in grouped:
            group.sort(key=lambda s: s.x)
            out.append(Line(round(sum(s.y for s in group) / len(group), 2), tuple(group)))
        return out

    def iter_lines(self, first: int = 1, last: int | None = None, *,
                   min_size: float = 8.0) -> Iterator[tuple[int, Line]]:
        """Yield ``(physical_page_number, line)`` across a page range."""
        stop = min(last or self.page_count, self.page_count)
        for number in range(max(1, first), stop + 1):
            for line in self.lines(number, min_size=min_size):
                yield number, line

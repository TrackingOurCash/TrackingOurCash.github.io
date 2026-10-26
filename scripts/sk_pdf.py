"""Minimal PDF text extraction, standard library only, for the Saskatchewan Public
Accounts Volume 2 (and anything else laid out as simple text).

How it works:
  * Every "N 0 obj" in the file is indexed; objects packed inside /ObjStm object
    streams are inflated and indexed too (that is where these files keep their page
    dictionaries).
  * The page tree is walked from the root /Pages object, so pages come out in
    document order, and each page's /Contents streams are inflated (FlateDecode)
    and concatenated into one content stream.
  * The text operators are interpreted (BT/ET, Tf, Tm, Td, TD, T*, TL, Tj, TJ, ' and
    ") together with the graphics state (q, Q, cm), so each shown string gets its
    page position. Strings on the same baseline are joined into a line, lines are
    returned top to bottom, and a two-column page can be split at a gutter x so the
    left column's lines come before the right column's.
  * Strings decode as cp1252 (the fonts use WinAnsiEncoding); hex strings decode as
    UTF-16BE when that gives printable text, else cp1252. Glyph widths are not
    read; a rough 0.5 em per character estimate decides where a space goes between
    adjacent strings on a line.
If no page tree can be found the extractor falls back to walking every stream in
file order.

Usage from other scripts:
    from sk_pdf import pdf_pages
    for page in pdf_pages(path, split=306):   # list of pages, each a list of lines
        ...
Run directly to dump a file as text, one page per "=== page N" block:
    python3 scripts/sk_pdf.py file.pdf [out.txt] [column split x, e.g. 306]
"""
import re
import sys
import zlib

TOKEN = re.compile(
    rb"\((?:\\.|[^\\()])*(?:\((?:\\.|[^\\()])*\)(?:\\.|[^\\()])*)*\)"  # (string) with one level of nesting
    rb"|<[0-9A-Fa-f\s]*>"                                               # <hex>
    rb"|\[|\]"
    rb"|/[^\s/\[\]()<>{}%]*"                                            # /Name
    rb"|[-+]?(?:\d+\.?\d*|\.\d+)"                                        # number
    rb"|[A-Za-z'\"*][A-Za-z0-9'\"*]*"                                    # operator
    rb"|<<|>>"
)
ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}
OCTAL = b"01234567"


def _unescape(s):
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i:i + 1]
        if c == b"\\" and i + 1 < len(s):
            n = s[i + 1:i + 2]
            if n in ESC:
                out += ESC[n]
                i += 2
            elif n in OCTAL:
                j = i + 1
                while j < len(s) and j < i + 4 and s[j:j + 1] in OCTAL:
                    j += 1
                out.append(int(s[i + 1:j], 8) & 0xFF)
                i = j
            elif n in (b"\n", b"\r"):
                i += 2
            else:
                out += n
                i += 2
        else:
            out += c
            i += 1
    return bytes(out)


def _decode_string(tok):
    if tok.startswith(b"("):
        return _unescape(tok[1:-1]).decode("cp1252", "replace")
    h = re.sub(rb"\s", b"", tok[1:-1])
    if len(h) % 2:
        h += b"0"
    raw = bytes.fromhex(h.decode())
    if len(raw) % 2 == 0 and len(raw) >= 2:
        try:
            t = raw.decode("utf-16-be")
            if all(ch.isprintable() or ch.isspace() for ch in t):
                return t
        except UnicodeDecodeError:
            pass
    return raw.decode("cp1252", "replace")


def _inflate(raw, dict_bytes=b""):
    if b"FlateDecode" not in dict_bytes and not raw.startswith((b"x\x9c", b"x\xda", b"x\x01", b"x^")):
        return raw
    try:
        return zlib.decompress(raw)
    except zlib.error:
        try:
            return zlib.decompressobj().decompress(raw)
        except zlib.error:
            return b""


# ---------------------------------------------------------------- object index

def _objects(data):
    """{object number: (dictionary bytes, raw stream bytes or None)}, including the
    objects packed in object streams. Later definitions win (incremental updates)."""
    objs = {}
    for m in re.finditer(rb"(?<![0-9A-Za-z])(\d+)\s+\d+\s+obj\b", data):
        num = int(m.group(1))
        start = m.end()
        sm = re.compile(rb"stream\r?\n").search(data, start)
        eo = data.find(b"endobj", start)
        if sm and (eo < 0 or sm.start() < eo):
            dict_part = data[start:sm.start()]
            end = data.find(b"endstream", sm.end())
            raw = data[sm.end():end]
            if raw.endswith(b"\r\n"):
                raw = raw[:-2]
            elif raw.endswith(b"\n"):
                raw = raw[:-1]
            objs[num] = (dict_part, raw)
        else:
            objs[num] = (data[start:eo] if eo >= 0 else data[start:], None)
    for num, (d, raw) in list(objs.items()):
        if raw is None or b"/ObjStm" not in d:
            continue
        content = _inflate(raw, d)
        mn = re.search(rb"/N\s+(\d+)", d)
        mf = re.search(rb"/First\s+(\d+)", d)
        if not (mn and mf):
            continue
        first = int(mf.group(1))
        header = content[:first].split()
        pairs = [(int(header[i]), int(header[i + 1])) for i in range(0, len(header) - 1, 2)]
        for i, (onum, off) in enumerate(pairs):
            end = pairs[i + 1][1] if i + 1 < len(pairs) else len(content) - first
            objs.setdefault(onum, (content[first + off:first + end], None))
    return objs


def _refs(d, key):
    """Object numbers referenced by /key in dictionary bytes d (single ref or array)."""
    m = re.search(rb"/" + key + rb"\s*(\[[^\]]*\]|\d+\s+\d+\s+R)", d)
    if not m:
        return []
    return [int(x) for x in re.findall(rb"(\d+)\s+\d+\s+R", m.group(1))]


def page_contents(data):
    """-> list of content-stream bytes, one per page in document order; [] if the
    page tree cannot be found."""
    objs = _objects(data)
    roots = [n for n, (d, _) in objs.items() if re.search(rb"/Type\s*/Pages\b", d) and b"/Parent" not in d]
    if not roots:
        return []
    pages = []
    seen = set()

    def walk(num):
        if num in seen or num not in objs:
            return
        seen.add(num)
        d, _ = objs[num]
        if re.search(rb"/Type\s*/Page\b", d):
            parts = []
            for c in _refs(d, b"Contents"):
                cd, raw = objs.get(c, (b"", None))
                if raw is None:
                    # /Contents pointing at an array object
                    for c2 in re.findall(rb"(\d+)\s+\d+\s+R", cd):
                        cd2, raw2 = objs.get(int(c2), (b"", None))
                        if raw2 is not None:
                            parts.append(_inflate(raw2, cd2))
                else:
                    parts.append(_inflate(raw, cd))
            pages.append(b"\n".join(parts))
        else:
            for k in _refs(d, b"Kids"):
                walk(k)

    for r in roots:
        walk(r)
    return pages


def iter_streams(data):
    """Fallback: every stream's inflated bytes in file order."""
    pos = 0
    pat = re.compile(rb"stream\r?\n")
    while True:
        m = pat.search(data, pos)
        if not m:
            return
        end = data.find(b"endstream", m.end())
        if end < 0:
            return
        pos = end + 9
        yield _inflate(data[m.end():end])


# ---------------------------------------------------------------- text operators

def _mul(m, n):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + b * c2, a * b2 + b * d2, c * a2 + d * c2, c * b2 + d * d2,
            e * a2 + f * c2 + e2, e * b2 + f * d2 + f2)


IDENT = (1, 0, 0, 1, 0, 0)


def stream_text_items(content):
    """-> list of (y, x, size, text) for every string shown in one content stream."""
    items = []
    ctm = IDENT
    ctm_stack = []
    tm = tlm = IDENT
    size, leading = 1.0, 0.0
    stack = []
    in_array = None

    def show(text):
        a, b, c, d, e, f = _mul(tm, ctm)
        fs = abs(size * (d if d else a)) or 1.0
        items.append((round(f, 1), e, fs, text))

    def advance(text):
        nonlocal tm
        tm = _mul((1, 0, 0, 1, 0.5 * size * len(text), 0), tm)

    for t in TOKEN.findall(content):
        if in_array is not None:
            if t == b"]":
                s = "".join(in_array)
                show(s)
                advance(s)
                in_array = None
            elif t[:1] in (b"(", b"<") and t != b"<<":
                in_array.append(_decode_string(t))
            else:
                try:
                    if float(t) < -200:
                        in_array.append(" ")
                except ValueError:
                    pass
            continue
        if t == b"[":
            in_array = []
            stack = []
        elif t[:1] in (b"(", b"<", b"/") or t in (b"<<", b">>") or re.match(rb"^[-+]?(\d|\.)", t):
            stack.append(t)
        else:
            op = t
            try:
                if op == b"BT":
                    tm = tlm = IDENT
                elif op == b"q":
                    ctm_stack.append(ctm)
                elif op == b"Q":
                    if ctm_stack:
                        ctm = ctm_stack.pop()
                elif op == b"cm" and len(stack) >= 6:
                    ctm = _mul(tuple(float(x) for x in stack[-6:]), ctm)
                elif op == b"Tf":
                    size = float(stack[-1])
                elif op == b"TL":
                    leading = float(stack[-1])
                elif op == b"Tm" and len(stack) >= 6:
                    tm = tlm = tuple(float(x) for x in stack[-6:])
                elif op in (b"Td", b"TD"):
                    tx, ty = float(stack[-2]), float(stack[-1])
                    if op == b"TD":
                        leading = -ty
                    tm = tlm = _mul((1, 0, 0, 1, tx, ty), tlm)
                elif op == b"T*":
                    tm = tlm = _mul((1, 0, 0, 1, 0, -leading), tlm)
                elif op == b"Tj":
                    s = _decode_string(stack[-1])
                    show(s)
                    advance(s)
                elif op in (b"'", b'"'):
                    tm = tlm = _mul((1, 0, 0, 1, 0, -leading), tlm)
                    s = _decode_string(stack[-1])
                    show(s)
                    advance(s)
            except (ValueError, IndexError):
                pass
            stack = []
    return items


def items_to_lines(items, y_tol=2.0):
    """Group positioned strings into text lines, top of page first, left to right."""
    items = sorted(items, key=lambda it: (-it[0], it[1]))
    lines = []
    cur, cur_y = [], None
    for y, x, fs, text in items:
        if cur_y is None or abs(y - cur_y) > y_tol:
            if cur:
                lines.append(cur)
            cur, cur_y = [], y
        cur.append((x, fs, text))
    if cur:
        lines.append(cur)
    out = []
    for line in lines:
        line.sort(key=lambda it: it[0])
        s = ""
        end_x = None
        for x, fs, text in line:
            if not text:
                continue
            if end_x is not None and x - end_x > 0.25 * fs and not s.endswith(" ") and not text.startswith(" "):
                s += " "
            s += text
            end_x = x + 0.5 * fs * len(text)
        s = re.sub(r"[ \t ]+", " ", s).strip()
        if s:
            out.append(s)
    return out


def _printable_share(items):
    text = "".join(t for _, _, _, t in items)
    if not text:
        return 0.0
    return sum(ch.isprintable() or ch.isspace() for ch in text) / len(text)


def pdf_pages(path, split=None, landscape_x=620):
    """-> list of pages, each a list of line strings, in document order.

    split: x coordinate of the gutter for two-column pages; lines left of it come
    first, then the right column. Pages wider than landscape_x (the summary tables)
    are never split. Streams that are not readable text are dropped."""
    data = open(path, "rb").read()
    contents = page_contents(data)
    if not contents:
        contents = [c for c in iter_streams(data) if b"BT" in c and (b"Tj" in c or b"TJ" in c)]
    pages = []
    for content in contents:
        items = stream_text_items(content)
        if not items or _printable_share(items) < 0.95:
            pages.append([])
            continue
        if split is not None and max(x for _, x, _, _ in items) < landscape_x:
            lines = items_to_lines([it for it in items if it[1] < split]) + \
                items_to_lines([it for it in items if it[1] >= split])
        else:
            lines = items_to_lines(items)
        pages.append(lines)
    return pages


if __name__ == "__main__":
    split = float(sys.argv[3]) if len(sys.argv) > 3 else None
    pages = pdf_pages(sys.argv[1], split=split)
    out = open(sys.argv[2], "w") if len(sys.argv) > 2 else sys.stdout
    for n, page in enumerate(pages, 1):
        print(f"=== page {n}", file=out)
        for line in page:
            print(line, file=out)
    print(len(pages), "pages", file=sys.stderr)

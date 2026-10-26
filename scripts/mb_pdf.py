"""PDF text extraction for Manitoba's "Vendor Payments over $50,000" statements,
standard library only. Built on sk_pdf.py, with two additions that file needs:

  * Fonts with a /ToUnicode CMap are decoded through it. The 2023-24 statement was
    produced with subset fonts whose character codes start at 33 and bear no relation
    to ASCII (the string "!"#$%" is the word "VENDO"); the other years use
    WinAnsi-encoded fonts, which sk_pdf's cp1252 decoding reads directly. Each page's
    /Resources /Font dictionary is read so the font named by Tf selects the CMap.
  * The page tree is rebuilt when an incremental update left a stale root. The
    2023-24 file's root /Pages object lists only the two cover pages; the real
    intermediate nodes still point at it as their /Parent, so they are walked too,
    in object-number order.

Usage:
    from mb_pdf import pdf_items
    for items in pdf_items(path):      # one list of (y, x, size, text) per page
        ...
Run directly to dump a file: python3 scripts/mb_pdf.py file.pdf [out.txt]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sk_pdf import TOKEN, _decode_string, _inflate, _mul, _objects, _refs, _unescape, items_to_lines  # noqa: E402

IDENT = (1, 0, 0, 1, 0, 0)
HEX = re.compile(rb"<([0-9A-Fa-f]*)>")


def _cmap(data):
    """ToUnicode CMap bytes -> {code (int): str}. Single-byte and two-byte codes."""
    out = {}

    def uni(h):
        h = re.sub(rb"\s", b"", h)
        if len(h) % 4:
            h += b"0" * (4 - len(h) % 4)
        try:
            return bytes.fromhex(h.decode()).decode("utf-16-be", "replace")
        except ValueError:
            return ""

    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        toks = HEX.findall(block)
        for i in range(0, len(toks) - 1, 2):
            out[int(toks[i], 16)] = uni(toks[i + 1])
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        pos = 0
        while True:
            m = re.compile(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]*>|\[[^\]]*\])").search(block, pos)
            if not m:
                break
            pos = m.end()
            lo, hi = int(m.group(1), 16), int(m.group(2), 16)
            dst = m.group(3)
            if dst.startswith(b"["):
                items = HEX.findall(dst)
                for i, code in enumerate(range(lo, hi + 1)):
                    if i < len(items):
                        out[code] = uni(items[i])
            else:
                base = uni(dst[1:-1])
                for i, code in enumerate(range(lo, hi + 1)):
                    if base:
                        out[code] = base[:-1] + chr(ord(base[-1]) + i)
    return out


def _font_maps(objs, page_dict):
    """{font resource name: cmap or None} for one page."""
    res = page_dict
    refs = _refs(page_dict, b"Resources")
    if refs and refs[0] in objs:
        res = objs[refs[0]][0]
    m = re.search(rb"/Font\s*(<<.*?>>|\d+\s+\d+\s+R)", res, re.S)
    if not m:
        return {}
    fd = m.group(1)
    if not fd.startswith(b"<<"):
        n = int(fd.split()[0])
        fd = objs.get(n, (b"", None))[0]
    maps = {}
    for name, num in re.findall(rb"/([^\s/<>\[\]()]+)\s+(\d+)\s+\d+\s+R", fd):
        fobj = objs.get(int(num))
        if not fobj:
            continue
        tu = _refs(fobj[0], b"ToUnicode")
        cm = None
        if tu and tu[0] in objs and objs[tu[0]][1] is not None:
            d, raw = objs[tu[0]]
            cm = _cmap(_inflate(raw, d))
            # An identity map (WinAnsi subset) adds nothing; keep cp1252 decoding then.
            if cm and all(chr(k) == v for k, v in cm.items() if 32 <= k < 127):
                cm = None
        maps[name.decode("latin1")] = cm
    return maps


def _decode(tok, cm):
    if cm is None:
        return _decode_string(tok)
    if tok.startswith(b"("):
        raw = _unescape(tok[1:-1])
    else:
        h = re.sub(rb"\s", b"", tok[1:-1])
        raw = bytes.fromhex((h + (b"0" if len(h) % 2 else b"")).decode())
    return "".join(cm.get(b, "�") for b in raw)


def text_items(content, fonts):
    """-> [(y, x, size, text)] for one content stream, like sk_pdf.stream_text_items
    but decoding strings through the current font's ToUnicode map when it has one."""
    items = []
    ctm, ctm_stack = IDENT, []
    tm = tlm = IDENT
    size, leading = 1.0, 0.0
    cm = None
    stack, in_array = [], None

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
                in_array.append(_decode(t, cm))
            else:
                try:
                    if float(t) < -200:
                        in_array.append(" ")
                except ValueError:
                    pass
            continue
        if t == b"[":
            in_array, stack = [], []
        elif t[:1] in (b"(", b"<", b"/") or t in (b"<<", b">>") or re.match(rb"^[-+]?(\d|\.)", t):
            stack.append(t)
        else:
            try:
                if t == b"BT":
                    tm = tlm = IDENT
                elif t == b"q":
                    ctm_stack.append(ctm)
                elif t == b"Q":
                    if ctm_stack:
                        ctm = ctm_stack.pop()
                elif t == b"cm" and len(stack) >= 6:
                    ctm = _mul(tuple(float(x) for x in stack[-6:]), ctm)
                elif t == b"Tf":
                    size = float(stack[-1])
                    cm = fonts.get(stack[-2][1:].decode("latin1")) if len(stack) >= 2 else None
                elif t == b"TL":
                    leading = float(stack[-1])
                elif t == b"Tm" and len(stack) >= 6:
                    tm = tlm = tuple(float(x) for x in stack[-6:])
                elif t in (b"Td", b"TD"):
                    tx, ty = float(stack[-2]), float(stack[-1])
                    if t == b"TD":
                        leading = -ty
                    tm = tlm = _mul((1, 0, 0, 1, tx, ty), tlm)
                elif t == b"T*":
                    tm = tlm = _mul((1, 0, 0, 1, 0, -leading), tlm)
                elif t == b"Tj":
                    s = _decode(stack[-1], cm)
                    show(s)
                    advance(s)
                elif t in (b"'", b'"'):
                    tm = tlm = _mul((1, 0, 0, 1, 0, -leading), tlm)
                    s = _decode(stack[-1], cm)
                    show(s)
                    advance(s)
            except (ValueError, IndexError):
                pass
            stack = []
    return items


def page_order(objs):
    """Page object numbers in document order, tolerating a stale root node."""
    nodes = {n: d for n, (d, _) in objs.items() if re.search(rb"/Type\s*/Pages\b", d)}
    roots = [n for n, d in nodes.items() if b"/Parent" not in d]
    pages, seen = [], set()

    def walk(num):
        if num in seen or num not in objs:
            return
        seen.add(num)
        d = objs[num][0]
        if re.search(rb"/Type\s*/Page\b", d):
            pages.append(num)
            return
        for k in _refs(d, b"Kids"):
            walk(k)
        # Nodes that name this one as parent but are missing from its Kids list.
        for k in sorted(n for n, nd in nodes.items() if n not in seen and _refs(nd, b"Parent") == [num]):
            walk(k)

    for r in sorted(roots):
        walk(r)
    return pages


def pdf_items(path):
    """-> list of pages, each a list of (y, x, size, text) items."""
    data = Path(path).read_bytes()
    objs = _objects(data)
    out = []
    for num in page_order(objs):
        d = objs[num][0]
        parts = []
        for c in _refs(d, b"Contents"):
            cd, raw = objs.get(c, (b"", None))
            if raw is None:
                for c2 in re.findall(rb"(\d+)\s+\d+\s+R", cd):
                    cd2, raw2 = objs.get(int(c2), (b"", None))
                    if raw2 is not None:
                        parts.append(_inflate(raw2, cd2))
            else:
                parts.append(_inflate(raw, cd))
        out.append(text_items(b"\n".join(parts), _font_maps(objs, d)))
    return out


if __name__ == "__main__":
    pages = pdf_items(sys.argv[1])
    out = open(sys.argv[2], "w") if len(sys.argv) > 2 else sys.stdout
    for n, items in enumerate(pages, 1):
        print(f"=== page {n}", file=out)
        for line in items_to_lines(items):
            print(line, file=out)
    print(len(pages), "pages", file=sys.stderr)

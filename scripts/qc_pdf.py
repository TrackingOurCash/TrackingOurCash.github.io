"""Read Québec's encrypted Comptes publics PDFs with sk_pdf, standard library only.

The Ministère des Finances publishes the Comptes publics volumes as PDFs encrypted with
the standard security handler, revision 6 (AES-256, /CFM /AESV3) and an empty user
password: any viewer opens them, but every stream (object streams, page contents) is
AES-CBC ciphertext, so sk_pdf.pdf_pages sees no readable page. This module implements
what is needed to open them without third-party packages:

  * AES-128/256 block cipher (FIPS-197, straightforward table-free implementation; it is
    slow but only the object streams and page content streams are decrypted, never the
    images, so a 400-page volume takes well under a minute);
  * ISO 32000-2 algorithm 2.B (the SHA-256/384/512 + AES-128-CBC iteration that turns a
    password and salt into an intermediate key) and the recovery of the file key from the
    /UE string with the empty user password;
  * a hook that wraps sk_pdf._inflate so each stream is decrypted (16-byte IV, AES-256-CBC,
    PKCS#5 padding) before it is inflated. Strings in dictionaries are also encrypted but
    are never needed for text extraction (the text sits inside content streams).

Usage:
    from qc_pdf import pdf_pages
    pages = pdf_pages("data/raw/qc/CPTFR_vol2-2024-2025.pdf")   # list of pages, list of lines
Unencrypted files pass straight through to sk_pdf.pdf_pages. Run directly to dump a file:
    python3 scripts/qc_pdf.py file.pdf [out.txt]
"""
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sk_pdf  # noqa: E402

# ---------------------------------------------------------------- AES (FIPS-197)

SBOX = [0] * 256
INV_SBOX = [0] * 256


def _init_sbox():
    p = q = 1
    while True:
        # multiply p by 3
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        # divide q by 3
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ (q << 1) ^ (q << 2) ^ (q << 3) ^ (q << 4)
        x = (x ^ (x >> 8) ^ 0x63) & 0xFF
        SBOX[p] = x
        INV_SBOX[x] = p
        if p == 1:
            break
    SBOX[0] = 0x63
    INV_SBOX[0x63] = 0


_init_sbox()


def _xtime(a):
    a <<= 1
    return (a ^ 0x1B) & 0xFF if a & 0x100 else a


def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


MUL2 = [_mul(i, 2) for i in range(256)]
MUL3 = [_mul(i, 3) for i in range(256)]
MUL9 = [_mul(i, 9) for i in range(256)]
MUL11 = [_mul(i, 11) for i in range(256)]
MUL13 = [_mul(i, 13) for i in range(256)]
MUL14 = [_mul(i, 14) for i in range(256)]


def _expand_key(key):
    nk = len(key) // 4
    rounds = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (rounds + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = [SBOX[t[1]] ^ rcon, SBOX[t[2]], SBOX[t[3]], SBOX[t[0]]]
            rcon = _xtime(rcon)
        elif nk > 6 and i % nk == 4:
            t = [SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    round_keys = []
    for r in range(rounds + 1):
        round_keys.append([b for col in w[4 * r:4 * r + 4] for b in col])
    return round_keys


def _add(state, rk):
    return [s ^ k for s, k in zip(state, rk)]


def _shift_rows(s):
    return [s[0], s[5], s[10], s[15], s[4], s[9], s[14], s[3], s[8], s[13], s[2], s[7], s[12], s[1], s[6], s[11]]


def _inv_shift_rows(s):
    return [s[0], s[13], s[10], s[7], s[4], s[1], s[14], s[11], s[8], s[5], s[2], s[15], s[12], s[9], s[6], s[3]]


def _mix_columns(s):
    out = []
    for c in range(4):
        a0, a1, a2, a3 = s[4 * c:4 * c + 4]
        out += [MUL2[a0] ^ MUL3[a1] ^ a2 ^ a3, a0 ^ MUL2[a1] ^ MUL3[a2] ^ a3,
                a0 ^ a1 ^ MUL2[a2] ^ MUL3[a3], MUL3[a0] ^ a1 ^ a2 ^ MUL2[a3]]
    return out


def _inv_mix_columns(s):
    out = []
    for c in range(4):
        a0, a1, a2, a3 = s[4 * c:4 * c + 4]
        out += [MUL14[a0] ^ MUL11[a1] ^ MUL13[a2] ^ MUL9[a3], MUL9[a0] ^ MUL14[a1] ^ MUL11[a2] ^ MUL13[a3],
                MUL13[a0] ^ MUL9[a1] ^ MUL14[a2] ^ MUL11[a3], MUL11[a0] ^ MUL13[a1] ^ MUL9[a2] ^ MUL14[a3]]
    return out


class AES:
    def __init__(self, key):
        self.rk = _expand_key(key)
        self.rounds = len(self.rk) - 1

    def encrypt_block(self, block):
        s = _add(list(block), self.rk[0])
        for r in range(1, self.rounds):
            s = _add(_mix_columns(_shift_rows([SBOX[b] for b in s])), self.rk[r])
        s = _add(_shift_rows([SBOX[b] for b in s]), self.rk[self.rounds])
        return bytes(s)

    def decrypt_block(self, block):
        s = _add(list(block), self.rk[self.rounds])
        for r in range(self.rounds - 1, 0, -1):
            s = _inv_mix_columns(_add([INV_SBOX[b] for b in _inv_shift_rows(s)], self.rk[r]))
        s = _add([INV_SBOX[b] for b in _inv_shift_rows(s)], self.rk[0])
        return bytes(s)

    def cbc_encrypt(self, data, iv):
        out = bytearray()
        prev = iv
        for i in range(0, len(data) - len(data) % 16, 16):
            prev = self.encrypt_block(bytes(a ^ b for a, b in zip(data[i:i + 16], prev)))
            out += prev
        return bytes(out)

    def cbc_decrypt(self, data, iv):
        out = bytearray()
        prev = iv
        for i in range(0, len(data) - len(data) % 16, 16):
            blk = data[i:i + 16]
            out += bytes(a ^ b for a, b in zip(self.decrypt_block(blk), prev))
            prev = blk
        return bytes(out)


# ---------------------------------------------------------------- ISO 32000-2 R6 keys

def _hash_2b(password, salt, udata=b""):
    k = hashlib.sha256(password + salt + udata).digest()
    i = 0
    while True:
        k1 = (password + k + udata) * 64
        e = AES(k[:16]).cbc_encrypt(k1, k[16:32])
        mod = sum(e[:16]) % 3
        k = (hashlib.sha256, hashlib.sha384, hashlib.sha512)[mod](e).digest()
        i += 1
        if i >= 64 and e[-1] <= i - 32:
            break
    return k[:32]


def _pdf_string(tok):
    """Bytes of a literal (..) or <hex> string token."""
    tok = tok.strip()
    if tok.startswith(b"<"):
        return bytes.fromhex(re.sub(rb"\s", b"", tok[1:-1]).decode())
    return sk_pdf._unescape(tok[1:-1])


def file_key(data, password=b""):
    """The AES-256 file key of a revision-6 encrypted PDF, or None when it is not encrypted
    (or uses an older handler)."""
    m = re.search(rb"/Encrypt\s+(\d+)\s+\d+\s+R", data)
    if not m:
        return None
    objs = sk_pdf._objects(data)
    enc = objs.get(int(m.group(1)), (b"", None))[0]
    r = re.search(rb"/R\s+(\d+)", enc)
    if not r or int(r.group(1)) < 5:
        raise ValueError("only revision 5/6 (AES-256) encryption is supported")
    strings = {}
    for key in (b"U", b"UE", b"O", b"OE"):
        sm = re.search(rb"/" + key + rb"\s*(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)", enc)
        strings[key] = _pdf_string(sm.group(1))
    u, ue = strings[b"U"], strings[b"UE"]
    validation_salt, key_salt = u[32:40], u[40:48]
    if int(r.group(1)) == 5:
        hashed = hashlib.sha256(password + validation_salt).digest()
        inter = hashlib.sha256(password + key_salt).digest()
    else:
        hashed = _hash_2b(password, validation_salt)
        inter = _hash_2b(password, key_salt)
    if hashed != u[:32]:
        raise ValueError("user password does not validate")
    return AES(inter).cbc_decrypt(ue[:32], bytes(16))


def decrypt_stream(raw, key):
    if len(raw) < 32:
        return b""
    body = AES(key).cbc_decrypt(raw[16:], raw[:16])
    if body and 1 <= body[-1] <= 16:
        body = body[:-body[-1]]
    return body


def _cmap(objs, font_dict):
    """{code: text} from a font's ToUnicode CMap, or None when it has none."""
    m = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", font_dict)
    if not m or int(m.group(1)) not in objs:
        return None
    td, tr = objs[int(m.group(1))]
    body = sk_pdf._inflate(tr or b"", td)
    cmap = {}
    for blk in re.finditer(rb"beginbfchar(.*?)endbfchar", body, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk.group(1)):
            cmap.setdefault(int(src, 16), bytes.fromhex(dst.decode()).decode("utf-16-be", "replace"))
    for blk in re.finditer(rb"beginbfrange(.*?)endbfrange", body, re.S):
        for lo, hi, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk.group(1)):
            lo, hi = int(lo, 16), int(hi, 16)
            base = bytes.fromhex(dst.decode()).decode("utf-16-be", "replace")
            for c in range(lo, min(hi, lo + 255) + 1):
                cmap.setdefault(c, base[:-1] + chr(ord(base[-1]) + c - lo) if base else "")
        for lo, hi, arr in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", blk.group(1), re.S):
            for k, dst in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", arr)):
                cmap.setdefault(int(lo, 16) + k, bytes.fromhex(dst.decode()).decode("utf-16-be", "replace"))
    return cmap


def _literal(text):
    """A PDF literal string (cp1252, escaped) for text."""
    raw = text.encode("cp1252", "replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _recode(content, fonts):
    """Rewrite every shown string of a content stream as a cp1252 literal using the
    current font's ToUnicode map (fonts: resource name -> (cmap or None, two_byte))."""
    out = bytearray()
    pos = 0
    font = None
    pending = None
    for m in sk_pdf.TOKEN.finditer(content):
        tok = m.group(0)
        if tok.startswith(b"/"):
            pending = tok[1:]
        elif tok == b"Tf":
            font = fonts.get(pending)
        elif tok[:1] in b"(<" and tok not in (b"<<",) and font and font[0]:
            cmap, two = font
            raw = bytes.fromhex(re.sub(rb"\s", b"", tok[1:-1]).decode()) if tok.startswith(b"<") else sk_pdf._unescape(tok[1:-1])
            if two:
                codes = [int.from_bytes(raw[k:k + 2], "big") for k in range(0, len(raw) - 1, 2)]
            else:
                codes = list(raw)
            text = "".join(cmap.get(c, "\ufffd") for c in codes)
            out += content[pos:m.start()] + _literal(text)
            pos = m.end()
    out += content[pos:]
    return bytes(out)


def _pages_with_fonts(data):
    """[(content bytes, {font resource name: (cmap, two_byte)})] in document order."""
    objs = sk_pdf._objects(data)
    roots = [n for n, (d, _) in objs.items() if re.search(rb"/Type\s*/Pages\b", d) and b"/Parent" not in d]
    font_cache = {}

    def font_entry(num):
        if num not in font_cache:
            d = objs.get(num, (b"", None))[0]
            font_cache[num] = (_cmap(objs, d), b"/Type0" in d)
        return font_cache[num]

    def fonts_of(resources):
        """resources: dict bytes or reference; -> {name: (cmap, two_byte)}"""
        rm = re.match(rb"\s*(\d+)\s+0\s+R", resources or b"")
        if rm:
            resources = objs.get(int(rm.group(1)), (b"", None))[0]
        fm = re.search(rb"/Font\s*(<<.*?>>|\d+\s+0\s+R)", resources or b"", re.S)
        if not fm:
            return {}
        fd = fm.group(1)
        if not fd.startswith(b"<<"):
            fd = objs.get(int(fd.split()[0]), (b"", None))[0]
        return {name: font_entry(int(num)) for name, num in re.findall(rb"/([^\s/\[\]()<>]+)\s+(\d+)\s+0\s+R", fd)}

    pages, seen = [], set()

    def resources_of(d):
        m = re.search(rb"/Resources\s*(<<(?:[^<>]|<<(?:[^<>]|<<[^<>]*>>)*>>)*>>|\d+\s+0\s+R)", d, re.S)
        return m.group(1) if m else None

    def walk(num, inherited):
        if num in seen or num not in objs:
            return
        seen.add(num)
        d, _ = objs[num]
        res = resources_of(d) or inherited
        if re.search(rb"/Type\s*/Page\b", d):
            parts = []
            for c in sk_pdf._refs(d, b"Contents"):
                cd, raw = objs.get(c, (b"", None))
                if raw is None:
                    for c2 in re.findall(rb"(\d+)\s+\d+\s+R", cd):
                        cd2, raw2 = objs.get(int(c2), (b"", None))
                        if raw2 is not None:
                            parts.append(sk_pdf._inflate(raw2, cd2))
                else:
                    parts.append(sk_pdf._inflate(raw, cd))
            pages.append((b"\n".join(parts), fonts_of(res)))
        else:
            for k in sk_pdf._refs(d, b"Kids"):
                walk(k, res)

    for r in roots:
        walk(r, None)
    return pages


def pdf_pages(path, sizes=False):
    """-> list of pages, each a list of line strings (sk_pdf.pdf_pages's shape), for an
    AES-256 encrypted (empty user password) or plain PDF, with each font's ToUnicode map
    applied: the Comptes publics tables are set in CID fonts (Identity-H hex strings of
    glyph ids) whose glyph numbering differs from font to font, so the strings are
    decoded per font before sk_pdf lays the page out."""
    data = open(path, "rb").read()
    key = file_key(data)
    original = sk_pdf._inflate

    def inflate(raw, dict_bytes=b""):
        if key is None or re.search(rb"/Type\s*/XRef", dict_bytes):
            return original(raw, dict_bytes)
        return original(decrypt_stream(raw, key), dict_bytes)

    sk_pdf._inflate = inflate
    try:
        pages = []
        for content, fonts in _pages_with_fonts(data):
            items = sk_pdf.stream_text_items(_recode(content, fonts))
            if not items or sk_pdf._printable_share(items) < 0.9:
                pages.append([])
                continue
            pages.append(sk_pdf.items_to_lines(items, sizes=sizes))
        return pages
    finally:
        sk_pdf._inflate = original


if __name__ == "__main__":
    pages = pdf_pages(sys.argv[1])
    out = open(sys.argv[2], "w") if len(sys.argv) > 2 else sys.stdout
    for n, page in enumerate(pages, 1):
        print(f"=== page {n}", file=out)
        for line in page:
            print(line, file=out)
    print(len(pages), "pages", sum(1 for p in pages if p), "readable", file=sys.stderr)

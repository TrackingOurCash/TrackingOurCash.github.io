"""The Sources page: every dataset behind every page, in one place.

Two lists per page, both gathered automatically so the page never falls behind the code:
  * "Cited on the page": the links in that page's notes (the human-readable source list).
  * "Read by the build": every URL the build scripts for that page download or query
    (run.sh curl lines and the URLs written into scripts/*.py).
A last section lists the curated reference files (cabinets, budgets, seat counts) with the
sources recorded inside them.
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Which scripts feed which page (by NAV href). fed_prov_spending.py places federal grants on provincial maps.
PAGE_SCRIPTS = {
    "index.html": ["build_spending.py", "trim_grants.py", "contracts.py", "population.py", "fetch_shapes.py", "fetch_csd.py",
                   "prep_ridings.py", "budget.py", "geo.py", "wiki_links.py"],
    "alberta.html": ["ab_prep.py", "ab_spending.py"],
    "bc.html": ["bc_prep.py", "bc_spending.py"],
    "saskatchewan.html": ["sk_prep.py", "sk_spending.py", "sk_pdf.py"],
    "manitoba.html": ["mb_prep.py", "mb_spending.py"],
    "ontario.html": ["on_prep.py", "on_spending.py"],
    "quebec.html": ["qc_prep.py", "qc_pdf.py", "fed_prov_spending.py"],
    "nb.html": ["nb_prep.py", "nb_spending.py"],
    "pei.html": ["pe_prep.py", "fed_prov_spending.py"],
    "ns.html": ["ns_prep.py", "ns_spending.py"],
    "nl.html": ["nl_prep.py", "fed_prov_spending.py"],
    "yukon.html": ["yt_prep.py", "territories.py", "fed_prov_spending.py"],
    "nwt.html": ["nt_prep.py", "territories.py", "fed_prov_spending.py"],
    "nunavut.html": ["nu_prep.py", "territories.py", "fed_prov_spending.py"],
    "international.html": ["intl_prep.py", "intl_spending.py"],
}
# run.sh curl lines go to the page whose raw folder they write into; everything else is federal.
RUN_SH_DIRS = {"/ab/": "alberta.html"}
CURATED = [
    ("data/ministers.json", "Cabinets and ministers' ridings (all pages)"),
    ("data/fiscal_history.json", "Budgets, deficits and debt (all pages)"),
    ("data/legislatures.json", "Seat counts in each legislature (all pages)"),
    ("data/budget_items.json", "Federal budget commitments by riding (federal page)"),
    ("data/equalization.json", "Equalization payments (federal page)"),
    ("data/pe_results.json", "PEI 2023 election results"),
    ("data/formula_programs.json", "Programs treated as formula money (all pages)"),
]
SKIP_HOSTS = {"claude.ai", "schemas.openxmlformats.org", "duckduckgo.com", "www.w3.org", "www.google.com"}
URL = re.compile(r"https?://[^\s\"'<>()\\]+")


def clean(u):
    u = u.rstrip(".,;:'\"")
    if "{" in u or "}" in u or "%s" in u or "%(" in u or "$" in u:
        return None
    # Bare hosts and half-built query stems (an API base the script appends to) say nothing on their own.
    parts = u.split("/", 3)
    if len(parts) < 4 or not parts[3] or re.search(r"[?=&]$|/wiki/$", u):
        return None
    host = u.split("/")[2] if u.count("/") >= 2 else ""
    return None if host in SKIP_HOSTS or not host else u


def run_sh_urls():
    """curl targets in run.sh, with its shell variables expanded."""
    text = (ROOT / "run.sh").read_text()
    env = dict(re.findall(r"^([A-Z_]+)=(\S+)$", text, flags=re.M))
    out = {}
    for line in text.splitlines():
        if "curl" not in line:
            continue
        line = re.sub(r"\$\{?([A-Z_]+)\}?", lambda m: env.get(m.group(1), m.group(0)), line)
        page = next((p for d, p in RUN_SH_DIRS.items() if d in line), "index.html")
        for u in URL.findall(line):
            u = clean(u)
            if u:
                out.setdefault(page, []).append((u, "run.sh"))
    return out


def script_urls(name):
    path = ROOT / "scripts" / name
    if not path.exists():
        return []
    return [(u, name) for u in (clean(x) for x in URL.findall(path.read_text())) if u]


def note_links(notes):
    seen, out = set(), []
    for n in notes:
        for href, text in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', n or "", flags=re.S):
            href = clean(html.unescape(href))
            if href and href not in seen:
                seen.add(href)
                out.append((re.sub(r"<[^>]+>", "", text).strip() or href, href))
    return out


def short(u, n=90):
    s = re.sub(r"^https?://(www\.)?", "", u)
    return s if len(s) <= n else s[: n - 1] + "…"


def build(pages, nav, head, nav_urls=None):
    """pages: [(href, label, [notes html])]. Returns the page body (head + markup + script), ready to wrap."""
    runsh = run_sh_urls()
    sections = []
    total = set()
    for href, label, notes in pages:
        cited = note_links(notes)
        read, seen = [], {u for _, u in cited}
        for u, src in runsh.get(href, []) + [x for s in PAGE_SCRIPTS.get(href, []) for x in script_urls(s)]:
            if u not in seen:
                seen.add(u)
                read.append((u, src))
        total |= seen
        page_link = (nav_urls or {}).get(href, href)
        sections.append(
            f'<section class="card src" id="{html.escape(href.split(".")[0])}"><h2><a href="{html.escape(page_link)}">{html.escape(label)}</a></h2>'
            + (f'<h3>Cited on the page</h3><ul>{"".join(f"<li><a href={json.dumps(u)} target=_blank rel=noopener>{html.escape(t)}</a> <span class=muted>{html.escape(short(u))}</span></li>" for t, u in cited)}</ul>' if cited else "")
            + (f'<h3>Read by the build</h3><ul>{"".join(f"<li><a href={json.dumps(u)} target=_blank rel=noopener>{html.escape(short(u))}</a> <span class=muted>{html.escape(s)}</span></li>" for u, s in read)}</ul>' if read else "")
            + "</section>")
    cur = []
    for path, label in CURATED:
        p = ROOT / path
        if not p.exists():
            continue
        urls = []
        for u in URL.findall(p.read_text()):
            u = clean(u)
            if u and u not in urls:
                urls.append(u)
        total |= set(urls)
        cur.append(f'<h3>{html.escape(label)} <span class="muted">({html.escape(path)})</span></h3>'
                   + (f'<ul>{"".join(f"<li><a href={json.dumps(u)} target=_blank rel=noopener>{html.escape(short(u))}</a></li>" for u in urls)}</ul>' if urls else '<p class="small muted">Compiled from the program lists on the pages above; no external links recorded.</p>'))
    sections.append(f'<section class="card src" id="curated"><h2>Curated reference files</h2><p class="small muted">Hand-checked tables kept in the repository, with the sources recorded inside each one.</p>{"".join(cur)}</section>')
    navhtml = "".join(f'<a href="{html.escape((nav_urls or {}).get(n["href"], n["href"]))}">{html.escape(n["label"])}</a>' for n in nav)
    toc = " · ".join(f'<a href="#{html.escape(h.split(".")[0])}">{html.escape(l)}</a>' for h, l, _ in pages) + ' · <a href="#curated">Curated files</a>'
    body = f"""
<style>
.src {{ margin-top: 16px; }}
.src ul {{ margin: 4px 0 10px; padding-left: 18px; font-size: 13px; }}
.src li {{ margin-bottom: 3px; overflow-wrap: anywhere; }}
.src a {{ color: var(--focus); }}
.src h2 a {{ color: inherit; text-decoration: none; }}
.src h3 {{ margin-top: 10px; color: var(--ink-2); }}
.toc {{ font-size: 13px; line-height: 1.9; }}
.toc a {{ color: var(--focus); }}
</style>
<div class="wrap">
  <div class="topbar"><h1>Sources</h1><button id="theme" type="button" aria-pressed="false">Dark mode</button></div>
  <nav class="nav" aria-label="Maps">{navhtml}</nav>
  <p class="sub">Every dataset behind these pages, page by page: the sources each page cites in its notes, then every address the build scripts download or query to produce it ({len(total)} distinct addresses). All of it is public government, election-agency or open data; the code is in the site's GitHub repository and rebuilds daily.</p>
  <div class="card toc">{toc}</div>
  {''.join(sections)}
</div>
<script>
const themeBtn = document.getElementById("theme");
const isDark = () => document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
function syncThemeBtn() {{ const d = isDark(); themeBtn.textContent = d ? "Light mode" : "Dark mode"; themeBtn.setAttribute("aria-pressed", d); }}
themeBtn.onclick = () => {{ const next = isDark() ? "light" : "dark"; document.documentElement.dataset.theme = next; try {{ localStorage.setItem("theme", next); }} catch (e) {{}} syncThemeBtn(); }};
try {{ const saved = localStorage.getItem("theme"); if (saved && !document.documentElement.dataset.theme) document.documentElement.dataset.theme = saved; }} catch (e) {{}}
syncThemeBtn();
</script>
"""
    return head + body, len(total)

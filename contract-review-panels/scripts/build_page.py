#!/usr/bin/env python3
"""Build the two-pane contract review page.

Usage:
    build_page.py contract.txt results.json out.html [--page-title "Contract Review"]
                  [--standalone [--intro-file intro.html]]

contract.txt  Plain text of the contract, paragraphs separated by blank lines,
              with article and section numbers at the start of their lines.
results.json  {"contract_title": str, "subtitle": str (optional),
               "results": [{"title": str, "body": str}, ...]}  (1 to 6 results)

By default the output is a self-contained HTML page (no doctype, html, head or
body tags) ready to publish with the Artifact tool. With --standalone it is a
complete HTML document for GitHub Pages or any other web host, with an optional
intro (an HTML fragment given by --intro-file) above the sample. Citations such as "(Art. 3.2)" or
"Section 3.2" in the results become links that scroll the contract to that
section, and numbered margin tags in the contract show which results cite it.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
N_COLORS = 6


def roman_to_int(s):
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = ROMAN[ch]
        total = total - v if v < prev else total + v
        prev = v
    return total


def norm_key(raw, exhibit=False):
    """'IX.3(a)' -> '9.3', '3.2' -> '3.2'. Exhibit keys such as 'A.7' keep their letter."""
    k = re.sub(r"\([^)]*\)", "", raw).strip(". ")
    parts = k.split(".")
    if not exhibit and parts:
        # A lone numeral ("Art. IX") or a multi-letter numeral before a dot ("IX.3").
        # A single letter before a dot ("C.1") is an exhibit item, so it is left alone.
        if re.fullmatch(r"[IVXLC]+", parts[0]) and (len(parts) == 1 or len(parts[0]) > 1):
            parts[0] = str(roman_to_int(parts[0]))
    return ".".join(p for p in parts if p)


# ---------------------------------------------------------------- contract

SEC_PATTERNS = [
    re.compile(r"^(?:ARTICLE|Article)\s+(\d+|[IVXLC]+)\b"),
    re.compile(r"^(?:SECTION|Section|§)\s*(\d+(?:\.\d+)*)"),
    re.compile(r"^(\d+(?:\.\d+)+)[.)]?\s+\S"),
    re.compile(r"^(\d{1,2})[.)]\s+[A-Z][A-Z0-9 &,/'\-]{3,}"),
]
LIST_START = re.compile(r"^\(?[A-Za-z0-9]{1,3}[.)]\s")


def split_blocks(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) < 8 and text.count("\n") > 20:
        blocks = [l for l in text.split("\n") if l.strip()]
    return blocks


def tidy(block):
    """Join hard-wrapped lines, keeping breaks before (a), 1., etc."""
    lines = [l.strip() for l in block.split("\n") if l.strip()]
    out = lines[0]
    for line in lines[1:]:
        out += ("\n" if LIST_START.match(line) else " ") + line
    return re.sub(r"[ ]{2,}", " ", out)


def is_heading(t):
    if re.match(r"^(ARTICLE|Article)\s+(\d+|[IVXLC]+)\b", t):
        return True
    return (
        len(t) < 90
        and t.upper() == t
        and re.search(r"[A-Z]{3}", t) is not None
        and not t.endswith(".")
    )


EXHIBIT_RE = re.compile(r"^(?:EXHIBIT|Exhibit)\s+([A-Z])\b")
EX_ITEM_RE = re.compile(r"^(\d{1,2}|[IVX]{1,4})[.)]\s+\S")


def parse_contract(text):
    """Return list of (text, key or None, is_heading) and a key -> block id map.

    Inside an exhibit, numbered items ("7. Schedule delays ...") get keys like "A.7",
    so results can cite them as "Ex. A.7" without clashing with body sections.
    """
    blocks, index = [], {}
    cur_ex = None
    for raw in split_blocks(text):
        t = tidy(raw)
        key = None
        m = EXHIBIT_RE.match(t)
        if m:
            cur_ex = m.group(1)
            key = cur_ex
        elif cur_ex and EX_ITEM_RE.match(t):
            key = f"{cur_ex}.{EX_ITEM_RE.match(t).group(1)}"
        else:
            for pat in SEC_PATTERNS:
                m = pat.match(t)
                if m:
                    key = norm_key(m.group(1))
                    break
        i = len(blocks)
        blocks.append((t, key, is_heading(t)))
        if key and key not in index:
            index[key] = f"b{i}"
    return blocks, index


def resolver(index):
    def resolve(raw, exhibit=False):
        k = norm_key(raw, exhibit)
        while k:
            if k in index:
                return index[k]
            if "." in k:
                k = k.rsplit(".", 1)[0]
            else:
                break
        return None

    return resolve


# ----------------------------------------------------------------- results

NUM = r"(?:\d+(?:\.\d+)*(?:\([A-Za-z0-9]{1,4}\))*|[IVXLC]{1,6}\b(?:\.\d+)*)"
NUM_RE = re.compile(NUM)
CITE_RE = re.compile(
    r"(?P<pre>(?<![A-Za-z])(?:Arts?\.?|Articles?|Secs?\.?|Sections?|§§?|¶)\s*)"
    r"(?P<nums>" + NUM + r"(?:\s*(?:,|;|and|&amp;|-|–|to|through)\s*" + NUM + r")*)"
)
# Exhibit citations: "Ex. A", "Exhibit A.7", "Exs. A.2, A.7"
EXNUM = r"[A-Z]\b(?:\.(?:\d+|[IVX]{1,4}\b)(?:\.\d+)*)?"
EXNUM_RE = re.compile(EXNUM)
EX_RE = re.compile(
    r"(?P<pre>(?<![A-Za-z])(?:Exhibits?|Exhs?\.|Exs?\.)\s*)"
    r"(?P<nums>" + EXNUM + r"(?:\s*(?:,|and|&amp;)\s*" + EXNUM + r")*)"
)


def color(n):
    return ((n - 1) % N_COLORS) + 1


def render_result(body, resolve):
    """Return (html, cited block ids in order, unresolved citation strings)."""
    cited, unresolved = [], []
    esc = html.escape(body.strip(), quote=False)

    def make_linker(exhibit):
        def link_one(m):
            raw = m.group(0)
            bid = resolve(raw, exhibit)
            if bid is None:
                unresolved.append(raw)
                return raw
            if bid not in cited:
                cited.append(bid)
            return f'<button type="button" class="cite" data-target="{bid}">{raw}</button>'

        return link_one

    ex_link, num_link = make_linker(True), make_linker(False)
    esc = EX_RE.sub(lambda m: m.group("pre") + EXNUM_RE.sub(ex_link, m.group("nums")), esc)
    esc = CITE_RE.sub(lambda m: m.group("pre") + NUM_RE.sub(num_link, m.group("nums")), esc)
    esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)

    out, para, items = [], [], []

    def flush_p():
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para.clear()

    def flush_l():
        if items:
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            items.clear()

    for line in esc.split("\n"):
        s = line.strip()
        if not s:
            flush_p()
            flush_l()
            continue
        m = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", s)
        if m:
            flush_p()
            items.append(m.group(1))
        else:
            flush_l()
            para.append(s)
    flush_p()
    flush_l()
    return "".join(out), cited, unresolved


# --------------------------------------------------------------------- page

TEMPLATE = r'''<title>{{PAGE_TITLE}}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
/* Layout: two independent scrolling panes, contract left and results right.
   Under 900px the panes become two tabs. Document set in a serif, tools in a sans. */
:root {
  --bg: #e9edf2; --panel: #f6f8fa; --paper: #ffffff;
  --ink: #18222d; --muted: #586577; --line: #d3dae3; --accent: #1d4f7a;
  --c1: #0b7a75; --c2: #a8510a; --c3: #6d4aa8; --c4: #b42343; --c5: #4d7a1e; --c6: #0e6fa8;
  --on-c: #ffffff;
  --serif: "Source Serif 4", Georgia, "Times New Roman", serif;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f141a; --panel: #161d25; --paper: #1a222b;
    --ink: #e4e9ef; --muted: #9aa7b6; --line: #2b3643; --accent: #86b6e0;
    --c1: #4fd1c5; --c2: #f0b45a; --c3: #b9a4ec; --c4: #f08aa0; --c5: #a9d36a; --c6: #7cc4f0;
    --on-c: #10161c;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0f141a; --panel: #161d25; --paper: #1a222b;
  --ink: #e4e9ef; --muted: #9aa7b6; --line: #2b3643; --accent: #86b6e0;
  --c1: #4fd1c5; --c2: #f0b45a; --c3: #b9a4ec; --c4: #f08aa0; --c5: #a9d36a; --c6: #7cc4f0;
  --on-c: #10161c;
  color-scheme: dark;
}
html { height: 100%; box-sizing: border-box; }
*, *::before, *::after { box-sizing: inherit; }
body { height: 100%; margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans); }
.app {
  height: 100%; display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 12px;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 14px 16px;
}
.top { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.top > div:first-child { min-width: 0; }
.eyebrow { margin: 0 0 2px; font-size: 11px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }
h1 { margin: 0; font-size: 20px; line-height: 1.25; font-weight: 600; text-wrap: balance; }
.sub { margin: 2px 0 0; font-size: 13px; color: var(--muted); }
.switch { display: none; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
.switch button { font: inherit; font-size: 13px; font-weight: 500; padding: 6px 14px; border: 0; background: var(--paper); color: var(--ink); cursor: pointer; }
.switch button[aria-selected="true"] { background: var(--accent); color: var(--paper); }

.panes { min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; }
.pane { min-height: 0; min-width: 0; overflow: auto; border: 1px solid var(--line); border-radius: 6px; }
#doc-pane { background: var(--paper); }
#res-pane { background: var(--panel); }
.pane-head {
  position: sticky; top: 0; z-index: 2; display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  padding: 9px 18px; border-bottom: 1px solid var(--line); background: inherit;
  font-size: 11px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; color: var(--muted);
}
.pane-head span:last-child { font-weight: 400; letter-spacing: 0; text-transform: none; font-variant-numeric: tabular-nums; }

.doc { display: flex; flex-direction: column; gap: 8px; padding: 18px 22px 40px; font-family: var(--serif); font-size: 15px; line-height: 1.62; }
.blk { position: relative; padding: 2px 6px 2px 34px; border-radius: 3px; white-space: pre-line; overflow-wrap: anywhere; }
.blk.h { margin-top: 12px; font-family: var(--sans); font-size: 12px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; line-height: 1.5; }
.tags { position: absolute; left: 0; top: 4px; display: flex; flex-wrap: wrap; gap: 2px; width: 30px; font-family: var(--sans); }
.tag { min-width: 15px; font-style: normal; font-size: 10px; font-weight: 600; line-height: 15px; text-align: center; border-radius: 3px; color: var(--on-c); }
.c1 { background: var(--c1); } .c2 { background: var(--c2); } .c3 { background: var(--c3); }
.c4 { background: var(--c4); } .c5 { background: var(--c5); } .c6 { background: var(--c6); }
.blk[data-hl="1"] { background: color-mix(in srgb, var(--c1) 16%, transparent); }
.blk[data-hl="2"] { background: color-mix(in srgb, var(--c2) 16%, transparent); }
.blk[data-hl="3"] { background: color-mix(in srgb, var(--c3) 16%, transparent); }
.blk[data-hl="4"] { background: color-mix(in srgb, var(--c4) 16%, transparent); }
.blk[data-hl="5"] { background: color-mix(in srgb, var(--c5) 16%, transparent); }
.blk[data-hl="6"] { background: color-mix(in srgb, var(--c6) 16%, transparent); }
.blk.flash { outline: 2px solid var(--accent); outline-offset: 2px; }

.legend { margin: 0; padding: 12px 18px 0; font-size: 12.5px; line-height: 1.5; color: var(--muted); }
.results { padding: 4px 18px 8px; }
.res { padding: 16px 0 18px; border-bottom: 1px solid var(--line); }
.res:last-of-type { border-bottom: 0; }
.res header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.badge { flex: none; width: 22px; height: 22px; display: grid; place-items: center; border-radius: 4px; font-size: 12px; font-weight: 600; color: var(--on-c); }
h2 { margin: 0; font-size: 16px; font-weight: 600; line-height: 1.3; }
.body p { margin: 0 0 8px; max-width: 68ch; font-size: 14px; line-height: 1.58; }
.body ul { margin: 0 0 8px; padding-left: 18px; }
.body li { margin: 0 0 4px; font-size: 14px; line-height: 1.55; }
.res footer { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 6px; }
.show { font: inherit; font-size: 12px; font-weight: 500; padding: 4px 10px; border-radius: 5px; border: 1px solid var(--line); background: var(--paper); color: var(--ink); cursor: pointer; }
.show[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
.show:disabled { opacity: .55; cursor: default; }
.wc { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
button.cite { font: inherit; padding: 0; border: 0; background: none; color: var(--accent); cursor: pointer; text-decoration: underline dotted; text-underline-offset: 3px; font-variant-numeric: tabular-nums; }
button.cite:hover { text-decoration-style: solid; }
.note { margin: 0; padding: 0 18px 22px; font-size: 12px; line-height: 1.5; color: var(--muted); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

@media (max-width: 899px) {
  .switch { display: flex; }
  .panes { grid-template-columns: minmax(0, 1fr); }
  .pane { display: none; }
  .app[data-view="res"] #res-pane, .app[data-view="doc"] #doc-pane { display: block; }
  .doc { padding: 14px 14px 32px; }
}
</style>
<div class="app" data-view="res">
  <header class="top">
    <div>
      <p class="eyebrow">Contract review</p>
      <h1>{{CONTRACT_TITLE}}</h1>
      {{SUBTITLE}}
    </div>
    <div class="switch" role="tablist" aria-label="Choose a pane">
      <button type="button" role="tab" data-view="res" aria-selected="true">Results</button>
      <button type="button" role="tab" data-view="doc" aria-selected="false">Contract</button>
    </div>
  </header>
  <main class="panes">
    <section class="pane" id="doc-pane" aria-label="Contract text">
      <div class="pane-head"><span>Contract</span><span>{{BLOCK_COUNT}} paragraphs, {{SECTION_COUNT}} numbered sections</span></div>
      <div class="doc">
{{DOC}}
      </div>
    </section>
    <section class="pane" id="res-pane" aria-label="Review results">
      <div class="pane-head"><span>Review</span><span>{{RESULT_COUNT}} prompts</span></div>
      <p class="legend">Numbers in the contract margin show which results cite that section. Select a section reference to jump to it.</p>
      <div class="results">
{{RESULTS}}
      </div>
      <p class="note">Each result is drawn only from the contract text on the left and is not legal advice. Check every point against the section it cites.</p>
    </section>
  </main>
</div>
<script>
(function () {
  var app = document.querySelector('.app');
  var mq = window.matchMedia('(max-width: 899px)');
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var tabs = document.querySelectorAll('.switch button');
  function setView(v) {
    app.setAttribute('data-view', v);
    tabs.forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-view') === v ? 'true' : 'false'); });
  }
  tabs.forEach(function (b) { b.addEventListener('click', function () { setView(b.getAttribute('data-view')); }); });
  function jump(id) {
    var el = document.getElementById(id);
    if (!el) return;
    if (mq.matches) setView('doc');
    el.scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' });
    el.classList.add('flash');
    setTimeout(function () { el.classList.remove('flash'); }, 1800);
  }
  function clearHighlight() {
    document.querySelectorAll('.blk[data-hl]').forEach(function (e) { e.removeAttribute('data-hl'); });
    document.querySelectorAll('.show[aria-pressed="true"]').forEach(function (b) {
      b.setAttribute('aria-pressed', 'false');
      b.textContent = b.getAttribute('data-label');
    });
  }
  document.addEventListener('click', function (e) {
    var cite = e.target.closest && e.target.closest('button.cite');
    if (cite) { jump(cite.getAttribute('data-target')); return; }
    var btn = e.target.closest && e.target.closest('.show');
    if (!btn || btn.disabled) return;
    var wasOn = btn.getAttribute('aria-pressed') === 'true';
    clearHighlight();
    if (wasOn) return;
    var sec = btn.closest('.res');
    var ids = sec.getAttribute('data-cites').split(' ').filter(Boolean);
    ids.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.setAttribute('data-hl', sec.getAttribute('data-c'));
    });
    btn.setAttribute('aria-pressed', 'true');
    btn.textContent = 'Clear highlight';
    jump(ids[0]);
  });
})();
</script>
'''


STANDALONE_CSS = """<style>
/* Standalone page: an intro above the sample. The sample keeps a fixed height with its own scrolling panes. */
html, body { height: auto; min-height: 100%; }
.intro {
  padding-block: 28px 6px;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
}
.intro-inner { max-width: 780px; }
.intro h1 { margin: 2px 0 10px; font-size: clamp(26px, 4.5vw, 34px); line-height: 1.15; font-weight: 600; text-wrap: balance; }
.intro .lede { margin: 0 0 16px; max-width: 66ch; font-size: 16px; line-height: 1.6; }
.intro a { color: var(--accent); }
.lenses { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; padding: 0; list-style: none; }
.lenses li {
  display: flex; align-items: center; gap: 8px; padding: 4px 12px 4px 5px;
  border: 1px solid var(--line); border-radius: 6px; background: var(--panel); font-size: 14px;
}
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 26px; }
.intro .btn {
  padding: 8px 16px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--paper); color: var(--ink); font-size: 14px; font-weight: 500; text-decoration: none;
}
.intro .btn.primary { background: var(--accent); border-color: var(--accent); color: var(--paper); }
.intro .btn:hover { text-decoration: underline; }
.intro h2 { margin: 0 0 4px; font-size: 12px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }
.sample-note { margin: 0 0 6px; max-width: 70ch; font-size: 13.5px; line-height: 1.55; color: var(--muted); }
.doc-title { margin: 0; font-size: 20px; line-height: 1.25; font-weight: 600; text-wrap: balance; }
.app { height: clamp(520px, calc(100vh - 16px), 880px); }
</style>
"""


def to_standalone(page, intro_html):
    """Wrap the artifact fragment in a complete HTML document, with an optional intro above the sample."""
    head, sep, rest = page.partition('<div class="app"')
    head = head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
    intro = ""
    if intro_html.strip():
        intro = f'<header class="intro"><div class="intro-inner">\n{intro_html.strip()}\n</div></header>\n'
        # The intro carries the page's h1, so the contract title inside the sample becomes an h2.
        rest = rest.replace("<h1>", '<h2 class="doc-title">', 1).replace("</h1>", "</h2>", 1)
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + head
        + STANDALONE_CSS
        + "</head>\n<body>\n"
        + intro
        + sep
        + rest
        + "</body>\n</html>\n"
    )


def build(contract_text, data, page_title):
    blocks, index = parse_contract(contract_text)
    resolve = resolver(index)
    results = data["results"]

    cards, tags, report = [], {}, []
    for n, r in enumerate(results, start=1):
        body_html, cited, unresolved = render_result(r["body"], resolve)
        for bid in cited:
            tags.setdefault(int(bid[1:]), set()).add(n)
        wc = len(r["body"].split())
        label = (
            f"Show in contract ({len(cited)} section{'s' if len(cited) != 1 else ''})"
            if cited
            else "No section cited"
        )
        disabled = "" if cited else " disabled"
        cards.append(
            f'        <section class="res" id="r{n}" data-n="{n}" data-c="{color(n)}" data-cites="{" ".join(cited)}">\n'
            f'          <header><span class="badge c{color(n)}">{n}</span><h2>{html.escape(r["title"])}</h2></header>\n'
            f'          <div class="body">{body_html}</div>\n'
            f'          <footer><button type="button" class="show" aria-pressed="false" data-label="{label}"{disabled}>{label}</button>'
            f'<span class="wc">{wc} words</span></footer>\n'
            f"        </section>"
        )
        report.append((n, r["title"], wc, len(cited), unresolved))

    doc_parts = []
    for i, (text, key, heading) in enumerate(blocks):
        cls = "blk" + (" h" if heading else "")
        tag_html = ""
        if i in tags:
            tag_html = '<span class="tags" aria-hidden="true">' + "".join(
                f'<i class="tag c{color(n)}">{n}</i>' for n in sorted(tags[i])
            ) + "</span>"
        key_attr = f' data-key="{html.escape(key)}"' if key else ""
        doc_parts.append(
            f'        <div class="{cls}" id="b{i}"{key_attr}>{tag_html}{html.escape(text, quote=False)}</div>'
        )

    subtitle = data.get("subtitle", "").strip()
    page = (
        TEMPLATE.replace("{{PAGE_TITLE}}", html.escape(page_title))
        .replace("{{CONTRACT_TITLE}}", html.escape(data.get("contract_title", page_title)))
        .replace("{{SUBTITLE}}", f'<p class="sub">{html.escape(subtitle)}</p>' if subtitle else "")
        .replace("{{BLOCK_COUNT}}", str(len(blocks)))
        .replace("{{SECTION_COUNT}}", str(len(index)))
        .replace("{{RESULT_COUNT}}", str(len(results)))
        .replace("{{DOC}}", "\n".join(doc_parts))
        .replace("{{RESULTS}}", "\n".join(cards))
    )
    return page, blocks, index, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("contract")
    ap.add_argument("results")
    ap.add_argument("out")
    ap.add_argument("--page-title", default="Contract Review")
    ap.add_argument("--standalone", action="store_true", help="write a complete HTML document instead of an artifact fragment")
    ap.add_argument("--intro-file", default="", help="standalone only: HTML fragment shown above the sample")
    a = ap.parse_args()

    text = Path(a.contract).read_text(encoding="utf-8", errors="replace")
    data = json.loads(Path(a.results).read_text(encoding="utf-8"))
    results = data.get("results")
    if not isinstance(results, list) or not 1 <= len(results) <= 6:
        sys.exit("results.json needs a 'results' list with 1 to 6 entries, each with 'title' and 'body'.")
    for r in results:
        if not r.get("title") or not r.get("body"):
            sys.exit("Every result needs a non-empty 'title' and 'body'.")

    page, blocks, index, report = build(text, data, a.page_title)
    if a.standalone:
        intro = Path(a.intro_file).read_text(encoding="utf-8") if a.intro_file else ""
        page = to_standalone(page, intro)
    Path(a.out).write_text(page, encoding="utf-8")

    print(f"Wrote {a.out} ({len(page) / 1024:.0f} KB)")
    print(f"Contract: {len(blocks)} paragraphs, {len(index)} numbered sections detected")
    if not index:
        print("WARNING: no article or section numbers detected, so citations cannot link. Check contract.txt.")
    problems = False
    for n, title, wc, linked, unresolved in report:
        flags = []
        if wc < 90 or wc > 170:
            flags.append(f"word count {wc} is outside 90 to 170")
        if unresolved:
            flags.append("unresolved citations: " + ", ".join(unresolved))
        if linked == 0:
            flags.append("no linked citations")
        problems = problems or bool(flags)
        print(f"  {n}. {title}: {wc} words, {linked} sections linked" + (" | " + "; ".join(flags) if flags else ""))
    if problems:
        print("Fix the items flagged above in results.json and rebuild.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Turn raw pdftotext output into clean paragraphs for build_page.py.

Usage:
    prepare_text.py raw.txt contract.txt [--drop REGEX ...] [--until REGEX]

PDF text arrives one visual line at a time, often with the section number on a
line of its own ("3.2" then the clause text). This script rejoins wrapped lines
into paragraphs, puts each numbered clause in its own paragraph, drops bare page
numbers, and separates paragraphs with blank lines, which is what build_page.py
expects.

--drop REGEX   Drop any line that matches (repeatable). Use for running headers,
               footers, file paths, and letterhead lines.
--until REGEX  Stop at the first line that matches, keeping that line. Use to cut
               off pages of tables or listings that would only add noise.

Check the result by eye. A real contract can have layout quirks no script predicts.
"""
import argparse
import re
import sys
from pathlib import Path

PAGE_NO = re.compile(r"^\d{1,3}$")
NUMBER_ONLY = re.compile(r"^\d+(?:\.\d+)+\.?$")
NUMBERED = re.compile(r"^\d+(?:\.\d+)+\.?\s+\S")
SECTION = re.compile(r"^(?:Section|SECTION|ARTICLE|Article)\s+(?:\d+|[IVXLC]+)\.?\s+\S")
RECITAL = re.compile(r"^(?:WHEREAS|NOW, THEREFORE|IN WITNESS)")
ITEM = re.compile(r"^(?:\d{1,2}\.\s+[A-Z]|[IVX]+\.\s+[A-Z]|\(?[a-z]{1,2}\)\s+\S)")
RULE = re.compile(r"^[_\-=]{5,}$")


def is_caps_heading(line):
    return len(line) < 60 and line.upper() == line and re.search(r"[A-Z]{3}", line) is not None


def prepare(lines, drops, until):
    out, cur, pending_number = [], [], False

    def flush():
        nonlocal cur, pending_number
        if cur:
            out.append(" ".join(cur))
        cur, pending_number = [], False

    for raw in lines:
        line = re.sub(r"[ \t]{3,}", "   ", raw.strip())
        line = re.sub(r"\s*\.{5,}\s*", " … ", line)  # dot leaders in price lists and tables
        if until and until.search(line):
            flush()
            out.append(line)
            break
        if not line or PAGE_NO.match(line) or any(d.search(line) for d in drops):
            continue
        if RULE.match(line):
            flush()
            continue
        if NUMBER_ONLY.match(line):
            flush()
            cur, pending_number = [line], True
            continue
        if pending_number:
            cur.append(line)
            pending_number = False
            continue
        starts_clause = bool(cur) and re.match(r"^(?:\d|Section|SECTION|ARTICLE|Article)", cur[0])
        if SECTION.match(line) or NUMBERED.match(line) or RECITAL.match(line) or ITEM.match(line):
            flush()
            cur = [line]
        elif is_caps_heading(line) and not starts_clause:
            flush()
            out.append(line)
        elif "   " in line:  # table row: keep on its own line
            flush()
            out.append(line)
        else:
            cur.append(line)
    flush()
    return "\n\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--drop", action="append", default=[], metavar="REGEX")
    ap.add_argument("--until", metavar="REGEX")
    a = ap.parse_args()
    lines = Path(a.raw).read_text(encoding="utf-8", errors="replace").splitlines()
    text = prepare(lines, [re.compile(d) for d in a.drop], re.compile(a.until) if a.until else None)
    Path(a.out).write_text(text, encoding="utf-8")
    paras = text.count("\n\n") + 1
    print(f"Wrote {a.out}: {paras} paragraphs, {len(text.split())} words", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Rebuild contract-review-panels.skill from the contract-review-panels folder.

Run this after you edit the prompts or any other file in the skill folder, then
commit the new .skill file so the download link serves the updated version.

    python3 build_skill.py

The .skill file is a zip archive with the skill folder at the top level. The
evals folder and Python cache files are left out.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL_DIR = ROOT / "contract-review-panels"
OUT = ROOT / "contract-review-panels.skill"
SKIP_DIRS = {"__pycache__", "evals"}
SKIP_NAMES = {".DS_Store"}


def main():
    files = sorted(
        p
        for p in SKILL_DIR.rglob("*")
        if p.is_file()
        and not (SKIP_DIRS & set(p.relative_to(SKILL_DIR).parts))
        and p.name not in SKIP_NAMES
        and p.suffix != ".pyc"
    )
    if not (SKILL_DIR / "SKILL.md").exists():
        raise SystemExit("contract-review-panels/SKILL.md not found. Run this from the repository folder.")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(ROOT).as_posix())
    print(f"Wrote {OUT.name} with {len(files)} files:")
    for p in files:
        print("  " + p.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()

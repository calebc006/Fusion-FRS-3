"""
Scan the Graduands photos folder and build a JSON manifest of participants.

Each image filename is expected to follow the pattern:
    "<number>. <BRANCH> - <NAME>.<ext>"
where BRANCH is one of: DIS, AF, Army, Navy.

Usage:
    python scripts/build_graduands_json.py [source_folder] [output_json]

Defaults:
    source_folder: C:\\Users\\Admin\\Desktop\\FR Image Bank\\SMEAC Jul 2026\\Graduands photos
    output_json:   scripts/graduands.json
"""

import json
import re
import sys
from pathlib import Path

DEFAULT_SOURCE = r"C:\Users\Admin\Desktop\FR Image Bank\SMEAC Jul 2026\Graduands photos"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "graduands.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
BRANCHES = ("DIS", "AF", "Army", "Navy")

# "<number>. <BRANCH> [-] <NAME>.<ext>"
# The dash and surrounding spacing are inconsistent in the source folder
# (e.g. "Army  - NAME", "DIS  NAME" with no dash at all), so match loosely.
FILENAME_RE = re.compile(
    r"^\s*\d+\.\s*(" + "|".join(BRANCHES) + r")\s*-?\s*(.+?)\s*$",
    re.IGNORECASE,
)


def parse_filename(stem: str):
    match = FILENAME_RE.match(stem)
    if not match:
        return None
    branch_raw, name = match.groups()
    branch = next(b for b in BRANCHES if b.lower() == branch_raw.lower())
    return branch, name.strip()


def build_manifest(source_folder: Path):
    entries = {}  # name -> {"name": ..., "images": [...], "tags": {branch}}
    unmatched = []

    for path in sorted(source_folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue

        parsed = parse_filename(path.stem)
        if parsed is None:
            unmatched.append(path.name)
            continue

        branch, name = parsed
        display_name = f"{branch} - {name}"

        entry = entries.setdefault(
            display_name, {"name": display_name, "images": [], "tags": set()}
        )
        entry["images"].append(path.name)
        entry["tags"].add(branch)

    details = []
    for entry in entries.values():
        details.append(
            {
                "name": entry["name"],
                "images": entry["images"],
                "tags": sorted(entry["tags"]),
            }
        )

    return details, unmatched


def main():
    source_folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_SOURCE)
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT

    if not source_folder.is_dir():
        print(f"Source folder not found: {source_folder}", file=sys.stderr)
        sys.exit(1)

    details, unmatched = build_manifest(source_folder)

    manifest = {
        "img_folder_path": "",
        "flag_folder_path": "",
        "details": details,
    }

    text = json.dumps(manifest, indent=4, ensure_ascii=False)
    # Collapse "tags" arrays onto a single line, e.g. "tags": ["DIS"]
    text = re.sub(
        r'"tags": \[\s*((?:"[^"]*",?\s*)+)\]',
        lambda m: '"tags": [' + ", ".join(re.findall(r'"[^"]*"', m.group(1))) + "]",
        text,
    )
    output_path.write_text(text, encoding="utf-8")

    print(f"Wrote {len(details)} entries to {output_path}")
    if unmatched:
        print(f"\n{len(unmatched)} file(s) did not match the expected pattern:")
        for name in unmatched:
            print(f"  - {name}")


if __name__ == "__main__":
    main()

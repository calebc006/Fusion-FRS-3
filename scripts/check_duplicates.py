"""
Cross-check the smeac_namelist.json database and the original Graduands
photos folder for duplicate names or duplicate photos.

Checks performed:
  1. Duplicate `name` entries within the JSON.
  2. Duplicate image filenames referenced within the JSON (same image used
     by more than one entry, or repeated within one entry's `images` list).
  3. Duplicate extracted names among the raw files in the source folder
     (same person appearing under more than one file number).
  4. Duplicate photo *content* in the source folder (byte-identical files
     saved under different filenames) via SHA-256 hashing.
  5. Files present in the source folder but missing from the JSON, and
     vice versa.

Usage:
    python scripts/check_duplicates.py [source_folder] [namelist_json]
"""

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_SOURCE = r"C:\Users\Admin\Desktop\FR Image Bank\SMEAC Jul 2026\Graduands photos"
DEFAULT_JSON = Path(__file__).resolve().parents[1] / "simpliFRy" / "data" / "smeac_namelist.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
BRANCHES = ("DIS", "AF", "Army", "Navy")
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
    return f"{branch} - {name.strip()}"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main():
    source_folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_SOURCE)
    json_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_JSON

    print(f"Source folder: {source_folder}")
    print(f"JSON file:     {json_path}\n")

    # ---------- Load JSON ----------
    data = json.loads(json_path.read_text(encoding="utf-8"))
    details = data.get("details", [])

    name_to_entries = defaultdict(list)
    image_to_entries = defaultdict(list)
    json_images = set()

    for entry in details:
        name_to_entries[entry["name"]].append(entry)
        for img in entry.get("images", []):
            image_to_entries[img].append(entry["name"])
            json_images.add(img)

    print("=" * 70)
    print("1. Duplicate NAMES in JSON")
    print("=" * 70)
    dup_names = {n: e for n, e in name_to_entries.items() if len(e) > 1}
    if dup_names:
        for name, entries in dup_names.items():
            imgs = [img for e in entries for img in e["images"]]
            print(f"  '{name}' appears {len(entries)}x -> images: {imgs}")
    else:
        print("  None found.")

    print("\n" + "=" * 70)
    print("2. Duplicate IMAGE filenames referenced in JSON")
    print("=" * 70)
    dup_images = {img: names for img, names in image_to_entries.items() if len(names) > 1}
    if dup_images:
        for img, names in dup_images.items():
            print(f"  '{img}' used by {len(names)} entries -> {names}")
    else:
        print("  None found.")

    # ---------- Scan source folder ----------
    folder_files = sorted(
        p for p in source_folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    folder_filenames = {p.name for p in folder_files}

    folder_name_to_files = defaultdict(list)
    unmatched = []
    for p in folder_files:
        parsed = parse_filename(p.stem)
        if parsed is None:
            unmatched.append(p.name)
        else:
            folder_name_to_files[parsed].append(p.name)

    print("\n" + "=" * 70)
    print("3. Duplicate NAMES among files in source folder (same person, multiple files)")
    print("=" * 70)
    dup_folder_names = {n: f for n, f in folder_name_to_files.items() if len(f) > 1}
    if dup_folder_names:
        for name, files in dup_folder_names.items():
            print(f"  '{name}' -> {files}")
    else:
        print("  None found.")

    print("\n" + "=" * 70)
    print("4. Duplicate PHOTO CONTENT in source folder (byte-identical files)")
    print("=" * 70)
    hash_to_files = defaultdict(list)
    for p in folder_files:
        hash_to_files[sha256_of(p)].append(p.name)
    dup_hashes = {h: f for h, f in hash_to_files.items() if len(f) > 1}
    if dup_hashes:
        for h, files in dup_hashes.items():
            print(f"  {h[:12]}... -> {files}")
    else:
        print("  None found.")

    print("\n" + "=" * 70)
    print("5. Files in folder vs JSON")
    print("=" * 70)
    missing_from_json = folder_filenames - json_images
    missing_from_folder = json_images - folder_filenames
    print(f"  In folder but NOT referenced in JSON ({len(missing_from_json)}):")
    for f in sorted(missing_from_json):
        print(f"    - {f}")
    print(f"  Referenced in JSON but NOT found in folder ({len(missing_from_folder)}):")
    for f in sorted(missing_from_folder):
        print(f"    - {f}")

    if unmatched:
        print(f"\n  Note: {len(unmatched)} folder file(s) didn't match the naming pattern: {unmatched}")

    print(f"\nTotals: {len(folder_files)} files in folder, {len(json_images)} unique images in JSON, {len(details)} entries in JSON.")


if __name__ == "__main__":
    main()

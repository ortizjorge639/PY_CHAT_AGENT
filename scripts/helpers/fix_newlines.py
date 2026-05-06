"""
Fix double-spaced files by collapsing consecutive blank lines to at most one.

Usage:
    python scripts/fix_newlines.py <file_or_glob> [<file_or_glob> ...]

Examples:
    python scripts/fix_newlines.py agent/kernel_customer.py
    python scripts/fix_newlines.py agent/*.py
    python scripts/fix_newlines.py .       # all .py files recursively
"""

import pathlib
import sys


def fix_newlines(path: pathlib.Path) -> bool:
    """Remove excessive blank lines. Returns True if file was changed."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank

    # Strip trailing blank lines
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()

    result = "\n".join(cleaned) + "\n"
    if result == text:
        return False

    path.write_text(result, encoding="utf-8", newline="\n")
    return True


def resolve_targets(args: list[str]) -> list[pathlib.Path]:
    """Expand arguments into a list of .py files."""
    files: list[pathlib.Path] = []
    for arg in args:
        p = pathlib.Path(arg)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        else:
            files.extend(sorted(pathlib.Path(".").glob(arg)))
    return files


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    targets = resolve_targets(sys.argv[1:])
    if not targets:
        print("No matching files found.")
        sys.exit(1)

    changed = 0
    for path in targets:
        if fix_newlines(path):
            print(f"  fixed: {path}")
            changed += 1

    print(f"\n{changed}/{len(targets)} file(s) fixed.")


if __name__ == "__main__":
    main()

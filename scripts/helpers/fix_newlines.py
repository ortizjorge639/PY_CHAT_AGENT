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


def _is_double_spaced(lines: list[str]) -> bool:
    """Detect the alternating blank-line pattern (every other line is blank)."""
    if len(lines) < 10:
        return False
    # Check if ~50% of lines are blank — strong double-spacing signal
    sample = lines[:60]
    blank_count = sum(1 for l in sample if l.strip() == "")
    return blank_count >= len(sample) * 0.4


def fix_newlines(path: pathlib.Path) -> bool:
    """Remove excessive blank lines. Returns True if file was changed."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if _is_double_spaced(lines):
        # Alternating pattern: strip ALL blank lines, then re-add
        # proper PEP-8 spacing based on context.
        non_blank = [l for l in lines if l.strip() != ""]
        cleaned = _reinsert_spacing(non_blank)
    else:
        # Fallback: just collapse consecutive blank lines to one.
        cleaned = []
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


def _reinsert_spacing(lines: list[str]) -> list[str]:
    """Re-add single blank lines where PEP-8 / readability expects them."""
    result: list[str] = []
    in_multiline_string = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track triple-quote multiline strings (rough heuristic)
        toggle_count = stripped.count('"""') + stripped.count("'''")
        if toggle_count % 2 == 1:
            in_multiline_string = not in_multiline_string

        if i == 0:
            result.append(line)
            continue

        prev = lines[i - 1].strip() if i > 0 else ""

        need_blank = False

        if not in_multiline_string:
            # Blank before top-level def/class
            if stripped.startswith(("def ", "class ", "async def ")):
                if not prev.startswith(("@", "def ", "class ", "async def ")):
                    need_blank = True
            # Blank before comment blocks (# ---) or section comments
            elif stripped.startswith("#") and not prev.startswith("#"):
                if prev and not prev.endswith(":") and not prev.endswith("\\"):
                    need_blank = True
            # Blank after closing triple-quote of docstring/prompt
            elif prev == '"""' or prev == "'''":
                need_blank = True
            # Blank before import groups
            elif stripped.startswith(("import ", "from ")) and prev and not prev.startswith(("import ", "from ")):
                if not prev.startswith("#"):
                    need_blank = True

        if need_blank:
            result.append("")
        result.append(line)

    return result


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

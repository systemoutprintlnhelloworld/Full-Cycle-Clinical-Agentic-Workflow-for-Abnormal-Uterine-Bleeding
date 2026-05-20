import os
import re
import sys


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo_root, "docs", "method.md")
    if not os.path.exists(path):
        print(f"ERROR: {path} not found")
        return 1

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    errors = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.rstrip("\n")
        if not stripped:
            continue

        if stripped.lstrip().startswith(("- ", "* ", "+ ")):
            errors.append(f"Line {idx}: bullet list detected")
            continue

        if re.match(r"^\s*\d+[\.)]\s+", stripped):
            errors.append(f"Line {idx}: numbered list detected")
            continue

        if stripped.startswith("|") or " | " in stripped:
            errors.append(f"Line {idx}: table-like pipe detected")
            continue

    if errors:
        print("FORMAT CHECK FAILED")
        for err in errors:
            print(err)
        return 1

    print("FORMAT CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

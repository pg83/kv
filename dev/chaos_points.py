#!/usr/bin/env python3

from pathlib import Path
import re
import sys


def main():
    root = Path(__file__).resolve().parent.parent
    chaos = root / "chaos_fault.go"
    declared = set(re.findall(r'^\t"([^"]+)":', chaos.read_text(), re.M))
    sources = [path for path in root.glob("*.go") if path.name != chaos.name]
    asked = set()

    for path in sources:
        source = path.read_text()
        asked |= set(re.findall(r'chaosCall(?:2)?\("([^"]+)"', source))

    if not declared:
        sys.exit("no chaos points are declared")

    silent = sorted(declared - asked)
    unknown = sorted(asked - declared)

    if silent:
        sys.exit("nothing ever asks about: " + ", ".join(silent))

    if unknown:
        sys.exit("undeclared chaos points: " + ", ".join(unknown))

    print(f"{len(declared)} chaos points, every one is connected")


if __name__ == "__main__":
    main()

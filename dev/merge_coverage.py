#!/usr/bin/env python3

import argparse
from decimal import Decimal
from pathlib import Path
import sys


def read(path):
    blocks = {}

    for line in Path(path).read_text().splitlines():
        if not line or line.startswith("mode:"):
            continue

        where, statements, count = line.rsplit(" ", 2)
        held = blocks.get(where, (0, 0))
        blocks[where] = (int(statements), max(int(count), held[1]))

    return blocks


def files(blocks):
    result = {}

    for where in blocks:
        result.setdefault(where.split(":")[0], set()).add(where)

    return result


def share(blocks):
    total = sum(statements for statements, _ in blocks.values())
    covered = sum(statements for statements, count in blocks.values() if count)
    percent = round(100 * covered / total, 1) if total else 0.0

    return covered, total, percent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("profiles", nargs="+")
    parser.add_argument("--output", required=True)
    parser.add_argument("--minimum", type=Decimal, default=Decimal(0))
    args = parser.parse_args()
    merged = {}

    for path in args.profiles:
        blocks = read(path)

        if not blocks:
            sys.exit(f"{path} carries no measured block")

        known = files(merged)

        for name, held in known.items():
            found = files(blocks).get(name)

            if found is not None and found != held:
                sys.exit(f"{path} was measured on other sources: {name} has other blocks")

        covered, total, percent = share(blocks)
        print(f"{Path(path).name}: {percent}% ({covered}/{total} statements)")

        for where, (statements, count) in blocks.items():
            held = merged.get(where, (0, 0))
            merged[where] = (statements, max(count, held[1]))

    covered, total, percent = share(merged)
    Path(args.output).write_text(
        "mode: atomic\n" + "".join(
            f"{where} {statements} {count}\n"
            for where, (statements, count) in sorted(merged.items())
        )
    )
    print(f"together: {percent}% ({covered}/{total} statements)")

    if not total or 100 * covered < args.minimum * total:
        sys.exit(f"coverage {covered}/{total} statements is below {args.minimum}%")


if __name__ == "__main__":
    main()

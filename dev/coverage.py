#!/usr/bin/env python3

import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--minimum", type=float, default=100)
    parser.add_argument("dirs", nargs="+")
    args = parser.parse_args()
    directories = []

    for name in args.dirs:
        root = Path(name)
        daemons = sorted(root.glob("daemon-*"))

        if not daemons:
            sys.exit(f"no daemon coverage directories in {root}")

        for daemon in daemons:
            if not list(daemon.glob("covcounters.*")):
                sys.exit(f"no daemon counters in {daemon}")

            directories.append(str(daemon))

    subprocess.run([
        "go", "tool", "covdata", "textfmt",
        "-i=" + ",".join(directories),
        "-o", args.output,
    ], check=True)
    summary = subprocess.run([
        "go", "tool", "cover", f"-func={args.output}",
    ], check=True, capture_output=True, text=True).stdout
    print(summary)
    total = float(summary.strip().splitlines()[-1].split()[-1].rstrip("%"))

    if total < args.minimum:
        sys.exit(f"coverage {total}% is below {args.minimum}%")


if __name__ == "__main__":
    main()

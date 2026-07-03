#!/usr/bin/env python3
"""Generate a bcrypt password hash for MagnetBox bootstrap."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth import hash_password


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a MagnetBox bcrypt password hash")
    parser.add_argument("password", nargs="?", help="Password to hash; omitted means prompt interactively")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    password = args.password if args.password is not None else getpass.getpass("Password: ")
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

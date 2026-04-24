"""Computa sha256 de um arquivo (usado para check anti-reprocessamento).

Uso: python scripts/data_ops_producers/hash_artifact.py <path>
Imprime o hex no stdout.
"""

import hashlib
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("uso: hash_artifact.py <path>", file=sys.stderr)
        return 2
    p = Path(sys.argv[1])
    if not p.exists():
        print(f"nao existe: {p}", file=sys.stderr)
        return 1
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    print(h.hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

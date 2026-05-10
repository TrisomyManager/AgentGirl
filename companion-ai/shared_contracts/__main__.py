"""`python -m shared_contracts` — print the public contract surface."""

from __future__ import annotations

import shared_contracts as _sc


def main() -> None:
    names = sorted(getattr(_sc, "__all__", []) or [n for n in dir(_sc) if not n.startswith("_")])
    print(f"shared_contracts public surface ({len(names)} symbols):")
    for name in names:
        obj = getattr(_sc, name, None)
        kind = type(obj).__name__
        print(f"  - {name:<32s}  [{kind}]")


if __name__ == "__main__":
    main()

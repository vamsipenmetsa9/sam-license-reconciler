from __future__ import annotations

import argparse
import logging
import sys

from .reconcile import load_csv, reconcile

log = logging.getLogger("samrecon")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="samrecon", description="Reconcile software installs against entitlements.")
    parser.add_argument("--installs", required=True)
    parser.add_argument("--entitlements", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        positions, unrecognized = reconcile(load_csv(args.installs), load_csv(args.entitlements))
    except (OSError, ValueError, KeyError) as exc:
        log.error("reconciliation failed: %s", exc)
        return 2
    print(f"{'Product':<28}{'Metric':<12}{'Owned':>6}{'Used':>6}{'Bal':>6}  {'Status':<15}{'True-up':>10}{'Savings':>10}")
    for p in positions:
        print(f"{p.publisher + ' ' + p.product:<28}{p.metric:<12}{p.owned:>6}{p.consumed:>6}{p.balance:>6}  {p.status:<15}{p.true_up_cost:>10.2f}{p.potential_savings:>10.2f}")
    for name in unrecognized:
        log.warning("not normalized, needs a rule: %s", name)
    return 1 if any(p.balance < 0 for p in positions) else 0


if __name__ == "__main__":
    sys.exit(main())

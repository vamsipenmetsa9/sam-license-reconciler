"""Software license reconciliation on synthetic data.

Mirrors the steps SAM Pro performs: normalize discovered installs to a publisher
and product, count rights consumed under each license metric, then compare with
entitlements to get a compliance position. Product names and prices are invented.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Discovered display name pattern -> (publisher, product). First match wins.
NORMALIZATION_RULES = [
    (r"^northwind\s+(office|productivity)\b", ("Northwind", "Office Suite")),
    (r"^nw\s+office\b", ("Northwind", "Office Suite")),
    (r"^acme\s*(db|database)\b", ("Acme", "Database Server")),
    (r"^(globex\s+)?diagram\s*pro\b", ("Globex", "Diagram Pro")),
]
METRICS = {"per_device", "per_user", "per_core"}
MIN_CORES_PER_DEVICE = 4  # common per-core licensing floor


@dataclass(frozen=True)
class Position:
    publisher: str
    product: str
    metric: str
    owned: int
    consumed: int
    unit_cost: float

    @property
    def balance(self) -> int:
        return self.owned - self.consumed

    @property
    def status(self) -> str:
        if self.balance < 0:
            return "NON-COMPLIANT"
        return "OVER-LICENSED" if self.balance > 0 else "COMPLIANT"

    @property
    def true_up_cost(self) -> float:
        return round(max(-self.balance, 0) * self.unit_cost, 2)

    @property
    def potential_savings(self) -> float:
        return round(max(self.balance, 0) * self.unit_cost, 2)


def load_csv(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def normalize(display_name: str) -> tuple[str, str] | None:
    cleaned = re.sub(r"\s+", " ", display_name.strip().lower())
    for pattern, product in NORMALIZATION_RULES:
        if re.search(pattern, cleaned):
            return product
    return None


def reconcile(installs: list[dict], entitlements: list[dict]) -> tuple[list[Position], list[str]]:
    """Return positions plus the display names that could not be normalized."""
    owned: dict[tuple, int] = defaultdict(int)
    metric_for: dict[tuple, str] = {}
    cost_for: dict[tuple, float] = {}
    for ent in entitlements:
        key = (ent["publisher"], ent["product"])
        metric = ent["metric"]
        if metric not in METRICS:
            raise ValueError(f"Unknown license metric '{metric}' for {key}")
        if metric_for.setdefault(key, metric) != metric:
            raise ValueError(f"Mixed license metrics for {key}")
        owned[key] += int(ent["quantity"])
        cost_for[key] = float(ent["unit_cost"])

    devices: dict[tuple, set] = defaultdict(set)
    users: dict[tuple, set] = defaultdict(set)
    cores: dict[tuple, dict] = defaultdict(dict)
    unrecognized: set[str] = set()
    for row in installs:
        key = normalize(row["display_name"])
        if key is None:
            unrecognized.add(row["display_name"])
            continue
        devices[key].add(row["device"])  # two installs on one device consume one right
        if row.get("user"):
            users[key].add(row["user"].lower())
        cores[key][row["device"]] = max(int(row.get("cores") or 0), MIN_CORES_PER_DEVICE)

    positions = []
    for key in sorted(set(owned) | set(devices)):
        metric = metric_for.get(key, "per_device")  # unlicensed installs still show as a shortfall
        consumed = {"per_device": len(devices[key]), "per_user": len(users[key]), "per_core": sum(cores[key].values())}[metric]
        positions.append(Position(key[0], key[1], metric, owned.get(key, 0), consumed, cost_for.get(key, 0.0)))
    return positions, sorted(unrecognized)

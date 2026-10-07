import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from samrecon.__main__ import main
from samrecon.reconcile import load_csv, normalize, reconcile

DATA = Path(__file__).resolve().parent.parent / "sample_data"


def install(device, name, user="", cores=""):
    return {"device": device, "user": user, "display_name": name, "cores": cores}


def ent(product, metric, qty, cost="10", publisher="Northwind"):
    return {"publisher": publisher, "product": product, "metric": metric, "quantity": str(qty), "unit_cost": cost}


class NormalizeTests(unittest.TestCase):
    def test_variants_map_to_one_product(self):
        for name in ["Northwind Office 2024", "  NW   Office Professional", "northwind productivity suite"]:
            self.assertEqual(normalize(name), ("Northwind", "Office Suite"))

    def test_unknown_returns_none(self):
        self.assertIsNone(normalize("Initech Screen Grabber"))


class ReconcileTests(unittest.TestCase):
    def test_per_device_counts_each_device_once(self):
        positions, _ = reconcile([install("D1", "Northwind Office 2024"), install("D1", "NW Office")], [ent("Office Suite", "per_device", 1)])
        self.assertEqual((positions[0].consumed, positions[0].status), (1, "COMPLIANT"))

    def test_per_user_dedupes_case_insensitively(self):
        rows = [install("D1", "Diagram Pro", "ana"), install("D2", "Diagram Pro", "ANA")]
        positions, _ = reconcile(rows, [ent("Diagram Pro", "per_user", 2, publisher="Globex")])
        self.assertEqual((positions[0].consumed, positions[0].status, positions[0].potential_savings), (1, "OVER-LICENSED", 10.0))

    def test_per_core_applies_minimum(self):
        positions, _ = reconcile([install("S1", "Acme DB", cores="2")], [ent("Database Server", "per_core", 2, "100", "Acme")])
        self.assertEqual((positions[0].consumed, positions[0].balance, positions[0].true_up_cost), (4, -2, 200.0))

    def test_install_without_entitlement_is_a_shortfall(self):
        positions, _ = reconcile([install("D1", "Diagram Pro")], [])
        self.assertEqual((positions[0].owned, positions[0].status), (0, "NON-COMPLIANT"))

    def test_entitlement_without_install(self):
        positions, _ = reconcile([], [ent("Office Suite", "per_device", 5)])
        self.assertEqual(positions[0].balance, 5)

    def test_unknown_metric_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown license metric"):
            reconcile([], [ent("Office Suite", "per_site", 1)])

    def test_mixed_metrics_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Mixed"):
            reconcile([], [ent("Office Suite", "per_device", 1), ent("Office Suite", "per_user", 1)])


class SampleDataTests(unittest.TestCase):
    def test_expected_positions(self):
        positions, unknown = reconcile(load_csv(DATA / "installs.csv"), load_csv(DATA / "entitlements.csv"))
        got = {p.product: (p.owned, p.consumed, p.status) for p in positions}
        self.assertEqual(got, {
            "Database Server": (16, 20, "NON-COMPLIANT"),
            "Diagram Pro": (2, 2, "COMPLIANT"),
            "Office Suite": (5, 4, "OVER-LICENSED"),
        })
        self.assertEqual(unknown, ["Initech Screen Grabber"])

    def test_cli_exit_code_signals_shortfall(self):
        with redirect_stdout(io.StringIO()) as out, self.assertLogs("samrecon", level="WARNING"):
            code = main(["--installs", str(DATA / "installs.csv"), "--entitlements", str(DATA / "entitlements.csv")])
        self.assertEqual(code, 1)
        self.assertIn("1800.00", out.getvalue())


if __name__ == "__main__":
    unittest.main()

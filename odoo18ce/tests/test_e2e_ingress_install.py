#!/usr/bin/env python3
"""Pure self-tests for the Ingress install driver of the 29-module parity run."""
import unittest

from e2e_ingress_install import ScanRound, install_order, new_rewrite_notifications, scan_rounds


class InstallOrderTests(unittest.TestCase):
    def test_a_module_comes_after_every_target_it_depends_on(self) -> None:
        deps = {
            "website_sale": {"website", "sale_management", "payment"},
            "sale_management": {"account"},
            "website": {"mail"},
            "account": {"mail"},
            "mail": set(),
        }
        order = install_order(["website_sale", "website", "sale_management", "account", "mail"], deps)
        self.assertEqual(order, ["mail", "account", "sale_management", "website", "website_sale"])

    def test_dependencies_outside_the_targets_are_left_to_odoo(self) -> None:
        order = install_order(["crm", "contacts"], {"crm": {"base", "mail"}, "contacts": {"mail"}})
        self.assertEqual(order, ["contacts", "crm"])

    def test_a_cycle_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            install_order(["a", "b"], {"a": {"b"}, "b": {"a"}})


class ScanRoundTests(unittest.TestCase):
    def test_each_round_report_in_the_log_is_one_round_with_its_prefixes(self) -> None:
        log = [
            "2026-09-24T10:00:01.1Z [10:00:01] INFO: Rewrite scan: PostgreSQL is ready",
            "2026-09-24T10:00:05.2Z Rewrite scan (apply): up to date",
            "2026-09-24T10:00:05.2Z   no database serves a new bundle",
            "2026-09-24T10:05:07.9Z Rewrite scan (apply): applied",
            "2026-09-24T10:05:07.9Z   2 rules generated and nginx was reloaded",
            "2026-09-24T10:05:07.9Z   prefixes: /shop /pos",
            "2026-09-24T10:05:08.0Z odoo.modules.loading: 91 modules loaded",
        ]
        self.assertEqual(
            scan_rounds(log),
            [ScanRound("up to date", ()), ScanRound("applied", ("/shop", "/pos"))],
        )

    def test_a_log_without_a_round_has_none(self) -> None:
        self.assertEqual(scan_rounds(["odoo.modules.loading: 91 modules loaded"]), [])


class NotificationTests(unittest.TestCase):
    def test_only_rewrite_notifications_that_are_new_or_recreated_count(self) -> None:
        before = [
            {"notification_id": "odoo18ce_generated_rewrites_added_aaaaaaaaaaaa", "created_at": "t1"},
            {"notification_id": "odoo18ce_generated_rewrites_failed", "created_at": "t1"},
        ]
        after = before[:1] + [
            {"notification_id": "odoo18ce_generated_rewrites_failed", "created_at": "t2"},
            {"notification_id": "odoo18ce_generated_rewrites_added_bbbbbbbbbbbb", "created_at": "t2"},
            {"notification_id": "config_entry_discovery", "created_at": "t2"},
        ]
        self.assertEqual(
            [n["notification_id"] for n in new_rewrite_notifications(before, after)],
            ["odoo18ce_generated_rewrites_failed", "odoo18ce_generated_rewrites_added_bbbbbbbbbbbb"],
        )


if __name__ == "__main__":
    unittest.main()

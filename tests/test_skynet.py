"""Tests for Skynet. Run with:  python3 -m pytest   (or)   python3 -m unittest

Uses only the stdlib so it runs anywhere with no install step.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from skynet import Brain, MemoryStore, Registry, Automations
from skynet.registry import App, Function
from skynet.automations import Rule


def make_brain(tmp: str) -> Brain:
    """A brain with an isolated on-disk memory and a health app registered."""
    memory = MemoryStore(Path(tmp) / "mem")
    registry = Registry([
        App(
            id="health",
            name="Health",
            summary="Metrics",
            status="live",
            location="skynet.apps.health:HealthApp",
            tags=("personal",),
            functions=(Function("log", "Record"),),
        ),
        App(id="foreman", name="Foreman", status="external", tags=("apps",)),
    ])
    rules = Automations([
        Rule(
            id="nudge_weight",
            name="nudge",
            trigger={
                "type": "check",
                "stale": {
                    "namespace": "health",
                    "collection": "metrics",
                    "where": {"type": "weight"},
                    "days": 3,
                },
            },
            actions=({"type": "notify", "message": "log a weight"},),
        ),
    ])
    return Brain(memory, registry, rules)


class MemoryTests(unittest.TestCase):
    def test_facts_roundtrip(self):
        with TemporaryDirectory() as tmp:
            m = MemoryStore(tmp)
            self.assertIsNone(m.get("health", "goal"))
            m.set("health", "goal", 185)
            self.assertEqual(m.get("health", "goal"), 185)
            self.assertTrue(m.delete("health", "goal"))
            self.assertFalse(m.delete("health", "goal"))

    def test_series_append_and_query(self):
        with TemporaryDirectory() as tmp:
            m = MemoryStore(tmp)
            a = m.append("health", "metrics", {"type": "weight", "value": 190})
            self.assertIn("id", a)
            self.assertIn("at", a)
            m.append("health", "metrics", {"type": "sleep", "value": 7})
            weights = m.query("health", "metrics", where=lambda r: r["type"] == "weight")
            self.assertEqual(len(weights), 1)
            self.assertEqual(m.collections("health"), ["metrics"])

    def test_same_second_tie_breaks_by_append_order(self):
        with TemporaryDirectory() as tmp:
            m = MemoryStore(tmp)
            at = "2026-01-01T00:00:00Z"
            m.append("h", "s", {"type": "w", "value": 1, "at": at})
            m.append("h", "s", {"type": "w", "value": 2, "at": at})
            newest = m.latest("h", "s")
            self.assertEqual(newest["value"], 2)  # last appended wins


class RegistryTests(unittest.TestCase):
    def test_load_real_registry(self):
        root = Path(__file__).resolve().parent.parent
        reg = Registry.load(root / "registry" / "apps.json")
        self.assertIn("health", reg)
        self.assertTrue(reg.get("health").is_live)
        self.assertFalse(reg.get("foreman").is_live)
        self.assertGreaterEqual(len(reg.live()), 1)


class HealthAppTests(unittest.TestCase):
    def test_log_list_summary_trend_goal(self):
        with TemporaryDirectory() as tmp:
            brain = make_brain(tmp)

            r = brain.dispatch("health", "log", {"type": "weight", "value": "192"})
            self.assertTrue(r.ok)
            self.assertEqual(r.data["record"]["unit"], "lbs")

            brain.dispatch("health", "log", {"type": "weight", "value": 188,
                                             "at": "2026-01-01T00:00:00Z"})

            summary = brain.dispatch("health", "summary")
            self.assertTrue(summary.ok)
            self.assertIn("weight", summary.data["metrics"])

            lst = brain.dispatch("health", "list", {"type": "weight"})
            self.assertEqual(len(lst.data["records"]), 2)

            trend = brain.dispatch("health", "trend", {"type": "weight", "days": 3650})
            self.assertTrue(trend.ok)
            self.assertEqual(trend.data["count"], 2)

            goal = brain.dispatch("health", "goal", {"type": "weight", "value": 185})
            self.assertTrue(goal.ok)
            read = brain.dispatch("health", "goal", {"type": "weight"})
            self.assertEqual(read.data["goal"], 185)

    def test_bad_value_fails_gracefully(self):
        with TemporaryDirectory() as tmp:
            brain = make_brain(tmp)
            r = brain.dispatch("health", "log", {"type": "weight", "value": "heavy"})
            self.assertFalse(r.ok)

    def test_unknown_command(self):
        with TemporaryDirectory() as tmp:
            brain = make_brain(tmp)
            r = brain.dispatch("health", "nope")
            self.assertFalse(r.ok)


class DispatchAndAutomationTests(unittest.TestCase):
    def test_external_app_returns_intent(self):
        with TemporaryDirectory() as tmp:
            brain = make_brain(tmp)
            r = brain.dispatch("foreman", "photo")
            self.assertTrue(r.ok)
            self.assertIsNotNone(r.intent)

    def test_unknown_app(self):
        with TemporaryDirectory() as tmp:
            brain = make_brain(tmp)
            r = brain.dispatch("nope", "x")
            self.assertFalse(r.ok)

    def test_check_fires_when_no_weight(self):
        with TemporaryDirectory() as tmp:
            brain = make_brain(tmp)
            fired = brain.check()  # nothing logged -> stale -> fires
            self.assertEqual(len(fired), 1)
            self.assertTrue(brain.outbox)

    def test_check_quiet_when_recent(self):
        with TemporaryDirectory() as tmp:
            brain = make_brain(tmp)
            brain.dispatch("health", "log", {"type": "weight", "value": 190})
            fired = brain.check()  # just logged -> not stale
            self.assertEqual(len(fired), 0)

    def test_event_rule_fires_on_emit(self):
        with TemporaryDirectory() as tmp:
            brain = make_brain(tmp)
            brain.automations.rules.append(Rule(
                id="e1", name="e1",
                trigger={"type": "event", "on": "ping"},
                actions=({"type": "notify", "message": "pong"},),
            ))
            fired = brain.emit("ping")
            self.assertEqual(len(fired), 1)
            self.assertIn("pong", brain.outbox)


if __name__ == "__main__":
    unittest.main()

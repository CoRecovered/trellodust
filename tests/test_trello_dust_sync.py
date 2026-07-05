import datetime as dt
import json
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trello_dust_sync import build_dust_payload, build_markdown


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_trello_export.json"


class TrelloDustSyncTests(unittest.TestCase):
    def setUp(self):
        self.export = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.reference_time = dt.datetime(2026, 7, 3, 12, 0, tzinfo=dt.timezone.utc)

    def test_markdown_groups_cards_by_list_and_highlights_risks(self):
        markdown = build_markdown(self.export, self.reference_time)

        self.assertIn("# Trello Project Brief: Dust Launch Plan", markdown)
        self.assertIn("### Blocked", markdown)
        self.assertIn("Blocked: waiting for Dust API key", markdown)
        self.assertIn("## Blocked or waiting", markdown)
        self.assertIn("## Overdue", markdown)
        self.assertIn("Map Trello card fields into Dust document", markdown)
        self.assertIn("Recent activity", markdown)
        self.assertIn("moved 'Map Trello card fields into Dust document' from Backlog to In Progress", markdown)

    def test_payload_matches_dust_document_upsert_shape(self):
        markdown = build_markdown(self.export, self.reference_time)
        payload = build_dust_payload(self.export, markdown, self.reference_time)

        self.assertEqual(payload["title"], "Trello Project Brief - Dust Launch Plan")
        self.assertEqual(payload["mime_type"], "text/markdown")
        self.assertEqual(payload["text"], markdown)
        self.assertEqual(payload["source_url"], "https://trello.com/b/example/dust-launch-plan")
        self.assertIn("trello", payload["tags"])
        self.assertIn("trello-board:board123", payload["tags"])
        self.assertEqual(payload["timestamp"], 1783080000000)
        self.assertTrue(payload["light_document_output"])
        self.assertFalse(payload["async"])


if __name__ == "__main__":
    unittest.main()

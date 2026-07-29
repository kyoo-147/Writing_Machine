import json
import tempfile
import unittest
from pathlib import Path

from content_machine.core import Database, Story, deduplicate, fingerprint, score_story
from content_machine.pipeline import ContentMachine


class ContentMachineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = Database(f"sqlite:///{root / 'test.db'}")
        self.machine = ContentMachine(self.db, root / "data")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_scoring_and_deduplication(self):
        a = Story("Open source AI agent demo", "https://x.test/a?utm_source=x", "GitHub", "API SDK benchmark", kind="release")
        b = Story("Open source AI agent demo!", "https://x.test/a", "X")
        self.assertGreater(score_story(a), 70)
        self.assertEqual(len(deduplicate([a, b])), 1)

    def test_develop_produce_archive_gate(self):
        story = Story("A useful AI agent release", "https://github.com/example/agent", "GitHub", "The project released an open source SDK.", kind="release")
        score_story(story)
        self.db.save_story(story)
        developed = self.machine.develop(story.id)
        self.assertTrue(developed["claims"])
        package = self.machine.produce(story.id)
        self.assertTrue(Path(package["path"], "package.json").exists())
        self.assertEqual(package["asset_policy"], "source-first")
        self.assertEqual(package["assets"], [])
        self.assertFalse(Path(package["path"], "cover.png").exists())
        self.assertEqual(self.machine.publish(story.id, "tiktok")["status"], "dry-run")
        public = Path(package["path"], "caption.txt").read_text(encoding="utf-8")
        self.assertNotIn("DISCOVERY_SOURCE_CHECKED", public)
        self.assertNotIn("CLAIM_LEDGER_CHECKED", public)

    def test_fingerprint_removes_tracking(self):
        self.assertEqual(
            fingerprint("Same", "https://example.com/a?utm_source=x"),
            fingerprint("Same", "https://example.com/a"),
        )


if __name__ == "__main__":
    unittest.main()

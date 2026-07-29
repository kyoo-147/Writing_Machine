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
        story = Story(
            "A useful AI agent release", "https://github.com/example/agent", "GitHub",
            "The project released an open source SDK.", kind="release",
            metadata={"trending_hashtags": ["#AgenticAI", "#DanceChallenge"]},
        )
        score_story(story)
        self.db.save_story(story)
        source_dir = self.machine.root / "assets" / story.id
        source_dir.mkdir(parents=True)
        (source_dir / "source-image.jpg").write_bytes(b"source-media")
        (source_dir / "imagegen-architecture.png").write_bytes(b"generated-illustration")
        result_dir = self.machine.root / "results" / f"{story.id}-a-useful-ai-agent-release"
        result_dir.mkdir(parents=True)
        (result_dir / "cover.png").write_bytes(b"legacy-placeholder")
        (result_dir / "preview.mp4").write_bytes(b"legacy-placeholder")
        developed = self.machine.develop(story.id)
        self.assertTrue(developed["claims"])
        package = self.machine.produce(story.id)
        self.assertTrue(Path(package["path"], "package.json").exists())
        self.assertEqual(package["asset_policy"], "source-required")
        self.assertEqual({asset["origin"] for asset in package["assets"]}, {"source", "imagegen"})
        self.assertIn("Source: GitHub", package["caption"])
        self.assertEqual(len(package["hashtags"]), 5)
        self.assertEqual(len({tag.lower() for tag in package["hashtags"]}), 5)
        self.assertIn("#AgenticAI", package["hashtags"])
        self.assertNotIn("#DanceChallenge", package["hashtags"])
        self.assertTrue(all(tag in package["caption"] for tag in package["hashtags"]))
        self.assertFalse(Path(package["path"], "cover.png").exists())
        self.assertFalse(Path(package["path"], "preview.mp4").exists())
        for filename in (
            "brief.json", "title-and-hooks.md", "script.md", "caption.md", "sources.md",
            "fact-check.md", "asset-manifest.json", "upload-checklist.md",
        ):
            self.assertTrue(Path(package["path"], filename).exists(), filename)
        self.assertEqual(len(list(Path(package["path"], "assets").iterdir())), 2)
        self.assertEqual(self.machine.publish(story.id, "tiktok")["status"], "dry-run")
        public = Path(package["path"], "caption.txt").read_text(encoding="utf-8")
        self.assertNotIn("DISCOVERY_SOURCE_CHECKED", public)
        self.assertNotIn("CLAIM_LEDGER_CHECKED", public)

    def test_produce_rejects_missing_source_media_and_svg(self):
        story = Story("AI architecture", "https://example.com/architecture", "Example", "Architecture overview.", kind="article")
        self.db.save_story(story)
        asset_dir = self.machine.root / "assets" / story.id
        asset_dir.mkdir(parents=True)
        (asset_dir / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        (asset_dir / "imagegen-diagram.png").write_bytes(b"generated-illustration")
        with self.assertRaisesRegex(RuntimeError, "Source media is required"):
            self.machine.produce(story.id)

    def test_fingerprint_removes_tracking(self):
        self.assertEqual(
            fingerprint("Same", "https://example.com/a?utm_source=x"),
            fingerprint("Same", "https://example.com/a"),
        )


if __name__ == "__main__":
    unittest.main()

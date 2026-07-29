import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_machine.core import Database, Story, deduplicate, fingerprint, score_story
from content_machine.cli import publishing_capabilities, run_scheduled_command, scheduler
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
        self.assertEqual(package["image_text"]["status"], "awaiting-user-decision")
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

    def test_visual_deduplication_keeps_higher_resolution(self):
        from PIL import Image

        asset_dir = self.machine.root / "dedup"
        asset_dir.mkdir(parents=True)
        low = asset_dir / "low.jpg"
        high = asset_dir / "high.webp"
        Image.new("RGB", (100, 50), "#336699").save(low)
        Image.new("RGB", (1000, 500), "#336699").save(high)
        result = self.machine._deduplicate_visuals([low, high])
        self.assertEqual(result, [high])

    def test_fingerprint_removes_tracking(self):
        self.assertEqual(
            fingerprint("Same", "https://example.com/a?utm_source=x"),
            fingerprint("Same", "https://example.com/a"),
        )

    def test_publish_capabilities_do_not_assume_browser_session(self):
        capabilities = publishing_capabilities("tiktok")
        self.assertEqual(capabilities["routes"]["browser_runtime"]["status"], "inspect-agent-tools")
        self.assertTrue(capabilities["routes"]["manual_package"]["available"])
        self.assertIn(
            capabilities["routes"]["native_api"]["status"],
            {"missing-credentials", "init-only-until-media-upload-is-verified"},
        )

    @patch("content_machine.pipeline.request")
    def test_webhook_publish_requires_a_stable_receipt_before_archiving(self, mocked_request):
        story = Story("Verified release", "https://example.com/release", "Example", "Release notes.", kind="release")
        self.db.save_story(story)
        self.db.execute(
            "INSERT INTO packages(story_id,package_path,platform,status,payload,created_at) VALUES(?,?,?,?,?,?)",
            (story.id, "unused", "tiktok", "ready", json.dumps({"caption": "Ready"}), "2026-07-29T00:00:00+00:00"),
        )
        mocked_request.return_value = b'{"status":"accepted"}'

        with self.assertRaisesRegex(RuntimeError, "post ID or public URL"):
            self.machine.publish(story.id, "tiktok", approve=True, webhook="https://publisher.test")

        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM archive").fetchone()[0], 0)

        mocked_request.return_value = b'{"data":{"post_id":"post-123","url":"https://social.test/post-123"}}'
        result = self.machine.publish(story.id, "tiktok", approve=True, webhook="https://publisher.test")
        self.assertEqual(result["external_id"], "post-123")
        self.assertEqual(result["public_url"], "https://social.test/post-123")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM archive").fetchone()[0], 1)

    def test_develop_does_not_self_verify_source_claims(self):
        story = Story(
            "Example model is 50% faster.",
            "https://example.com/model",
            "Example",
            "Example says the model is 50% faster.",
            kind="release",
        )
        self.db.save_story(story)

        developed = self.machine.develop(story.id)

        self.assertTrue(developed["claims"])
        self.assertTrue(all(claim["verdict"] == "unverified" for claim in developed["claims"]))
        self.assertTrue(all(claim["verification_basis"] == "no-independent-source" for claim in developed["claims"]))
        self.assertEqual(developed["citations"][0]["semantic"]["verdict"], "source-supported")
        self.assertFalse(developed["citations"][0]["semantic"]["independent"])

    @patch("content_machine.cli.subprocess.run")
    def test_scheduler_executes_parsed_argv_without_a_shell(self, mocked_run):
        run_scheduled_command("python -m content_machine doctor")
        mocked_run.assert_called_once_with(
            ["python", "-m", "content_machine", "doctor"],
            check=True,
            shell=False,
        )
        with self.assertRaisesRegex(ValueError, "--job-command is required"):
            scheduler(self.db, "add", None, None, None)


if __name__ == "__main__":
    unittest.main()

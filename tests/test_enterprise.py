import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_machine.connectors import story_from_social
from content_machine.core import Database, Story, score_story
from content_machine.enterprise import AccessControl, ClaimChecker, JobQueue, LLMWriter, OAuthManager, ObjectStore, PlatformPublisher
from content_machine.pipeline import ContentMachine


class EnterpriseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = Database(f"sqlite:///{root / 'test.db'}")
        self.machine = ContentMachine(self.db, root / "data")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_supplied_x_use_case_and_metric_velocity(self):
        payload = json.loads(Path("tests/fixtures/x_graph_slides.json").read_text(encoding="utf-8"))
        story = self.machine.ingest_social(payload)
        self.assertEqual(story.metadata["views"], 575649)
        self.db.execute(
            """INSERT INTO metric_snapshots(story_id,platform,views,likes,comments,shares,reposts,bookmarks,captured_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (story.id, "X", 600000, 800, 40, 2, 80, 900, "2026-07-29T10:00:00+00:00"),
        )
        self.db.execute("UPDATE metric_snapshots SET captured_at=? WHERE row_id=1", ("2026-07-29T09:00:00+00:00",))
        velocity = self.db.metric_velocity(story.id)
        self.assertEqual(velocity["views_per_hour"], 24351.0)
        self.assertGreater(velocity["engagement_per_hour"], 100)

    def test_claim_entailment_and_numeric_contradiction(self):
        source = Story("Gemini release", "https://blog.google/example", "Google",
                       "Gemini 3.6 Flash uses 17% fewer output tokens and costs $1.50 per million input tokens.", kind="release")
        checker = ClaimChecker()
        self.assertEqual(checker.check("Gemini 3.6 Flash uses 17% fewer output tokens.", [source])["verdict"], "verified")
        self.assertEqual(checker.check("Gemini 3.6 Flash uses 50% fewer output tokens.", [source])["verdict"], "contradicted")
        self.assertTrue(checker.validate_citation("Gemini 3.6 Flash uses 17% fewer output tokens.", source)["primary"])

    def test_queue_retry_rbac_review_and_object_store(self):
        queue = JobQueue(self.db)
        job_id = queue.enqueue("develop", {"story_id": "abc"}, max_attempts=2)
        leased = queue.lease()
        self.assertEqual(leased["job_id"], job_id)
        queue.fail(job_id, "temporary", retry_delay=0)
        self.assertEqual(queue.stats()["retry"], 1)
        access = AccessControl(self.db)
        workspace = access.create_workspace("Editorial")
        access.add_member(workspace, "editor", "reviewer")
        access.require(workspace, "editor", "review")
        with self.assertRaises(PermissionError):
            access.require(workspace, "editor", "publish")
        access.review("abc", "editor", "approved", "Checked")
        source = Path(self.temp.name, "asset.txt")
        source.write_text("asset", encoding="utf-8")
        stored = ObjectStore(Path(self.temp.name, "objects")).put(source, "abc/asset.txt")
        self.assertTrue(Path(stored).exists())

    @patch("content_machine.enterprise.request")
    def test_llm_and_native_publisher_contracts(self, mocked_request):
        story = Story("AI release", "https://example.com", "Example", "Primary evidence", kind="release")
        mocked_request.return_value = json.dumps({"choices": [{"message": {"content": json.dumps({
            "title": "Title", "hooks": ["Hook"], "script": [], "caption": "Caption", "hashtags": [], "claims": []
        })}}]}).encode()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "CONTENT_LLM_PROVIDER": "openai"}):
            result = LLMWriter().generate(story, {"description": "Skeptical"}, "tiktok")
        self.assertEqual(result["caption"], "Caption")
        mocked_request.return_value = b'{"data":{"id":"123"}}'
        with patch.dict(os.environ, {"X_ACCESS_TOKEN": "test"}):
            published = PlatformPublisher("x").publish({"caption": "Test post"})
        self.assertEqual(published["data"]["id"], "123")
        url = mocked_request.call_args.args[0]
        self.assertEqual(url, "https://api.x.com/2/tweets")

    def test_oauth_url_contract(self):
        with patch.dict(os.environ, {"X_CLIENT_ID": "client", "X_REDIRECT_URI": "https://local.test/callback"}):
            url = OAuthManager().authorization_url("x", "state-123", "challenge-123")
        self.assertIn("code_challenge=challenge-123", url)
        self.assertIn("tweet.write", urllib_parse(url))


def urllib_parse(url):
    from urllib.parse import unquote
    return unquote(url)


if __name__ == "__main__":
    unittest.main()

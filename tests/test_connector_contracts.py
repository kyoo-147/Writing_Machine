import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_machine.connectors import collect_apify, collect_firecrawl, collect_web
from content_machine.enterprise import MediaGenerator, PlatformAnalytics


class ConnectorContractTests(unittest.TestCase):
    @patch("content_machine.connectors.request")
    def test_firecrawl_contract(self, mocked_request):
        mocked_request.return_value = json.dumps({"data": {"markdown": "# Release", "metadata": {"title": "AI Release"}}}).encode()
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test"}):
            story = collect_firecrawl("https://example.com")[0]
        self.assertEqual(story.title, "AI Release")
        self.assertIn("Authorization", mocked_request.call_args.kwargs["headers"])

    @patch("content_machine.connectors.request")
    def test_apify_contract(self, mocked_request):
        mocked_request.return_value = json.dumps([{
            "url": "https://x.com/example/status/1", "text": "Agent demo", "likes": 10
        }]).encode()
        with patch.dict(os.environ, {"APIFY_TOKEN": "test"}):
            story = collect_apify("actor/test", {"search": "AI"})[0]
        self.assertEqual(story.summary.find("Agent demo") >= 0, True)

    @patch("content_machine.connectors.request")
    def test_public_article_parser(self, mocked_request):
        mocked_request.return_value = b"""<html><head><title>Model release</title>
        <meta property="og:description" content="Primary announcement">
        <meta property="article:published_time" content="2026-07-21"></head>
        <body><article><h1>Model release</h1><p>Uses 17% fewer tokens.</p>
        <script>ignore_this()</script></article></body></html>"""
        story = collect_web("https://blog.google/example")[0]
        self.assertIn("17% fewer tokens", story.summary)
        self.assertNotIn("ignore_this", story.summary)

    @patch("content_machine.enterprise.request")
    def test_video_and_analytics_contracts(self, mocked_request):
        mocked_request.side_effect = [
            b'{"url":"https://media.test/video.mp4"}',
            b"video-bytes",
            b'{"data":{"public_metrics":{"like_count":12}}}',
        ]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "video.mp4")
            with patch.dict(os.environ, {"VIDEO_GENERATION_WEBHOOK": "https://provider.test/generate"}):
                MediaGenerator().generate_video("AI animation", target)
            self.assertEqual(target.read_bytes(), b"video-bytes")
        with patch.dict(os.environ, {"X_ACCESS_TOKEN": "test"}):
            result = PlatformAnalytics().fetch("x", "123")
        self.assertEqual(result["data"]["public_metrics"]["like_count"], 12)


if __name__ == "__main__":
    unittest.main()

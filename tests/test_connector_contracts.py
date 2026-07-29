import json
import os
import unittest
from unittest.mock import patch

from content_machine.connectors import collect_apify, collect_firecrawl, collect_github, collect_web
from content_machine.enterprise import PlatformAnalytics


class ConnectorContractTests(unittest.TestCase):
    @patch("content_machine.connectors.request")
    def test_github_search_returns_repository_semantics(self, mocked_request):
        mocked_request.return_value = json.dumps({"items": [{
            "full_name": "example/agent",
            "description": "Agent toolkit",
            "html_url": "https://github.com/example/agent",
            "created_at": "2024-01-02T03:04:05Z",
            "updated_at": "2026-07-28T03:04:05Z",
            "pushed_at": "2026-07-29T03:04:05Z",
            "stargazers_count": 42,
        }]}).encode()

        story = collect_github("agent", limit=1)[0]

        self.assertEqual(story.kind, "repository")
        self.assertEqual(story.published_at, "2024-01-02T03:04:05Z")
        self.assertEqual(story.metadata["pushed_at"], "2026-07-29T03:04:05Z")

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
        <meta property="og:image" content="/hero.jpg">
        <meta property="article:published_time" content="2026-07-21"></head>
        <body><article><h1>Model release</h1><img alt="Benchmark" src="/small.jpg"
        srcset="/small.jpg 500w, /large.jpg 1600w"><img alt="Ignored vector" src="/diagram.svg">
        <p>Uses 17% fewer tokens.</p>
        <script>ignore_this()</script></article></body></html>"""
        story = collect_web("https://blog.google/example")[0]
        self.assertIn("17% fewer tokens", story.summary)
        self.assertNotIn("ignore_this", story.summary)
        self.assertEqual(
            story.metadata["images"],
            [
                {"url": "https://blog.google/hero.jpg", "alt": "Article hero"},
                {"url": "https://blog.google/large.jpg", "alt": "Benchmark"},
            ],
        )

    @patch("content_machine.enterprise.request")
    def test_analytics_contract(self, mocked_request):
        mocked_request.return_value = b'{"data":{"public_metrics":{"like_count":12}}}'
        with patch.dict(os.environ, {"X_ACCESS_TOKEN": "test"}):
            result = PlatformAnalytics().fetch("x", "123")
        self.assertEqual(result["data"]["public_metrics"]["like_count"], 12)


if __name__ == "__main__":
    unittest.main()

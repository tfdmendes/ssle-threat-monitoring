import unittest
from unittest.mock import Mock, patch

import requests

import analytics


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.client = analytics.app.test_client()

    def query_with_stats(self, stats):
        response = Mock()
        response.json.return_value = stats
        with patch.object(analytics.requests, "get", return_value=response):
            return self.client.get("/average")

    def test_empty_storage_returns_null_average(self):
        response = self.query_with_stats({"count": 0, "sum": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"average_temperature": None})

    def test_average_uses_all_readings_and_rounds_to_two_places(self):
        response = self.query_with_stats({"count": 3, "sum": 76})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"average_temperature": 25.33})

    def test_storage_timeout_returns_gateway_timeout(self):
        with patch.object(analytics.requests, "get", side_effect=requests.Timeout):
            response = self.client.get("/average")
        self.assertEqual(response.status_code, 504)

    def test_unavailable_storage_returns_bad_gateway(self):
        with patch.object(analytics.requests, "get", side_effect=requests.ConnectionError):
            response = self.client.get("/average")
        self.assertEqual(response.status_code, 502)

    def test_storage_http_error_returns_bad_gateway(self):
        upstream = Mock()
        upstream.raise_for_status.side_effect = requests.HTTPError()
        with patch.object(analytics.requests, "get", return_value=upstream):
            response = self.client.get("/average")
        self.assertEqual(response.status_code, 502)

    def test_invalid_json_returns_bad_gateway(self):
        upstream = Mock()
        upstream.json.side_effect = ValueError("Invalid JSON")
        with patch.object(analytics.requests, "get", return_value=upstream):
            response = self.client.get("/average")
        self.assertEqual(response.status_code, 502)

    def test_invalid_statistics_return_bad_gateway(self):
        for stats in (
            {}, None, [], {"count": -1, "sum": 0},
            {"count": True, "sum": 25}, {"count": 1, "sum": "25"},
            {"count": 1, "sum": True}, {"count": 1, "sum": float("nan")},
        ):
            with self.subTest(stats=stats):
                self.assertEqual(self.query_with_stats(stats).status_code, 502)


if __name__ == "__main__":
    unittest.main()

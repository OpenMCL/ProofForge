from django.test import TestCase

class HealthTest(TestCase):
    def test_healthz_returns_ok(self):
        resp = self.client.get("/healthz/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

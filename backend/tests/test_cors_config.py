import os
import unittest

os.environ["DATABASE_URL"] = "sqlite://"

from app.config import cors_origins


class CorsConfigTests(unittest.TestCase):
    def test_local_storefront_is_allowed_with_existing_env_override(self):
        origins = cors_origins("http://localhost:5173,https://example.test")
        self.assertIn("http://localhost:5176", origins)
        self.assertIn("https://example.test", origins)
        self.assertEqual(len(origins), len(set(origins)))


if __name__ == "__main__":
    unittest.main()

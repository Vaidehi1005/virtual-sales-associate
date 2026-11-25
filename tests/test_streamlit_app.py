"""Verification tests for Streamlit conversion, DB path config, and helper logic."""

from __future__ import annotations

import os
import py_compile
import sys
import tempfile
import types
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
PRODUCTS_PATH = os.path.join(PROJECT_ROOT, "data", "products.json")
STREAMLIT_APP_PATH = os.path.join(PROJECT_ROOT, "streamlit_app.py")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import ChatbotDatabase, resolve_db_path
from engine import SalesAssociateEngine


def _install_streamlit_stub() -> None:
    """Install a minimal streamlit stub so streamlit_app helpers can be imported and tested."""
    if "streamlit" in sys.modules:
        return
    stub = types.ModuleType("streamlit")
    stub.secrets = {}
    stub.session_state = {}
    stub.cache_resource = lambda fn: fn
    sys.modules["streamlit"] = stub


class TestStreamlitConversion(unittest.TestCase):
    def setUp(self) -> None:
        _install_streamlit_stub()
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)
        import streamlit_app  # noqa: E402

        self.st_app = streamlit_app

    def test_streamlit_app_compiles_cleanly(self) -> None:
        py_compile.compile(STREAMLIT_APP_PATH, doraise=True)

    def test_resolve_db_path_env_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, "env_custom.db")
            old_env = os.environ.get("CHATBOT_DB_PATH")
            try:
                os.environ["CHATBOT_DB_PATH"] = env_path
                self.assertEqual(resolve_db_path(), os.path.abspath(env_path))

                explicit = os.path.join(tmp, "explicit.db")
                self.assertEqual(resolve_db_path(explicit_path=explicit), os.path.abspath(explicit))
                self.assertEqual(self.st_app.get_configured_db_path(explicit), os.path.abspath(explicit))
            finally:
                if old_env is None:
                    os.environ.pop("CHATBOT_DB_PATH", None)
                else:
                    os.environ["CHATBOT_DB_PATH"] = old_env

    def test_comparison_table_and_catalog_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = ChatbotDatabase(os.path.join(tmp, "helper.db"))
            engine = SalesAssociateEngine(PRODUCTS_PATH, db)

            p1 = engine.product_map["phone-iphone-16-pro"]
            p2 = engine.product_map["phone-samsung-s25-ultra"]
            comp = engine._build_comparison([p1, p2], "compare")
            rows = self.st_app.build_comparison_table(comp)
            self.assertTrue(rows)
            self.assertIn("Spec / Feature", rows[0])
            self.assertIn("Apple iPhone 16 Pro", rows[0])
            self.assertIn("Samsung Galaxy S25 Ultra", rows[0])

            filtered = self.st_app.filter_catalog_products(
                engine, query="camera phone", category="Electronics", sort_by="Price: Low to High"
            )
            self.assertTrue(filtered)
            prices = [p["price"] for p in filtered]
            self.assertEqual(prices, sorted(prices))

    def test_requirements_txt_contains_streamlit_and_requests(self) -> None:
        req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
        with open(req_path, "r", encoding="utf-8") as f:
            content = f.read().lower()
        self.assertIn("streamlit", content)
        self.assertIn("requests", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)

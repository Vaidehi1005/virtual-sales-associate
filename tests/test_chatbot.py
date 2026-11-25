"""Automated verification tests for the Virtual Sales Associate chatbot."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
PRODUCTS_PATH = os.path.join(PROJECT_ROOT, "data", "products.json")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

sys.path.insert(0, BACKEND_DIR)

from database import ChatbotDatabase
from engine import SalesAssociateEngine
from server import AppContext, make_handler


class TestVirtualSalesAssociate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_chatbot.db")
        self.db = ChatbotDatabase(self.db_path)
        self.engine = SalesAssociateEngine(PRODUCTS_PATH, self.db)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_catalog_integrity(self) -> None:
        self.assertGreaterEqual(len(self.engine.products), 45)
        ids = [p["id"] for p in self.engine.products]
        self.assertEqual(len(ids), len(set(ids)), "Product IDs must be unique")

    def test_persistence_across_restart(self) -> None:
        s = self.db.create_session("Trip Chat")
        res = self.engine.handle_message(s["id"], "Suggest some black shirts for my upcoming Goa trip.")
        self.assertTrue(res["message"]["metadata"]["products"])
        self.db.save_item(res["message"]["metadata"]["products"][0]["id"], list_type="cart", quantity=2)
        self.db.set_preference("skin_type", "Oily", source="user")

        # Re-open database & engine from disk
        db2 = ChatbotDatabase(self.db_path)
        sessions = db2.list_sessions()
        self.assertEqual(len(sessions), 1)
        msgs = db2.get_messages(s["id"])
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[1]["role"], "assistant")
        self.assertTrue(msgs[1]["metadata"]["products"])

        saved = db2.list_saved_items("cart")
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["quantity"], 2)

        prefs = db2.get_preferences()
        self.assertEqual(prefs["skin_type"]["value"], "Oily")

    def test_pdf_scenarios(self) -> None:
        s = self.db.create_session()

        # 1. Goa black shirts
        r1 = self.engine.handle_message(s["id"], "Suggest some black shirts for my upcoming Goa trip.")
        prods1 = r1["message"]["metadata"]["products"]
        self.assertTrue(any("Shirt" in p["subcategory"] for p in prods1))

        # 2. Camera phone under 40,000
        r2 = self.engine.handle_message(s["id"], "Recommend the best camera phone under ₹40,000.")
        prods2 = r2["message"]["metadata"]["products"]
        self.assertTrue(prods2)
        self.assertTrue(all(p["price"] <= 40000 for p in prods2))
        self.assertTrue(all(p["subcategory"] == "Smartphones" for p in prods2))

        # 3. Compare iPhone 16 Pro and Samsung S25 Ultra
        r3 = self.engine.handle_message(s["id"], "Compare iPhone 16 Pro and Samsung S25 Ultra.")
        comp = r3["message"]["metadata"]["comparison"]
        self.assertIsNotNone(comp)
        comp_names = {p["name"] for p in comp["products"]}
        self.assertIn("Apple iPhone 16 Pro", comp_names)
        self.assertIn("Samsung Galaxy S25 Ultra", comp_names)

        # 4. Computer Engineering laptop
        r4 = self.engine.handle_message(s["id"], "Help me buy a laptop for Computer Engineering studies.")
        prods4 = r4["message"]["metadata"]["products"]
        self.assertTrue(any(p["subcategory"] == "Laptops" for p in prods4))

        # 5. Gym starter bundle
        r5 = self.engine.handle_message(s["id"], "I am joining a gym next week. What shoes and clothes should I buy?")
        bundle = r5["message"]["metadata"]["bundle"]
        self.assertIsNotNone(bundle)
        self.assertGreaterEqual(len(bundle["items"]), 4)

        # 6. India travel sunscreen
        r6 = self.engine.handle_message(s["id"], "I am travelling to India next month. Which sunscreen should I purchase?")
        prods6 = r6["message"]["metadata"]["products"]
        self.assertTrue(any(p["subcategory"] == "Sunscreen" for p in prods6))

    def test_arbitrary_non_pdf_questions_and_followups(self) -> None:
        s = self.db.create_session()

        # General tech Q&A
        qa = self.engine.handle_message(s["id"], "Is 8GB RAM enough for programming?")
        self.assertEqual(qa["message"]["metadata"]["intent"], "tech_qa")
        self.assertIn("16GB RAM", qa["message"]["content"])

        # WFH setup bundle
        wfh = self.engine.handle_message(s["id"], "Help me build a Work-From-Home desk setup")
        self.assertEqual(wfh["message"]["metadata"]["intent"], "bundle")
        self.assertGreaterEqual(len(wfh["message"]["metadata"]["bundle"]["items"]), 4)

        # Oily skincare routine
        skin = self.engine.handle_message(s["id"], "Build me a skincare routine for oily skin")
        self.assertEqual(skin["message"]["metadata"]["intent"], "bundle")
        self.assertTrue(any(p["category"] == "Personal Care" for p in skin["message"]["metadata"]["products"]))

        # Tablet recommendation + multi-turn follow-up ("cheaper") + contextual compare + save to cart
        tab = self.engine.handle_message(s["id"], "I need a tablet for taking notes in class")
        self.assertTrue(any(p["subcategory"] == "Tablets" for p in tab["message"]["metadata"]["products"]))

        cheaper = self.engine.handle_message(s["id"], "Show cheaper options")
        self.assertEqual(cheaper["message"]["metadata"]["intent"], "follow_up")
        self.assertTrue(all(p["price"] < 56900 for p in cheaper["message"]["metadata"]["products"]))

        # Arbitrary headphones comparison
        cmp_audio = self.engine.handle_message(s["id"], "Compare Sony WH-1000XM5 and Anker Soundcore Q20i")
        self.assertEqual(cmp_audio["message"]["metadata"]["intent"], "compare")
        self.assertIsNotNone(cmp_audio["message"]["metadata"]["comparison"])

        # Memory store & recall
        self.engine.handle_message(s["id"], "Remember my budget is 30000 and I have oily skin")
        rec = self.engine.handle_message(s["id"], "What do you remember about me?")
        self.assertEqual(rec["message"]["metadata"]["intent"], "memory_recall")
        self.assertIn("Oily", rec["message"]["content"])

        # Winter Manali trek
        trek = self.engine.handle_message(s["id"], "I am going on a Manali trekking trip in winter")
        self.assertEqual(trek["message"]["metadata"]["intent"], "bundle")
        self.assertTrue(any("Trekking" in p["name"] or "Down" in p["name"] for p in trek["message"]["metadata"]["products"]))

    def test_http_api_end_to_end(self) -> None:
        os.environ["CHATBOT_QUIET"] = "1"
        app = AppContext(products_path=PRODUCTS_PATH, db_path=self.db_path, frontend_dir=FRONTEND_DIR)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            base = f"http://127.0.0.1:{port}"
            with urllib.request.urlopen(f"{base}/api/health") as resp:
                health = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(health["status"], "ok")

            req = urllib.request.Request(
                f"{base}/api/chat",
                data=json.dumps({"message": "Suggest noise cancelling headphones under 5000"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                chat_res = json.loads(resp.read().decode("utf-8"))
                self.assertIn("session", chat_res)
                prods = chat_res["message"]["metadata"]["products"]
                self.assertTrue(any(p["price"] <= 5000 for p in prods))

            with urllib.request.urlopen(f"{base}/") as resp:
                html = resp.read().decode("utf-8")
                self.assertIn("ShopSense AI", html)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

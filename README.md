# ShopSense AI — Intelligent Product Recommendation Chatbot

A full-stack **Virtual Sales Associate for E-Commerce** built with Python and Vanilla JS, backed by **SQLite** for persistent conversation history, shopping memory, wishlist, and cart state.

## Key Capabilities

- **Works for Any Natural-Language Shopping Question**: Uses a hybrid BM25 + semantic concept expansion + constraint extraction engine (budget parsing, brand/color/category detection, climate/lifestyle reasoning) across 48+ curated products in Electronics, Fashion, Footwear, Fitness, Travel, Personal Care, and Home/Office.
- **Persistent Data (SQLite)**:
  - Stores all chat sessions and full message histories (including product cards, comparison tables, and bundles) in `data/chatbot.db`.
  - Automatically learns and persists cross-session user preferences (budgets, brands, skin type, lifestyle interests).
  - Persists Wishlist and Cart items across browser reloads and server restarts.
- **Side-by-Side Product Comparisons**: Generates structured spec tables, pros/cons, and value verdicts for any two or three products.
- **Lifestyle Bundle Builder**: Assembles complete multi-item kits (e.g., Gym starter kit, Goa trip, Manali trek, WFH desk setup, Content Creator kit, Oily skincare routine).
- **Technical Spec Q&A & Multi-Turn Follow-Ups**: Answers questions like *"Is 8GB RAM enough?"*, *"Linen vs cotton for humid weather?"*, *"Show cheaper options"*, or *"Compare the first two"*.
- **Optional Gemini API RAG Mode**: Runs 100% offline out-of-the-box; optionally configure a Gemini API key in Settings (or `GEMINI_API_KEY`) for LLM-generated conversational phrasing grounded in the catalog.

## Run Locally

```bash
python3 run.py
```

Then open `http://127.0.0.1:8000` in your browser.

## Run Tests

```bash
python3 -m unittest discover -s tests -v
```

# ShopSense AI — Intelligent Product Recommendation Chatbot

A full-stack **Virtual Sales Associate for E-Commerce** built with Python, **Streamlit** (ready for **Streamlit Community Cloud**), and **SQLite** for conversation history, shopping memory, wishlist, and cart state.

## Key Capabilities

- **Works for Any Natural-Language Shopping Question**: Uses a hybrid BM25 + semantic concept expansion + constraint extraction engine (budget parsing, brand/color/category detection, climate/lifestyle reasoning) across 73 curated products in Electronics, Fashion, Footwear, Fitness, Travel, Personal Care, and Home/Office.
- **Conversation & Preference Storage (SQLite)**:
  - Stores all chat sessions and full message histories (including product cards, comparison tables, and bundles).
  - Automatically learns and persists cross-session user preferences (budgets, brands, skin type, lifestyle interests).
  - Persists Wishlist and Cart items with quantities.
- **Side-by-Side Product Comparisons**: Generates structured spec tables, pros/cons, and value verdicts for any two or three products—either via chat or the dedicated Compare tab.
- **Lifestyle Bundle Builder**: Assembles complete multi-item kits (e.g., Gym starter kit, Goa trip, Manali trek, WFH desk setup, Content Creator kit, Oily skincare routine).
- **Technical Spec Q&A & Multi-Turn Follow-Ups**: Answers questions like *"Is 8GB RAM enough?"*, *"Linen vs cotton for humid weather?"*, *"Show cheaper options"*, or *"Compare the first two"*.
- **Optional Gemini API RAG Mode**: Works 100% offline out-of-the-box; optionally set `GEMINI_API_KEY` in Streamlit Secrets, environment variables, or in the **Memory & Settings** view for generative phrasing grounded in the catalog.

## Run with Streamlit (Recommended / Streamlit Community Cloud)

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### Deploying to Streamlit Community Cloud

1. Push this repository to GitHub.
2. In [share.streamlit.io](https://share.streamlit.io/), create a new app pointing to:
   - **Repository:** `Vaidehi1005/virtual-sales-associate`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
3. *(Optional)* In **App Settings → Secrets**, add:
   ```toml
   GEMINI_API_KEY = "your-key-here"
   CHATBOT_DB_PATH = "/tmp/shopsense_chatbot.db"
   ```

> **Important Note on Persistence on Streamlit Community Cloud:**
> You can configure the SQLite database path via `CHATBOT_DB_PATH` (environment variable, Streamlit Secrets, or the **Memory & Settings** page). However, **Streamlit Community Cloud's local container filesystem is ephemeral and should not be assumed to persist across app restarts, sleeps, or redeployments**. For durable multi-session cloud persistence across restarts, connect an external hosted database.

## Alternative: Standalone Python HTTP Server

The original zero-dependency HTTP server and static frontend are preserved:

```bash
python3 run.py
```

Then open `http://127.0.0.1:8000`.

## Run Tests

```bash
python3 -m unittest discover -s tests -v
```

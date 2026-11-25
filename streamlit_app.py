"""Streamlit web application entry point for ShopSense AI — Virtual Sales Associate.

Run locally with:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
PRODUCTS_PATH = os.path.join(PROJECT_ROOT, "data", "products.json")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from database import ChatbotDatabase, resolve_db_path
from engine import SalesAssociateEngine


STARTER_PROMPTS: List[Tuple[str, str]] = [
    ("Travel Fashion", "Suggest some black shirts for my upcoming Goa trip."),
    ("Budget Tech", "Recommend the best camera phone under ₹40,000."),
    ("Comparison", "Compare iPhone 16 Pro and Samsung S25 Ultra."),
    ("Student / Coding", "Help me buy a laptop for Computer Engineering studies."),
    ("Lifestyle Bundle", "I am joining a gym next week. What shoes and clothes should I buy?"),
    ("Personal Care", "I am travelling to India next month. Which sunscreen should I purchase?"),
    ("Tech Spec Q&A", "Is 8GB RAM enough for programming and college?"),
    ("WFH & Desk Setup", "Help me build a Work-From-Home desk setup with monitor and chair."),
    ("Audio & Gifting", "Suggest a great gift under ₹15,000 for someone who loves reading or music."),
]

NAV_OPTIONS = [
    "💬 Chat",
    "🛍️ Catalog",
    "⚖️ Compare",
    "🛒 Cart & Wishlist",
    "🧠 Memory & Settings",
]


# ----------------------------------------------------------------------
# Pure / Reusable Helpers
# ----------------------------------------------------------------------


def format_price(price: Any) -> str:
    return f"₹{int(price or 0):,}"


def _read_streamlit_secret(key: str) -> str:
    try:
        val = st.secrets.get(key, "")
        return str(val).strip() if val else ""
    except Exception:
        return ""


def get_configured_db_path(custom_path: Optional[str] = None) -> str:
    """Resolve a writable SQLite path from UI override, env var, secrets, or default."""
    secret_path = _read_streamlit_secret("CHATBOT_DB_PATH")
    candidate = resolve_db_path(
        explicit_path=(custom_path or "").strip() or None,
        default_path=secret_path or os.path.join(PROJECT_ROOT, "data", "chatbot.db"),
    )
    parent = os.path.dirname(candidate)
    try:
        os.makedirs(parent, exist_ok=True)
        probe = os.path.join(parent, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return candidate
    except OSError:
        fallback = os.path.join(tempfile.gettempdir(), "virtual_sales_associate.db")
        return os.path.abspath(fallback)


def sync_gemini_secret() -> None:
    """Expose Streamlit Cloud secret GEMINI_API_KEY to the backend engine if unset."""
    if not os.environ.get("GEMINI_API_KEY"):
        secret_key = _read_streamlit_secret("GEMINI_API_KEY")
        if secret_key:
            os.environ["GEMINI_API_KEY"] = secret_key


def build_comparison_table(comparison: Dict[str, Any]) -> List[Dict[str, str]]:
    """Convert engine comparison payload into tabular rows for Streamlit."""
    products = comparison.get("products", [])
    rows = comparison.get("rows", [])
    table: List[Dict[str, str]] = []
    for row in rows:
        record: Dict[str, str] = {"Spec / Feature": str(row.get("attribute", ""))}
        values = row.get("values", [])
        for idx, prod in enumerate(products):
            col_name = prod.get("name", f"Product {idx + 1}")
            record[col_name] = str(values[idx]) if idx < len(values) else "—"
        table.append(record)
    return table


def filter_catalog_products(
    engine: SalesAssociateEngine,
    query: str = "",
    category: str = "All",
    sort_by: str = "Relevance",
) -> List[Dict[str, Any]]:
    """Filter and sort catalog products using the existing recommendation search."""
    q = (query or "").strip()
    cat = (category or "All").strip()

    if q:
        constraints = {"category": cat} if cat != "All" else None
        ranked = engine.search_products(q, constraints=constraints, top_k=len(engine.products))
        items = [m[0] for m in ranked]
    else:
        items = list(engine.products)
        if cat != "All":
            items = [p for p in items if p["category"].lower() == cat.lower()]

    if sort_by == "Price: Low to High":
        items.sort(key=lambda p: p["price"])
    elif sort_by == "Price: High to Low":
        items.sort(key=lambda p: p["price"], reverse=True)
    elif sort_by == "Top Rated":
        items.sort(key=lambda p: (p.get("rating", 0), p.get("reviews_count", 0)), reverse=True)
    return items


@st.cache_resource
def load_backend(products_path: str, db_path: str) -> Tuple[ChatbotDatabase, SalesAssociateEngine]:
    db = ChatbotDatabase(db_path)
    engine = SalesAssociateEngine(products_path, db)
    return db, engine


# ----------------------------------------------------------------------
# Session State & Actions
# ----------------------------------------------------------------------


def init_session_state(db: ChatbotDatabase) -> None:
    if "active_view" not in st.session_state:
        st.session_state.active_view = "💬 Chat"
    if "compare_selection" not in st.session_state:
        st.session_state.compare_selection = []
    if "queued_prompt" not in st.session_state:
        st.session_state.queued_prompt = None
    if "active_session_id" not in st.session_state:
        sessions = db.list_sessions()
        if sessions:
            st.session_state.active_session_id = sessions[0]["id"]
        else:
            created = db.create_session("New Shopping Chat")
            st.session_state.active_session_id = created["id"]


def ensure_valid_session(db: ChatbotDatabase) -> str:
    sid = st.session_state.get("active_session_id")
    if sid and db.get_session(sid):
        return sid
    sessions = db.list_sessions()
    if sessions:
        st.session_state.active_session_id = sessions[0]["id"]
    else:
        st.session_state.active_session_id = db.create_session("New Shopping Chat")["id"]
    return st.session_state.active_session_id


def toggle_compare_product(product_id: str) -> None:
    selected: List[str] = list(st.session_state.get("compare_selection", []))
    if product_id in selected:
        selected.remove(product_id)
    else:
        if len(selected) >= 3:
            selected.pop(0)
        selected.append(product_id)
    st.session_state.compare_selection = selected


def queue_chat_prompt(prompt: str) -> None:
    st.session_state.queued_prompt = prompt
    st.session_state.active_view = "💬 Chat"


# ----------------------------------------------------------------------
# UI Components
# ----------------------------------------------------------------------


def render_product_card(
    product: Dict[str, Any],
    db: ChatbotDatabase,
    key_prefix: str,
    show_why: bool = True,
) -> None:
    pid = product["id"]
    selected_for_compare = pid in st.session_state.get("compare_selection", [])
    slot = f"{product['slot_label']} • " if product.get("slot_label") else ""

    with st.container(border=True):
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.caption(f"{slot}{product.get('brand', '')} • {product.get('subcategory', '')}")
        with top_right:
            st.markdown(f"**★ {product.get('rating', 0)}**")

        st.markdown(f"**{product['name']}**")

        price_str = f"**{format_price(product['price'])}**"
        orig = product.get("original_price", 0)
        if orig and orig > product["price"]:
            price_str += f"  ~~{format_price(orig)}~~"
        st.markdown(price_str)

        if show_why and product.get("why_recommended"):
            st.info(product["why_recommended"], icon="✨")
        elif product.get("description"):
            desc = product["description"]
            st.caption(desc[:140] + ("..." if len(desc) > 140 else ""))

        specs = list((product.get("specs") or {}).items())[:3]
        if specs:
            st.caption(" | ".join(f"**{k}:** {v}" for k, v in specs))

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("+ Cart", key=f"{key_prefix}_cart_{pid}", use_container_width=True):
                db.save_item(pid, list_type="cart", quantity=1)
                st.toast(f"Added {product['name']} to Cart")
                st.rerun()
        with c2:
            if st.button("♡ Save", key=f"{key_prefix}_wish_{pid}", use_container_width=True):
                db.save_item(pid, list_type="wishlist", quantity=1)
                st.toast(f"Saved {product['name']} to Wishlist")
                st.rerun()
        with c3:
            cmp_label = "✓ Cmp" if selected_for_compare else "Compare"
            if st.button(cmp_label, key=f"{key_prefix}_cmp_{pid}", use_container_width=True):
                toggle_compare_product(pid)
                st.rerun()
        with c4:
            if st.button("Details", key=f"{key_prefix}_det_{pid}", use_container_width=True):
                queue_chat_prompt(f"Tell me more about {product['name']}")
                st.rerun()


def render_sidebar(db: ChatbotDatabase, engine: SalesAssociateEngine, db_path: str) -> None:
    with st.sidebar:
        st.title("🛍️ ShopSense AI")
        st.caption("Virtual Sales Associate for E-Commerce")

        has_gemini = bool(
            db.get_setting("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
        )
        st.markdown(
            f"**Engine:** `{'Gemini RAG Active' if has_gemini else 'Local Hybrid AI'}`  \n"
            f"**Catalog:** `{len(engine.products)} products`"
        )

        st.divider()
        selected_nav = st.radio(
            "Navigation",
            NAV_OPTIONS,
            index=NAV_OPTIONS.index(st.session_state.active_view),
            label_visibility="collapsed",
        )
        if selected_nav != st.session_state.active_view:
            st.session_state.active_view = selected_nav
            st.rerun()

        compare_ids: List[str] = st.session_state.get("compare_selection", [])
        if compare_ids:
            st.divider()
            st.subheader(f"Compare Tray ({len(compare_ids)}/3)")
            names = [
                engine.product_map[pid]["name"]
                for pid in compare_ids
                if pid in engine.product_map
            ]
            for name in names:
                st.caption(f"• {name}")
            col_cmp, col_clr = st.columns(2)
            with col_cmp:
                if len(names) >= 2 and st.button("Compare", key="sb_cmp_go", use_container_width=True, type="primary"):
                    st.session_state.compare_selection = []
                    queue_chat_prompt(f"Compare {' and '.join(names)}")
                    st.rerun()
            with col_clr:
                if st.button("Clear", key="sb_cmp_clr", use_container_width=True):
                    st.session_state.compare_selection = []
                    st.rerun()

        st.divider()
        st.subheader("Conversations")
        if st.button("➕ New Chat", key="sb_new_chat", use_container_width=True, type="primary"):
            new_sess = db.create_session("New Shopping Chat")
            st.session_state.active_session_id = new_sess["id"]
            st.session_state.active_view = "💬 Chat"
            st.rerun()

        active_sid = ensure_valid_session(db)
        sessions = db.list_sessions()
        for sess in sessions[:15]:
            s_col, del_col = st.columns([5, 1])
            is_active = sess["id"] == active_sid
            label = f"{'▶ ' if is_active else ''}{sess['title']}"
            with s_col:
                if st.button(
                    label,
                    key=f"sess_pick_{sess['id']}",
                    use_container_width=True,
                    help=f"{sess.get('message_count', 0)} messages",
                ):
                    st.session_state.active_session_id = sess["id"]
                    st.session_state.active_view = "💬 Chat"
                    st.rerun()
            with del_col:
                if st.button("✕", key=f"sess_del_{sess['id']}", help="Delete conversation"):
                    db.delete_session(sess["id"])
                    if st.session_state.active_session_id == sess["id"]:
                        st.session_state.active_session_id = None
                    st.rerun()

        st.divider()
        cart_items = db.list_saved_items("cart")
        wish_items = db.list_saved_items("wishlist")
        cart_qty = sum(i["quantity"] for i in cart_items)
        cart_total = sum(
            engine.product_map[i["product_id"]]["price"] * i["quantity"]
            for i in cart_items
            if i["product_id"] in engine.product_map
        )
        st.caption(
            f"🛒 **Cart:** {cart_qty} item(s) ({format_price(cart_total)})  \n"
            f"♡ **Wishlist:** {len(wish_items)} item(s)"
        )

        prefs = db.get_preferences()
        if prefs:
            pref_summary = engine._format_memory_summary(prefs)
            if pref_summary:
                st.caption(f"🧠 **Memory:** {pref_summary}")

        st.caption(
            f"💾 **DB:** `{os.path.basename(db_path)}`  \n"
            "⚠️ *Streamlit Cloud Note:* Local SQLite files on Streamlit Community Cloud "
            "are ephemeral and may reset on app restarts or redeployments."
        )


def render_chat_view(db: ChatbotDatabase, engine: SalesAssociateEngine) -> None:
    session_id = ensure_valid_session(db)
    session = db.get_session(session_id)

    # Execute any queued prompt (e.g. starter card, follow-up button, Compare, Details)
    queued = st.session_state.get("queued_prompt")
    if queued:
        st.session_state.queued_prompt = None
        engine.handle_message(session_id, queued)
        st.rerun()

    head_left, head_right = st.columns([4, 1])
    with head_left:
        st.subheader(session["title"] if session else "Shopping Assistant")
    with head_right:
        with st.popover("Rename Chat"):
            new_title = st.text_input(
                "Chat title",
                value=session["title"] if session else "",
                key="rename_chat_input",
            )
            if st.button("Save Title", key="rename_chat_save"):
                if new_title.strip():
                    db.update_session_title(session_id, new_title.strip())
                    st.rerun()

    messages = db.get_messages(session_id)

    if not messages:
        st.markdown(
            "Ask me anything about products — vague lifestyle goals, exact budgets, "
            "side-by-side comparisons, tech specs, or multi-turn follow-ups like "
            "*\"show cheaper options\"* and *\"compare the top 2\"*."
        )
        cols = st.columns(3)
        for idx, (cat, q) in enumerate(STARTER_PROMPTS):
            with cols[idx % 3]:
                with st.container(border=True):
                    st.caption(cat.upper())
                    st.markdown(f"**{q}**")
                    if st.button("Ask this", key=f"starter_{idx}", use_container_width=True):
                        queue_chat_prompt(q)
                        st.rerun()
    else:
        for msg_idx, msg in enumerate(messages):
            role = msg["role"]
            with st.chat_message(role):
                if role == "user":
                    st.markdown(msg["content"])
                    continue

                meta = msg.get("metadata") or {}
                intent_label = str(meta.get("intent", "assistant")).replace("_", " ").title()
                ai_mode = meta.get("ai_mode", "local-hybrid")
                st.caption(f"Intent: **{intent_label}** • Engine: `{ai_mode}`")
                st.markdown(msg["content"])

                bundle = meta.get("bundle")
                if bundle and bundle.get("items"):
                    b_col1, b_col2 = st.columns([3, 1])
                    with b_col1:
                        st.success(
                            f"**{bundle['title']}** — {len(bundle['items'])} curated items • "
                            f"Total: **{format_price(bundle['total_price'])}**"
                        )
                    with b_col2:
                        if st.button(
                            "Add Kit to Cart",
                            key=f"add_bundle_{msg['id']}_{msg_idx}",
                            type="primary",
                            use_container_width=True,
                        ):
                            for item in bundle["items"]:
                                db.save_item(item["id"], list_type="cart", quantity=1)
                            st.toast(f"Added {len(bundle['items'])} bundle items to Cart")
                            st.rerun()

                comparison = meta.get("comparison")
                if comparison and comparison.get("rows"):
                    st.table(build_comparison_table(comparison))

                products = meta.get("products") or []
                if products:
                    for row_start in range(0, len(products), 2):
                        row_prods = products[row_start : row_start + 2]
                        cols = st.columns(2)
                        for col_i, prod in enumerate(row_prods):
                            with cols[col_i]:
                                render_product_card(
                                    prod,
                                    db=db,
                                    key_prefix=f"msg_{msg['id']}_{row_start + col_i}",
                                    show_why=True,
                                )

                alternatives = meta.get("alternatives") or []
                if alternatives:
                    st.markdown("**Other Budget Options:**")
                    alt_cols = st.columns(min(len(alternatives), 3))
                    for a_idx, alt in enumerate(alternatives[:3]):
                        with alt_cols[a_idx]:
                            lbl = f"{alt.get('tier_label', 'Option')}: {alt['name']} ({format_price(alt['price'])})"
                            if st.button(lbl, key=f"alt_{msg['id']}_{a_idx}", use_container_width=True):
                                queue_chat_prompt(f"Tell me more about {alt['name']}")
                                st.rerun()

                follow_ups = meta.get("follow_ups") or []
                if follow_ups and msg_idx == len(messages) - 1:
                    st.markdown("**Suggested Follow-ups:**")
                    f_cols = st.columns(min(len(follow_ups), 4))
                    for f_idx, fq in enumerate(follow_ups[:4]):
                        with f_cols[f_idx]:
                            if st.button(fq, key=f"fu_{msg['id']}_{f_idx}", use_container_width=True):
                                queue_chat_prompt(fq)
                                st.rerun()

    # Must stay at top-level (never inside tabs/columns/expanders)
    user_input = st.chat_input(
        "Ask anything — e.g. 'Best camera phone under ₹40,000', 'Is 8GB RAM enough?', 'Compare iPhone 16 Pro and S25 Ultra'..."
    )
    if user_input and user_input.strip():
        engine.handle_message(session_id, user_input.strip())
        st.rerun()


def render_catalog_view(db: ChatbotDatabase, engine: SalesAssociateEngine) -> None:
    st.subheader("🛍️ Store Product Catalog")
    categories = ["All"] + sorted({p["category"] for p in engine.products})

    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        search_q = st.text_input(
            "Search products, specs, brands, or use cases",
            placeholder="e.g. breathable black shirt, RTX 4050, matte sunscreen...",
        )
    with f2:
        cat_choice = st.selectbox("Category", categories)
    with f3:
        sort_choice = st.selectbox(
            "Sort by",
            ["Relevance", "Price: Low to High", "Price: High to Low", "Top Rated"],
        )

    items = filter_catalog_products(engine, query=search_q, category=cat_choice, sort_by=sort_choice)
    st.caption(f"Showing **{len(items)}** product(s)")

    if not items:
        st.info("No products matched your filter. Try broadening your search.")
        return

    for row_start in range(0, len(items), 3):
        row_items = items[row_start : row_start + 3]
        cols = st.columns(3)
        for idx, prod in enumerate(row_items):
            with cols[idx]:
                render_product_card(
                    prod,
                    db=db,
                    key_prefix=f"cat_{row_start + idx}",
                    show_why=False,
                )


def render_compare_view(db: ChatbotDatabase, engine: SalesAssociateEngine) -> None:
    st.subheader("⚖️ Side-by-Side Product Comparison")
    name_to_prod = {f"{p['name']} ({format_price(p['price'])})": p for p in engine.products}
    labels = list(name_to_prod.keys())

    preselected_labels: List[str] = []
    for pid in st.session_state.get("compare_selection", []):
        p = engine.product_map.get(pid)
        if p:
            lbl = f"{p['name']} ({format_price(p['price'])})"
            if lbl in name_to_prod:
                preselected_labels.append(lbl)

    if len(preselected_labels) < 2 and len(labels) >= 2:
        default_pick = labels[:2]
    else:
        default_pick = preselected_labels[:3]

    chosen_labels = st.multiselect(
        "Select 2 or 3 products to compare",
        options=labels,
        default=default_pick,
        max_selections=3,
    )

    if len(chosen_labels) < 2:
        st.info("Select at least 2 products above to generate a side-by-side comparison.")
        return

    chosen_products = [name_to_prod[lbl] for lbl in chosen_labels]
    comparison = engine._build_comparison(chosen_products, "compare")

    st.markdown(comparison["verdict"])
    st.table(build_comparison_table(comparison))

    cols = st.columns(len(chosen_products))
    for idx, prod in enumerate(chosen_products):
        with cols[idx]:
            render_product_card(prod, db=db, key_prefix=f"cmp_view_{idx}", show_why=False)


def render_saved_view(db: ChatbotDatabase, engine: SalesAssociateEngine) -> None:
    st.subheader("🛒 Shopping Cart & Saved Wishlist")
    col_cart, col_wish = st.columns(2)

    with col_cart:
        st.markdown("### Shopping Cart")
        cart_rows = db.list_saved_items("cart")
        if not cart_rows:
            st.info("Your cart is empty.")
        else:
            total = 0
            for item in cart_rows:
                prod = engine.product_map.get(item["product_id"])
                if not prod:
                    continue
                line_total = prod["price"] * item["quantity"]
                total += line_total
                with st.container(border=True):
                    st.markdown(f"**{prod['name']}**")
                    st.caption(f"{format_price(prod['price'])} × {item['quantity']} = **{format_price(line_total)}**")
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("➖", key=f"cart_dec_{item['id']}", use_container_width=True):
                            db.update_saved_quantity(item["id"], item["quantity"] - 1)
                            st.rerun()
                    with b2:
                        if st.button("➕", key=f"cart_inc_{item['id']}", use_container_width=True):
                            db.update_saved_quantity(item["id"], item["quantity"] + 1)
                            st.rerun()
                    with b3:
                        if st.button("Remove", key=f"cart_rm_{item['id']}", use_container_width=True):
                            db.remove_saved_item(item["id"])
                            st.rerun()
            st.metric("Cart Subtotal", format_price(total))
            if st.button("Clear Cart", key="clear_cart_btn"):
                db.clear_saved_items("cart")
                st.rerun()

    with col_wish:
        st.markdown("### Saved Wishlist")
        wish_rows = db.list_saved_items("wishlist")
        if not wish_rows:
            st.info("Your wishlist is empty.")
        else:
            for item in wish_rows:
                prod = engine.product_map.get(item["product_id"])
                if not prod:
                    continue
                with st.container(border=True):
                    st.markdown(f"**{prod['name']}**")
                    st.caption(f"{format_price(prod['price'])} • ★ {prod['rating']}")
                    w1, w2 = st.columns(2)
                    with w1:
                        if st.button("Move to Cart", key=f"wish_mv_{item['id']}", use_container_width=True, type="primary"):
                            db.save_item(prod["id"], list_type="cart", quantity=1)
                            db.remove_saved_item(item["id"])
                            st.rerun()
                    with w2:
                        if st.button("Remove", key=f"wish_rm_{item['id']}", use_container_width=True):
                            db.remove_saved_item(item["id"])
                            st.rerun()
            if len(wish_rows) >= 2:
                wish_names = [
                    engine.product_map[i["product_id"]]["name"]
                    for i in wish_rows[:3]
                    if i["product_id"] in engine.product_map
                ]
                if len(wish_names) >= 2 and st.button("Compare Wishlist Items", key="cmp_wish_btn"):
                    queue_chat_prompt(f"Compare {' and '.join(wish_names)}")
                    st.rerun()


def render_memory_settings_view(
    db: ChatbotDatabase, engine: SalesAssociateEngine, db_path: str
) -> None:
    st.subheader("🧠 User Preferences, Memory & Deployment Settings")

    st.warning(
        "**Streamlit Community Cloud Storage Notice:** Local SQLite files (including the default "
        "`data/chatbot.db` or `/tmp/...`) live on ephemeral container storage and **should not be assumed "
        "to persist across app restarts, sleeps, or redeployments**. You can configure the database path "
        "via the `CHATBOT_DB_PATH` environment variable / Streamlit Secret or below for the current deployment; "
        "for durable production persistence across restarts, connect an external hosted database.",
        icon="⚠️",
    )

    col_prefs, col_settings = st.columns(2)

    with col_prefs:
        st.markdown("### Stored Shopping Preferences")
        prefs = db.get_preferences()
        if not prefs:
            st.info("No preferences stored yet. Chat normally or add one below!")
        else:
            for key, info in prefs.items():
                val = ", ".join(map(str, info["value"])) if isinstance(info["value"], list) else str(info["value"])
                p1, p2 = st.columns([4, 1])
                with p1:
                    st.markdown(f"**{key}:** `{val}` *({info.get('source', 'inferred')})*")
                with p2:
                    if st.button("Delete", key=f"del_pref_{key}"):
                        db.delete_preference(key)
                        st.rerun()

        with st.form("add_pref_form"):
            st.markdown("**Add / Update Preference**")
            p_key = st.text_input("Preference key", placeholder="e.g. skin_type, preferred_budget_max")
            p_val = st.text_input("Value", placeholder="e.g. Oily / Acne-prone, 35000")
            submitted = st.form_submit_button("Save Preference")
            if submitted and p_key.strip() and p_val.strip():
                val_parsed: Any = p_val.strip()
                if val_parsed.isdigit():
                    val_parsed = int(val_parsed)
                db.set_preference(p_key.strip(), val_parsed, source="user")
                st.toast("Preference saved")
                st.rerun()

        if prefs and st.button("Clear All Preferences", key="clear_all_prefs_btn"):
            db.clear_preferences()
            st.rerun()

        st.markdown("### Recent Query History")
        recent = db.get_recent_queries(limit=10)
        if not recent:
            st.caption("No queries logged yet.")
        else:
            for rq in recent:
                st.caption(f"• `{rq['intent']}` — {rq['query']}")

    with col_settings:
        st.markdown("### Optional Gemini API Key (RAG Enhancement)")
        st.caption(
            "Works 100% offline with the built-in Local Hybrid AI Engine. "
            "Optionally provide a Gemini API key (or set `GEMINI_API_KEY` in Streamlit Secrets) for LLM-phrased replies grounded on catalog products."
        )
        saved_key = db.get_setting("gemini_api_key", "")
        env_key = os.environ.get("GEMINI_API_KEY", "")
        st.caption(
            f"Current status: **{'Configured (' + ('settings' if saved_key else 'env/secrets') + ')' if (saved_key or env_key) else 'Not configured (Local Hybrid AI)'}**"
        )
        new_key = st.text_input("Gemini API Key", type="password", placeholder="Paste Gemini API key (optional)")
        k1, k2 = st.columns(2)
        with k1:
            if st.button("Save API Key", key="save_gem_key", use_container_width=True):
                db.set_setting("gemini_api_key", new_key.strip())
                st.toast("Gemini API setting updated")
                st.rerun()
        with k2:
            if st.button("Remove Saved Key", key="rm_gem_key", use_container_width=True):
                db.set_setting("gemini_api_key", "")
                st.toast("Saved API key removed")
                st.rerun()

        st.divider()
        st.markdown("### Database Path Configuration")
        st.caption(f"Active SQLite path: `{db_path}`")
        custom_db_input = st.text_input(
            "Override SQLite DB path for this session",
            value=st.session_state.get("custom_db_path", ""),
            placeholder="e.g. /tmp/shopsense_chatbot.db",
        )
        d1, d2 = st.columns(2)
        with d1:
            if st.button("Apply DB Path", key="apply_db_path", use_container_width=True):
                st.session_state.custom_db_path = custom_db_input.strip()
                st.session_state.pop("active_session_id", None)
                st.rerun()
        with d2:
            if st.button("Reset to Default", key="reset_db_path", use_container_width=True):
                st.session_state.custom_db_path = ""
                st.session_state.pop("active_session_id", None)
                st.rerun()


# ----------------------------------------------------------------------
# App Entrypoint
# ----------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="ShopSense AI — Virtual Sales Associate",
        page_icon="🛍️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    sync_gemini_secret()
    db_path = get_configured_db_path(st.session_state.get("custom_db_path"))
    db, engine = load_backend(PRODUCTS_PATH, db_path)
    init_session_state(db)

    render_sidebar(db, engine, db_path)

    view = st.session_state.active_view
    if view == "💬 Chat":
        render_chat_view(db, engine)
    elif view == "🛍️ Catalog":
        render_catalog_view(db, engine)
    elif view == "⚖️ Compare":
        render_compare_view(db, engine)
    elif view == "🛒 Cart & Wishlist":
        render_saved_view(db, engine)
    else:
        render_memory_settings_view(db, engine, db_path)


if __name__ == "__main__":
    main()

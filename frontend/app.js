const state = {
  sessionId: null,
  sessions: [],
  messages: [],
  saved: { cart: [], wishlist: [], cart_total: 0 },
  savedTab: "cart",
  compareSelection: [], // array of {id, name}
  preferences: {},
  recentQueries: [],
  isSending: false,
};

const STARTER_PROMPTS = [
  { cat: "Travel Fashion", q: "Suggest some black shirts for my upcoming Goa trip." },
  { cat: "Budget Tech", q: "Recommend the best camera phone under ₹40,000." },
  { cat: "Comparison", q: "Compare iPhone 16 Pro and Samsung S25 Ultra." },
  { cat: "Student / Coding", q: "Help me buy a laptop for Computer Engineering studies." },
  { cat: "Lifestyle Bundle", q: "I am joining a gym next week. What shoes and clothes should I buy?" },
  { cat: "Personal Care", q: "I am travelling to India next month. Which sunscreen should I purchase?" },
  { cat: "Tech Spec Q&A", q: "Is 8GB RAM enough for programming and college?" },
  { cat: "WFH & Desk Setup", q: "Help me build a Work-From-Home desk setup with monitor and chair." },
  { cat: "Audio & Gifting", q: "Suggest a great gift under ₹15,000 for someone who loves reading or music." },
];

// ---- Helpers ----

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatPrice(n) {
  return `₹${Number(n || 0).toLocaleString("en-IN")}`;
}

function renderMarkdown(text) {
  const lines = escapeHtml(text || "").split("\n");
  let html = "";
  let inList = false;

  const formatInline = (s) =>
    s
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>");

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line.startsWith("### ")) {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<h3>${formatInline(line.slice(4))}</h3>`;
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${formatInline(line.slice(2))}</li>`;
    } else if (!line) {
      if (inList) { html += "</ul>"; inList = false; }
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      html += `<p>${formatInline(line)}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.add("hidden"), 2500);
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Request failed (${res.status})`);
  }
  return res.json();
}

// ---- Initialization & Data Loading ----

async function init() {
  bindEvents();
  await Promise.all([refreshHealth(), refreshSessions(), refreshSaved(), refreshMemory()]);
  if (state.sessions.length > 0) {
    await loadSession(state.sessions[0].id);
  } else {
    renderWelcome();
  }
}

async function refreshHealth() {
  const data = await api("/api/health");
  const badge = document.getElementById("aiModeBadge");
  badge.textContent = data.ai_mode === "gemini-rag" ? "Gemini RAG Active" : "Local Hybrid AI";
}

async function refreshSessions() {
  const data = await api("/api/sessions");
  state.sessions = data.sessions || [];
  renderSessionList();
}

async function refreshMemory() {
  const data = await api("/api/memory");
  state.preferences = data.preferences || {};
  state.recentQueries = data.recent_queries || [];
  renderMemorySidebar();
}

async function refreshSaved() {
  const data = await api("/api/saved");
  state.saved = data;
  const totalCount =
    (data.cart || []).reduce((acc, i) => acc + i.quantity, 0) +
    (data.wishlist || []).length;
  document.getElementById("savedBadge").textContent = totalCount;
  document.getElementById("cartCountTab").textContent = (data.cart || []).reduce((acc, i) => acc + i.quantity, 0);
  document.getElementById("wishlistCountTab").textContent = (data.wishlist || []).length;
  renderSavedDrawer();
}

async function createNewChat() {
  const data = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title: "New Shopping Chat" }),
  });
  await refreshSessions();
  await loadSession(data.session.id);
}

async function loadSession(sessionId) {
  state.sessionId = sessionId;
  const data = await api(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
  state.messages = data.messages || [];
  document.getElementById("chatTitle").textContent = data.session.title || "Shopping Chat";
  renderSessionList();
  renderChatFeed();
}

async function deleteSession(sessionId, e) {
  e.stopPropagation();
  await api(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  await refreshSessions();
  if (state.sessionId === sessionId) {
    state.sessionId = null;
    state.messages = [];
    if (state.sessions.length > 0) {
      await loadSession(state.sessions[0].id);
    } else {
      document.getElementById("chatTitle").textContent = "New Shopping Chat";
      renderWelcome();
    }
  }
}

// ---- Rendering ----

function renderSessionList() {
  const container = document.getElementById("sessionList");
  if (!state.sessions.length) {
    container.innerHTML = `<div class="muted small">No saved chats yet. Start asking below!</div>`;
    return;
  }
  container.innerHTML = "";
  for (const s of state.sessions) {
    const btn = document.createElement("div");
    btn.className = `session-item ${s.id === state.sessionId ? "active" : ""}`;
    btn.onclick = () => {
      loadSession(s.id);
      document.getElementById("sidebar").classList.remove("open");
    };
    btn.innerHTML = `
      <div class="session-info">
        <div class="session-title">${escapeHtml(s.title)}</div>
        <div class="session-meta">${s.message_count || 0} msgs</div>
      </div>
      <button class="session-del" title="Delete chat">✕</button>
    `;
    btn.querySelector(".session-del").onclick = (e) => deleteSession(s.id, e);
    container.appendChild(btn);
  }
}

function renderMemorySidebar() {
  const container = document.getElementById("memoryTags");
  const entries = Object.entries(state.preferences);
  if (!entries.length) {
    container.innerHTML = `<span class="memory-empty">Learns your budget, brands &amp; needs automatically.</span>`;
    return;
  }
  container.innerHTML = "";
  for (const [k, obj] of entries) {
    const val = Array.isArray(obj.value) ? obj.value.join(", ") : obj.value;
    const tag = document.createElement("span");
    tag.className = "memory-tag";
    tag.textContent = `${k.replace(/_/g, " ")}: ${val}`;
    container.appendChild(tag);
  }
}

function renderWelcome() {
  const feed = document.getElementById("chatFeed");
  feed.innerHTML = `
    <div class="welcome-box">
      <h2>Ask Your Virtual Sales Associate Anything</h2>
      <p>
        Describe your trip, budget, lifestyle, or technical requirements in plain English — or ask follow-ups like
        <em>"show cheaper options"</em> and <em>"compare the top 2"</em>. All chats and preferences are saved automatically.
      </p>
      <div class="starter-grid">
        ${STARTER_PROMPTS.map(
          (item) => `
            <button class="starter-card" data-q="${escapeHtml(item.q)}">
              <div class="starter-cat">${escapeHtml(item.cat)}</div>
              <div class="starter-q">${escapeHtml(item.q)}</div>
            </button>
          `
        ).join("")}
      </div>
    </div>
  `;
  feed.querySelectorAll(".starter-card").forEach((el) => {
    el.onclick = () => sendMessage(el.dataset.q);
  });
}

function renderChatFeed() {
  const feed = document.getElementById("chatFeed");
  if (!state.messages.length) {
    renderWelcome();
    return;
  }
  feed.innerHTML = "";
  for (const msg of state.messages) {
    const row = document.createElement("div");
    row.className = `msg-row ${msg.role}`;
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";

    if (msg.role === "user") {
      bubble.textContent = msg.content;
    } else {
      const meta = msg.metadata || {};
      const intentLabel = (meta.intent || "assistant").replace("_", " ");
      let inner = `<span class="intent-chip">${escapeHtml(intentLabel)}</span>`;
      inner += `<div class="msg-text">${renderMarkdown(msg.content)}</div>`;

      if (meta.bundle && Array.isArray(meta.bundle.items) && meta.bundle.items.length) {
        const idsJson = escapeHtml(JSON.stringify(meta.bundle.items.map((i) => i.id)));
        inner += `
          <div class="bundle-banner">
            <div>
              <strong>${escapeHtml(meta.bundle.title)}</strong>
              <span class="muted"> (${meta.bundle.items.length} items • Total ${formatPrice(meta.bundle.total_price)})</span>
            </div>
            <button class="btn-primary add-bundle-btn" data-ids="${idsJson}">Add Entire Kit to Cart</button>
          </div>
        `;
      }

      if (meta.comparison && meta.comparison.rows) {
        inner += renderComparisonHtml(meta.comparison);
      }

      if (Array.isArray(meta.products) && meta.products.length) {
        inner += `<div class="products-grid">${meta.products.map(renderProductCardHtml).join("")}</div>`;
      }

      if (Array.isArray(meta.alternatives) && meta.alternatives.length) {
        inner += `<div class="alt-strip"><strong>Other Budgets:</strong> ${meta.alternatives
          .map(
            (a) =>
              `<button class="alt-pill" data-q="Tell me more about ${escapeHtml(a.name)}">${escapeHtml(a.tier_label)}: ${escapeHtml(a.name)} (${formatPrice(a.price)})</button>`
          )
          .join("")}</div>`;
      }

      if (Array.isArray(meta.follow_ups) && meta.follow_ups.length) {
        inner += `<div class="followup-row">${meta.follow_ups
          .map((f) => `<button class="followup-chip" data-q="${escapeHtml(f)}">${escapeHtml(f)}</button>`)
          .join("")}</div>`;
      }

      bubble.innerHTML = inner;
      attachMessageListeners(bubble);
    }

    row.appendChild(bubble);
    feed.appendChild(row);
  }
  feed.scrollTop = feed.scrollHeight;
}

function renderComparisonHtml(comp) {
  const headers = comp.products.map((p) => `<th>${escapeHtml(p.name)}</th>`).join("");
  const rows = comp.rows
    .map(
      (r) =>
        `<tr><td>${escapeHtml(r.attribute)}</td>${r.values
          .map((v) => `<td>${escapeHtml(v)}</td>`)
          .join("")}</tr>`
    )
    .join("");
  return `
    <div class="compare-wrap">
      <table class="compare-table">
        <thead><tr><th>Spec / Feature</th>${headers}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderProductCardHtml(p) {
  const isSelected = state.compareSelection.some((c) => c.id === p.id);
  const specEntries = Object.entries(p.specs || {}).slice(0, 3);
  const slot = p.slot_label ? `${p.slot_label} • ` : "";
  return `
    <div class="product-card" data-pid="${escapeHtml(p.id)}">
      <div class="product-top">
        <span class="product-cat">${escapeHtml(slot + p.subcategory)}</span>
        <span class="product-rating">★ ${p.rating}</span>
      </div>
      <div class="product-name">${escapeHtml(p.name)}</div>
      <div class="product-price-row">
        <span class="product-price">${formatPrice(p.price)}</span>
        ${p.original_price > p.price ? `<span class="product-mrp">${formatPrice(p.original_price)}</span>` : ""}
      </div>
      ${p.why_recommended ? `<div class="product-why">${escapeHtml(p.why_recommended)}</div>` : ""}
      <div class="spec-chips">
        ${specEntries.map(([k, v]) => `<span class="spec-chip">${escapeHtml(k)}: ${escapeHtml(v)}</span>`).join("")}
      </div>
      <div class="product-actions">
        <button class="mini-btn primary act-cart" data-id="${escapeHtml(p.id)}">+ Cart</button>
        <button class="mini-btn act-wish" data-id="${escapeHtml(p.id)}">♡ Save</button>
        <button class="mini-btn act-cmp ${isSelected ? "selected" : ""}" data-id="${escapeHtml(p.id)}" data-name="${escapeHtml(p.name)}">
          ${isSelected ? "✓ Compare" : "Compare"}
        </button>
        <button class="mini-btn act-ask" data-name="${escapeHtml(p.name)}">Details</button>
      </div>
    </div>
  `;
}

function attachMessageListeners(container) {
  container.querySelectorAll(".act-cart").forEach((btn) => {
    btn.onclick = () => addToSaved([btn.dataset.id], "cart");
  });
  container.querySelectorAll(".act-wish").forEach((btn) => {
    btn.onclick = () => addToSaved([btn.dataset.id], "wishlist");
  });
  container.querySelectorAll(".act-cmp").forEach((btn) => {
    btn.onclick = () => toggleCompareSelection(btn.dataset.id, btn.dataset.name);
  });
  container.querySelectorAll(".act-ask").forEach((btn) => {
    btn.onclick = () => sendMessage(`Tell me more about ${btn.dataset.name}`);
  });
  container.querySelectorAll(".add-bundle-btn").forEach((btn) => {
    btn.onclick = () => addToSaved(JSON.parse(btn.dataset.ids), "cart");
  });
  container.querySelectorAll(".followup-chip, .alt-pill").forEach((btn) => {
    btn.onclick = () => sendMessage(btn.dataset.q);
  });
}

// ---- Actions ----

async function sendMessage(text) {
  const trimmed = (text ?? document.getElementById("chatInput").value).trim();
  if (!trimmed || state.isSending) return;

  state.isSending = true;
  document.getElementById("sendBtn").disabled = true;
  document.getElementById("chatInput").value = "";

  // Optimistic user bubble
  state.messages.push({ role: "user", content: trimmed, metadata: {} });
  renderChatFeed();

  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: state.sessionId, message: trimmed }),
    });
    state.sessionId = data.session.id;
    document.getElementById("chatTitle").textContent = data.session.title;
    state.messages.push(data.message);
    renderChatFeed();
    await Promise.all([refreshSessions(), refreshMemory(), refreshSaved()]);
  } catch (err) {
    showToast(`Error: ${err.message}`);
  } finally {
    state.isSending = false;
    document.getElementById("sendBtn").disabled = false;
    document.getElementById("chatInput").focus();
  }
}

async function addToSaved(productIds, listType) {
  await api("/api/saved", {
    method: "POST",
    body: JSON.stringify({ product_ids: productIds, list_type: listType, quantity: 1 }),
  });
  await refreshSaved();
  showToast(`Added ${productIds.length > 1 ? `${productIds.length} items` : "item"} to ${listType}`);
}

function toggleCompareSelection(id, name) {
  const idx = state.compareSelection.findIndex((i) => i.id === id);
  if (idx >= 0) {
    state.compareSelection.splice(idx, 1);
  } else {
    if (state.compareSelection.length >= 3) {
      state.compareSelection.shift();
    }
    state.compareSelection.push({ id, name });
  }
  const btn = document.getElementById("compareSelectedBtn");
  document.getElementById("compareCount").textContent = state.compareSelection.length;
  btn.classList.toggle("hidden", state.compareSelection.length < 2);
  renderChatFeed();
}

function renderSavedDrawer() {
  const body = document.getElementById("savedDrawerBody");
  const foot = document.getElementById("savedDrawerFoot");
  const items = state.saved[state.savedTab] || [];

  if (!items.length) {
    body.innerHTML = `<p class="muted">Your ${state.savedTab} is empty.</p>`;
    foot.innerHTML = "";
    return;
  }

  body.innerHTML = items
    .map(
      (item) => `
      <div class="saved-row">
        <div>
          <div class="session-title">${escapeHtml(item.product.name)}</div>
          <div class="session-meta">${formatPrice(item.product.price)} ${state.savedTab === "cart" ? `× ${item.quantity}` : ""}</div>
        </div>
        <div style="display:flex;gap:6px;">
          ${
            state.savedTab === "wishlist"
              ? `<button class="mini-btn primary move-cart" data-pid="${escapeHtml(item.product_id)}">+ Cart</button>`
              : `<button class="mini-btn qty-dec" data-id="${item.id}" data-qty="${item.quantity - 1}">-</button>
                 <button class="mini-btn qty-inc" data-id="${item.id}" data-qty="${item.quantity + 1}">+</button>`
          }
          <button class="mini-btn rm-saved" data-id="${item.id}">✕</button>
        </div>
      </div>
    `
    )
    .join("");

  foot.innerHTML =
    state.savedTab === "cart"
      ? `<span>Cart Total</span><span>${formatPrice(state.saved.cart_total)}</span>`
      : `<span>${items.length} Saved Items</span>`;

  body.querySelectorAll(".rm-saved").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/saved/${b.dataset.id}`, { method: "DELETE" });
      await refreshSaved();
    };
  });
  body.querySelectorAll(".qty-dec, .qty-inc").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/saved/${b.dataset.id}`, {
        method: "PATCH",
        body: JSON.stringify({ quantity: Number(b.dataset.qty) }),
      });
      await refreshSaved();
    };
  });
  body.querySelectorAll(".move-cart").forEach((b) => {
    b.onclick = () => addToSaved([b.dataset.pid], "cart");
  });
}

async function openCatalogModal() {
  document.getElementById("catalogModalBackdrop").classList.remove("hidden");
  await loadCatalog();
}

async function loadCatalog() {
  const q = document.getElementById("catalogSearch").value.trim();
  const cat = document.getElementById("catalogCategory").value;
  const data = await api(`/api/products?q=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}`);
  const catSel = document.getElementById("catalogCategory");
  if (catSel.options.length <= 1) {
    for (const c of data.categories || []) {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      catSel.appendChild(opt);
    }
  }
  const grid = document.getElementById("catalogGrid");
  grid.innerHTML = (data.products || []).map(renderProductCardHtml).join("") || `<p class="muted">No products matched.</p>`;
  attachMessageListeners(grid);
}

async function openSettingsModal() {
  document.getElementById("settingsModalBackdrop").classList.remove("hidden");
  await refreshMemory();
  const settings = await api("/api/settings");
  document.getElementById("geminiStatusText").textContent = settings.gemini_configured
    ? `Gemini API key is active (source: ${settings.gemini_source}).`
    : "Using Local Hybrid NLU Engine (no API key required).";

  const list = document.getElementById("memoryListModal");
  const entries = Object.entries(state.preferences);
  list.innerHTML = entries.length
    ? entries
        .map(([k, obj]) => {
          const val = Array.isArray(obj.value) ? obj.value.join(", ") : obj.value;
          return `<div class="mem-row"><span><strong>${escapeHtml(k)}:</strong> ${escapeHtml(val)}</span><button class="link-btn del-mem" data-k="${escapeHtml(k)}">Remove</button></div>`;
        })
        .join("")
    : `<p class="muted small">No saved preferences yet.</p>`;

  list.querySelectorAll(".del-mem").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/memory/${encodeURIComponent(b.dataset.k)}`, { method: "DELETE" });
      await openSettingsModal();
    };
  });

  const rq = document.getElementById("recentQueriesModal");
  rq.innerHTML = state.recentQueries.length
    ? state.recentQueries
        .slice(0, 8)
        .map((r) => `<div class="mem-row"><span>${escapeHtml(r.query)}</span><span class="muted small">${escapeHtml(r.intent)}</span></div>`)
        .join("")
    : `<p class="muted small">No past queries recorded yet.</p>`;
}

// ---- Event Binding ----

function bindEvents() {
  document.getElementById("newChatBtn").onclick = createNewChat;

  document.getElementById("chatForm").onsubmit = (e) => {
    e.preventDefault();
    sendMessage();
  };

  document.getElementById("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  document.getElementById("compareSelectedBtn").onclick = () => {
    if (state.compareSelection.length >= 2) {
      const names = state.compareSelection.map((i) => i.name).join(" and ");
      state.compareSelection = [];
      document.getElementById("compareSelectedBtn").classList.add("hidden");
      sendMessage(`Compare ${names}`);
    }
  };

  document.getElementById("toggleSidebarBtn").onclick = () => {
    document.getElementById("sidebar").classList.toggle("open");
  };

  document.getElementById("openSavedBtn").onclick = () => {
    document.getElementById("savedDrawerBackdrop").classList.remove("hidden");
    renderSavedDrawer();
  };
  document.getElementById("closeSavedBtn").onclick = () => {
    document.getElementById("savedDrawerBackdrop").classList.add("hidden");
  };
  document.querySelectorAll(".tabs .tab").forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll(".tabs .tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      state.savedTab = tab.dataset.tab;
      renderSavedDrawer();
    };
  });

  document.getElementById("openCatalogBtn").onclick = openCatalogModal;
  document.getElementById("closeCatalogBtn").onclick = () => {
    document.getElementById("catalogModalBackdrop").classList.add("hidden");
  };
  document.getElementById("catalogSearch").oninput = loadCatalog;
  document.getElementById("catalogCategory").onchange = loadCatalog;

  document.getElementById("openSettingsBtn").onclick = openSettingsModal;
  document.getElementById("openMemoryBtn").onclick = openSettingsModal;
  document.getElementById("closeSettingsBtn").onclick = () => {
    document.getElementById("settingsModalBackdrop").classList.add("hidden");
  };

  document.getElementById("addPrefForm").onsubmit = async (e) => {
    e.preventDefault();
    const key = document.getElementById("prefKeyInput").value.trim();
    const value = document.getElementById("prefValInput").value.trim();
    await api("/api/memory", { method: "POST", body: JSON.stringify({ key, value }) });
    document.getElementById("prefKeyInput").value = "";
    document.getElementById("prefValInput").value = "";
    await openSettingsModal();
    showToast("Preference saved");
  };

  document.getElementById("clearAllMemoryBtn").onclick = async () => {
    await api("/api/memory", { method: "DELETE" });
    await openSettingsModal();
    showToast("Cleared saved preferences");
  };

  document.getElementById("saveGeminiKeyBtn").onclick = async () => {
    const key = document.getElementById("geminiKeyInput").value.trim();
    await api("/api/settings", { method: "POST", body: JSON.stringify({ gemini_api_key: key }) });
    document.getElementById("geminiKeyInput").value = "";
    await Promise.all([refreshHealth(), openSettingsModal()]);
    showToast("AI settings updated");
  };

  document.getElementById("clearGeminiKeyBtn").onclick = async () => {
    await api("/api/settings", { method: "POST", body: JSON.stringify({ gemini_api_key: "" }) });
    await Promise.all([refreshHealth(), openSettingsModal()]);
    showToast("Gemini API key removed");
  };
}

init();

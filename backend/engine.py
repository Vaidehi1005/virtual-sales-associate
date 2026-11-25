"""General-purpose AI Virtual Sales Associate engine.

Supports arbitrary natural-language shopping questions, multi-turn contextual
follow-ups, side-by-side product comparisons, lifestyle bundle assembly,
technical spec Q&A, budget alternatives, persistent cross-session user memory,
and optional Gemini API RAG enhancement.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

try:
    from database import ChatbotDatabase
except ImportError:
    from .database import ChatbotDatabase

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None


STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "am", "be", "been", "being",
    "i", "me", "my", "we", "our", "you", "your", "it", "its", "this", "that",
    "these", "those", "for", "of", "to", "in", "on", "at", "by", "with", "from",
    "and", "or", "but", "so", "if", "as", "into", "about", "what", "which",
    "who", "whom", "how", "why", "when", "where", "can", "could", "should",
    "would", "will", "do", "does", "did", "have", "has", "had", "want", "need",
    "looking", "suggest", "recommend", "help", "buy", "purchase", "get", "find",
    "show", "give", "tell", "please", "some", "any", "best", "good", "better",
    "top", "great", "nice", "really", "very", "much", "more", "most", "upcoming",
    "next", "month", "week", "day", "days", "going", "joining", "planning",
}

CONCEPT_EXPANSIONS: Dict[str, List[str]] = {
    "goa": ["beach", "tropical", "humid", "summer", "breathable", "linen", "resort", "vacation", "sunscreen", "sandals", "sunglasses"],
    "beach": ["tropical", "humid", "resort", "linen", "quick dry", "waterproof", "sandals", "sunscreen", "polarized"],
    "tropical": ["humid", "breathable", "linen", "seersucker", "viscose", "sunscreen", "spf", "matte"],
    "humid": ["breathable", "linen", "viscose", "seersucker", "matte", "oil-free", "lightweight", "sweat"],
    "summer": ["breathable", "linen", "cotton", "lightweight", "sunscreen", "spf", "shorts", "cooling"],
    "india": ["humid", "tropical", "spf 50", "sunscreen", "no white cast", "travel", "sweat resistant"],
    "travel": ["portable", "lightweight", "packable", "power bank", "backpack", "carry-on", "quick dry", "battery"],
    "trip": ["travel", "packable", "portable", "lightweight", "vacation", "backpack"],
    "manali": ["winter", "cold", "puffer", "down", "jacket", "trekking", "hiking", "waterproof", "warm"],
    "hill": ["winter", "puffer", "jacket", "trekking", "hiking", "waterproof", "warm"],
    "trek": ["trekking", "hiking", "waterproof", "lugs", "windcheater", "outdoor"],
    "trekking": ["hiking", "waterproof", "lugs", "windcheater", "mountain"],
    "hiking": ["trekking", "waterproof", "lugs", "mountain", "outdoor"],
    "winter": ["puffer", "down", "hoodie", "fleece", "warm", "jacket"],
    "monsoon": ["waterproof", "rain", "windcheater", "ip68", "eva", "sandals", "quick dry"],
    "rain": ["waterproof", "windcheater", "ip68", "sandals"],
    "gym": ["workout", "training", "dri-fit", "shorts", "cross trainer", "running shoes", "water bottle", "duffel", "gym bag", "socks"],
    "workout": ["gym", "training", "sweat wicking", "shorts", "shoes", "yoga mat", "dumbbells", "bottle"],
    "fitness": ["gym", "workout", "running", "smartwatch", "yoga mat", "dumbbells"],
    "walking": ["cushioning", "memory foam", "slip-in", "arch support", "lightweight", "gel", "daily walking"],
    "running": ["cushioning", "breathable", "running shoes", "gps", "anti-blister", "socks"],
    "coding": ["programming", "16gb ram", "thinkpad", "macbook", "linux", "keyboard", "monitor", "developer"],
    "programming": ["coding", "16gb ram", "processor", "thinkpad", "macbook", "virtualization", "linux", "multitasking"],
    "engineering": ["programming", "virtualization", "16gb ram", "rtx", "cad", "multitasking", "thinkpad", "vivobook", "victus"],
    "computer": ["programming", "coding", "16gb ram", "laptop", "virtualization", "ssd"],
    "college": ["student", "laptop", "backpack", "tablet", "budget", "portable", "battery"],
    "student": ["college", "budget", "value", "laptop", "tablet", "headphones"],
    "content": ["creator", "4k", "camera", "vlogging", "microphone", "tripod", "gimbal", "oled", "rtx"],
    "creator": ["content creation", "4k", "120fps", "vlogging", "mic", "gimbal", "tripod", "oled"],
    "youtube": ["vlogging", "microphone", "tripod", "gimbal", "4k", "camera", "creator"],
    "vlog": ["vlogging", "selfie", "front camera", "gimbal", "tripod", "mic", "4k"],
    "vlogging": ["selfie", "front camera", "gimbal", "tripod", "mic", "4k"],
    "podcast": ["microphone", "usb mic", "anc headphones", "cardioid"],
    "photography": ["camera", "ois", "telephoto", "zeiss", "leica", "pixel", "200mp", "night sight"],
    "camera": ["photography", "ois", "telephoto", "sensor", "4k", "pixel", "vivo", "xiaomi"],
    "gaming": ["rtx", "144hz", "snapdragon", "vapor chamber", "esports", "gaming mouse", "gpu"],
    "wfh": ["work from home", "monitor", "ergonomic chair", "keyboard", "mouse", "anc", "microphone"],
    "desk": ["monitor", "ergonomic chair", "mechanical keyboard", "mouse", "usb-c"],
    "office": ["formal", "chinos", "oxford", "ergonomic", "laptop", "anc", "calls"],
    "formal": ["oxford", "chinos", "smart casual", "interview", "office"],
    "party": ["viscose", "resort", "speaker", "jbl", "evening", "drape"],
    "oily": ["matte", "oil-free", "gel", "niacinamide", "non-comedogenic", "acne"],
    "acne": ["non-comedogenic", "silicone", "matte", "dermatologist", "gentle cleanser"],
    "sensitive": ["fragrance-free", "dermatologist", "gentle", "non-comedogenic", "spf 50"],
    "skincare": ["sunscreen", "cleanser", "moisturizer", "serum", "spf", "vitamin c"],
    "gift": ["kindle", "speaker", "espresso", "trimmer", "smartwatch", "airpods", "sunglasses"],
    "gifting": ["kindle", "speaker", "espresso", "trimmer", "smartwatch", "airpods", "sunglasses"],
    "reading": ["kindle", "e-reader", "ipad", "tablet", "glare-free"],
    "music": ["headphones", "earbuds", "anc", "ldac", "speaker", "jbl", "sony"],
    "coffee": ["espresso", "cappuccino", "kitchen"],
    "beard": ["trimmer", "grooming", "philips"],
    "grooming": ["trimmer", "philips", "cleanser", "skincare"],
    "battery": ["6000 mah", "5500 mah", "18 hours", "14 days", "power bank", "fast charging"],
}

CATEGORY_SYNONYMS: Dict[str, Tuple[Optional[str], Optional[str]]] = {
    "phone": ("Electronics", "Smartphones"),
    "phones": ("Electronics", "Smartphones"),
    "smartphone": ("Electronics", "Smartphones"),
    "smartphones": ("Electronics", "Smartphones"),
    "mobile": ("Electronics", "Smartphones"),
    "iphone": ("Electronics", "Smartphones"),
    "laptop": ("Electronics", "Laptops"),
    "laptops": ("Electronics", "Laptops"),
    "notebook": ("Electronics", "Laptops"),
    "macbook": ("Electronics", "Laptops"),
    "tablet": ("Electronics", "Tablets"),
    "tablets": ("Electronics", "Tablets"),
    "ipad": ("Electronics", "Tablets"),
    "shirt": ("Fashion", "Shirts"),
    "shirts": ("Fashion", "Shirts"),
    "tshirt": ("Fashion", None),
    "t-shirt": ("Fashion", None),
    "polo": ("Fashion", "T-Shirts"),
    "shorts": ("Fashion", None),
    "chinos": ("Fashion", "Bottoms"),
    "pants": ("Fashion", "Bottoms"),
    "trousers": ("Fashion", "Bottoms"),
    "jacket": ("Fashion", "Outerwear"),
    "hoodie": ("Fashion", "Activewear"),
    "clothes": ("Fashion", None),
    "clothing": ("Fashion", None),
    "wear": ("Fashion", None),
    "outfit": ("Fashion", None),
    "shoe": ("Footwear", None),
    "shoes": ("Footwear", None),
    "footwear": ("Footwear", None),
    "sneakers": ("Footwear", None),
    "sandal": ("Footwear", "Sandals"),
    "sandals": ("Footwear", "Sandals"),
    "sunscreen": ("Personal Care", "Sunscreen"),
    "spf": ("Personal Care", "Sunscreen"),
    "sunblock": ("Personal Care", "Sunscreen"),
    "cleanser": ("Personal Care", "Cleansers"),
    "facewash": ("Personal Care", "Cleansers"),
    "moisturizer": ("Personal Care", "Moisturizers"),
    "serum": ("Personal Care", "Serums"),
    "trimmer": ("Personal Care", "Grooming"),
    "skincare": ("Personal Care", None),
    "headphone": ("Electronics", "Audio"),
    "headphones": ("Electronics", "Audio"),
    "earbuds": ("Electronics", "Audio"),
    "earphones": ("Electronics", "Audio"),
    "speaker": ("Electronics", "Audio"),
    "watch": ("Fitness & Sports", "Wearables"),
    "smartwatch": ("Fitness & Sports", "Wearables"),
    "bottle": ("Fitness & Sports", "Hydration"),
    "backpack": ("Travel & Bags", "Backpacks"),
    "bag": (None, None),
    "monitor": ("Electronics", "Monitors"),
    "keyboard": ("Electronics", "Peripherals"),
    "mouse": ("Electronics", "Peripherals"),
    "mic": ("Electronics", "Creator Gear"),
    "microphone": ("Electronics", "Creator Gear"),
    "tripod": ("Electronics", "Creator Gear"),
    "chair": ("Home & Office", "Furniture"),
    "kindle": ("Electronics", "E-Readers"),
    "espresso": ("Home & Kitchen", "Coffee Makers"),
    "coffee": ("Home & Kitchen", "Coffee Makers"),
}

COLORS = {
    "black", "white", "blue", "navy", "grey", "gray", "silver", "green",
    "olive", "beige", "khaki", "red", "yellow", "pink", "purple", "brown",
    "charcoal", "titanium", "teal",
}


class TechKnowledgeBase:
    """Answers general product, specification, and shopping advice questions."""

    TOPICS: List[Dict[str, Any]] = [
        {
            "patterns": [r"\b8\s*gb\b.*\bram\b", r"\bram\b.*\benough\b", r"\b8gb\s+vs\s+16gb\b", r"\bhow much ram\b"],
            "title": "Is 8GB RAM Enough?",
            "answer": (
                "**It depends on your device and workload:**\n"
                "- **For Smartphones:** **8GB RAM is plenty** for smooth photography, social media, and daily apps (only heavy mobile gamers or 7-year power users benefit from 12GB).\n"
                "- **For Laptops (Programming / College / Multitasking):** **8GB RAM is tight.** Browsers + VS Code + Docker/VMs easily cross 10–12GB. **16GB RAM** is the sweet spot for Computer Engineering and smooth multitasking; aim for **upgradeable 16GB** if you run heavy VMs or local AI models."
            ),
            "search_query": "16GB RAM laptop programming",
            "follow_ups": [
                "Recommend programming laptops with 16GB RAM",
                "Compare ThinkPad E14 and MacBook Air M3",
                "Best laptops under ₹50,000 with 16GB RAM",
            ],
        },
        {
            "patterns": [r"\bprocessor\b.*\b(program|coding|develop|engineer|cs)\b", r"\bcpu\b.*\b(program|coding)\b", r"\bwhich processor\b"],
            "title": "Best Processors for Programming & Engineering",
            "answer": (
                "For programming, compiling, and running containers/VMs, prioritize **multi-core performance and efficiency**:\n"
                "- **Great Value / Mid-Range:** **AMD Ryzen 7 (7735HS / 7840HS)** or **Intel Core i5/i7 H-series (13th Gen+)** — strong multi-core speed for builds and Docker.\n"
                "- **Ultrabook / AI & Battery Balance:** **Intel Core Ultra 5 / Ultra 7** — cool running with dedicated NPU and solid battery.\n"
                "- **Best Battery + Unix Workflow:** **Apple M3 / M2** — unbeatable performance-per-watt and silent fanless operation for web, mobile, and backend dev."
            ),
            "search_query": "laptop programming computer engineering",
            "follow_ups": [
                "Show me laptops for Computer Engineering",
                "Do I need a dedicated GPU for engineering?",
                "Compare MacBook Air M3 and Lenovo ThinkPad E14",
            ],
        },
        {
            "patterns": [r"\b(gpu|graphics card|rtx)\b.*\b(need|require|engineer|ml|ai|coding)\b", r"\bdedicated gpu\b"],
            "title": "Do You Need a Dedicated GPU?",
            "answer": (
                "- **Skip a heavy GPU** if you mostly do web dev, DSA, backend APIs, Python scripting, or mobile apps — integrated GPUs (M3, Radeon 780M, Intel Arc) give you lighter laptops and 2x better battery life.\n"
                "- **Get a dedicated NVIDIA RTX GPU (RTX 4050/4060)** if you do **local Machine Learning/CUDA, 3D CAD/SolidWorks, game dev (Unreal/Unity), 4K video editing, or AAA gaming**."
            ),
            "search_query": "RTX 4050 laptop engineering",
            "follow_ups": [
                "Show RTX laptops for ML and gaming",
                "Show lightweight coding laptops without heavy GPU",
            ],
        },
        {
            "patterns": [r"\boled\b.*\b(ips|lcd|amoled)\b", r"\b(ips|lcd)\b.*\boled\b", r"\bamoled\b.*\bvs\b"],
            "title": "OLED / AMOLED vs IPS LCD Displays",
            "answer": (
                "- **OLED / AMOLED:** Per-pixel lighting gives **true blacks, infinite contrast, vibrant DCI-P3 colors, and faster response times**. Ideal for content creators, media consumption, and outdoor smartphone visibility.\n"
                "- **IPS LCD:** Usually **more affordable, zero burn-in risk on static code/IDE sidebars, and sharp subpixel text clarity** — great for long coding and office spreadsheets."
            ),
            "search_query": "OLED laptop AMOLED phone",
            "follow_ups": [
                "Show OLED laptops for creators",
                "Compare budget AMOLED phones under ₹30,000",
            ],
        },
        {
            "patterns": [r"\b128\s*gb\b.*\b256\s*gb\b", r"\bhow much storage\b", r"\b128gb\b.*\benough\b"],
            "title": "Is 128GB Storage Enough or Should You Get 256GB?",
            "answer": (
                "- **128GB:** Fine if you stream music/video, store photos in the cloud, and install standard apps.\n"
                "- **256GB (Recommended):** Much safer for **4K video recording, offline playlists, large games, or keeping a phone 3–4+ years** — and essential on laptops (**512GB SSD minimum** for coding/IDEs/Docker)."
            ),
            "search_query": "256GB smartphone 512GB laptop",
            "follow_ups": [
                "Show 256GB camera phones under ₹40,000",
                "Show laptops with 1TB SSD",
            ],
        },
        {
            "patterns": [r"\bip6[78]\b", r"\bwaterproof\b", r"\bwater resistant\b"],
            "title": "Understanding IP67 / IP68 Water & Dust Resistance",
            "answer": (
                "- **IP54:** Splash & sweat resistant (safe for gym workouts and light drizzle).\n"
                "- **IP67:** Dust-tight and survives immersion in up to **1m of fresh water for 30 mins**.\n"
                "- **IP68:** Dust-tight and rated for **1.5m+ water immersion** — great peace of mind for monsoon commutes and beach travel."
            ),
            "search_query": "IP68 waterproof phone speaker",
            "follow_ups": [
                "Show IP68 waterproof phones",
                "Show waterproof speakers for beach trips",
            ],
        },
        {
            "patterns": [r"\banc\b", r"\bnoise cancell?ing\b", r"\bheadphones\b.*\bearbuds\b", r"\bearbuds\b.*\bheadphones\b"],
            "title": "Over-Ear ANC Headphones vs TWS Earbuds",
            "answer": (
                "- **Over-Ear ANC Headphones** (e.g., Sony WH-1000XM5, Soundcore Q20i): Stronger passive+active noise isolation for **flights, WFH calls, and deep coding focus**, plus 30–40hr battery.\n"
                "- **TWS Earbuds** (e.g., AirPods Pro 2, Nothing Ear (a)): Pocketable and **IP54 sweat-resistant**, making them far better for **gym workouts, running, and hot commutes**."
            ),
            "search_query": "ANC headphones wireless earbuds",
            "follow_ups": [
                "Compare Sony WH-1000XM5 and Soundcore Q20i",
                "Best earbuds for gym and commute",
            ],
        },
        {
            "patterns": [r"\bspf\b", r"\bpa\+\+", r"\bsunscreen\b.*\b(which|how|choose|india|oily|white cast)\b"],
            "title": "Choosing the Right Sunscreen (Especially for India & Humid Weather)",
            "answer": (
                "Look for 4 key labels when buying sunscreen:\n"
                "1. **SPF 50** (blocks ~98% UVB rays causing sunburn) + **PA+++ or PA++++** (strong UVA defense against tanning & aging).\n"
                "2. **Climate & Skin Match:** For **humid Indian heat or oily skin**, choose **matte silicone-gel or ultra-light fluid** formulas so it doesn't feel greasy.\n"
                "3. **No White Cast:** Modern chemical/hybrid filters (like Uvinul T150, Tinosorb) blend invisibly on deeper skin tones.\n"
                "4. **Water/Sweat Resistance:** Essential if you're walking outdoors, at the beach, or sweating."
            ),
            "search_query": "sunscreen SPF 50 India humid",
            "follow_ups": [
                "Best matte sunscreen for oily skin",
                "Best budget sunscreen with zero white cast",
                "Build me a summer skincare routine",
            ],
        },
        {
            "patterns": [r"\blinen\b.*\bcotton\b", r"\bcotton\b.*\blinen\b", r"\bfabric\b.*\b(summer|humid|goa|hot)\b"],
            "title": "Linen vs Cotton vs Viscose for Hot & Humid Weather",
            "answer": (
                "- **100% Linen:** Most breathable natural fiber — wicks sweat fast and dries quickly, even in dark colors like black. Wrinkles naturally.\n"
                "- **Cotton-Linen Blend / Seersucker:** Best balance for travel — nearly as airy as linen while resisting suitcase creases.\n"
                "- **Viscose / Rayon:** Silky, cool-to-touch drape that won't cling in coastal humidity — great for evening wear."
            ),
            "search_query": "black shirt goa breathable linen",
            "follow_ups": [
                "Suggest black shirts for Goa",
                "Show travel shorts to pair with resort shirts",
            ],
        },
        {
            "patterns": [r"\bgym shoes\b.*\brunning\b", r"\b(cross trainer|training shoe)\b.*\brunning\b", r"\bwhich shoes\b.*\bgym\b"],
            "title": "Running Shoes vs Gym Cross-Trainers",
            "answer": (
                "- **For Weightlifting / Squats / Deadlifts / HIIT:** Choose a **flat, firm cross-trainer** (like Reebok Nanoflex) so your heels don't wobble under heavy weights.\n"
                "- **For Treadmill / Road Running / Daily 10k Steps:** Choose **cushioned neutral runners or walking shoes** (like ASICS Gel-Nimbus or Nike Revolution) to absorb joint impact."
            ),
            "search_query": "gym shoes walking running",
            "follow_ups": [
                "I'm joining a gym next week, build my kit",
                "Best comfortable shoes for daily walking",
            ],
        },
        {
            "patterns": [r"\bcamera phone\b.*\b(good|best|choose|what makes|photography)\b", r"\bmegapixel\b"],
            "title": "What Actually Makes a Great Camera Phone?",
            "answer": (
                "Ignore megapixel hype alone — focus on these four specs:\n"
                "1. **Sensor Size & OIS (Optical Image Stabilization):** Larger sensors + OIS capture clean, blur-free night shots.\n"
                "2. **Dedicated Telephoto Lens (2x–5x):** Crucial for flattering natural portraits and zoom without digital grain.\n"
                "3. **Computational Processing:** Google Pixel and Apple lead in natural skin tones and HDR; Vivo (ZEISS) and Xiaomi (Leica) excel in portrait bokeh under ₹40,000.\n"
                "4. **Video Stabilization:** Look for 4K60 or 4K120 OIS+EIS if you shoot reels/vlogs."
            ),
            "search_query": "camera phone under 40000",
            "follow_ups": [
                "Recommend the best camera phone under ₹40,000",
                "Compare iPhone 16 Pro and Samsung S25 Ultra",
            ],
        },
    ]

    @classmethod
    def match_topic(cls, query: str) -> Optional[Dict[str, Any]]:
        q = query.lower()
        for topic in cls.TOPICS:
            for pat in topic["patterns"]:
                if re.search(pat, q):
                    return topic
        return None


class SalesAssociateEngine:
    """Hybrid general-purpose recommendation, comparison, Q&A, and memory engine."""

    def __init__(self, products_path: str, db: ChatbotDatabase) -> None:
        self.products_path = products_path
        self.db = db
        with open(products_path, "r", encoding="utf-8") as f:
            self.products: List[Dict[str, Any]] = json.load(f)
        self.product_map: Dict[str, Dict[str, Any]] = {p["id"]: p for p in self.products}
        self.brands: List[str] = sorted(
            {p["brand"].lower() for p in self.products}, key=len, reverse=True
        )
        self._build_search_index()

    def _build_search_index(self) -> None:
        """Build BM25-style inverted index across product fields."""
        self._doc_tokens: Dict[str, Counter] = {}
        self._doc_lengths: Dict[str, int] = {}
        self._df: Counter = Counter()

        for p in self.products:
            parts = [
                p["name"],
                p["name"],
                p["brand"],
                p["category"],
                p["subcategory"],
                p["subcategory"],
                " ".join(p.get("use_cases", [])),
                " ".join(p.get("use_cases", [])),
                " ".join(p.get("tags", [])),
                " ".join(p.get("tags", [])),
                " ".join(p.get("colors", [])),
                p.get("description", ""),
                " ".join(f"{k} {v}" for k, v in p.get("specs", {}).items()),
                " ".join(p.get("pros", [])),
            ]
            tokens = self._tokenize(" ".join(parts))
            counts = Counter(tokens)
            self._doc_tokens[p["id"]] = counts
            self._doc_lengths[p["id"]] = sum(counts.values())
            for t in counts.keys():
                self._df[t] += 1

        self._num_docs = len(self.products)
        self._avg_len = (
            sum(self._doc_lengths.values()) / self._num_docs if self._num_docs else 1.0
        )

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        raw = re.findall(r"[a-z0-9\+]+", text.lower())
        tokens: List[str] = []
        for tok in raw:
            if tok in STOPWORDS or len(tok) < 2:
                continue
            tokens.append(tok)
            if len(tok) > 4 and tok.endswith("s") and not tok.endswith("ss"):
                tokens.append(tok[:-1])
        return tokens

    # ------------------------------------------------------------------
    # Constraint & Memory Extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_number_token(num_str: str, suffix: str = "") -> int:
        clean = num_str.replace(",", "").strip()
        val = float(clean)
        s = suffix.lower().strip()
        if s == "k":
            val *= 1000
        elif s in ("l", "lac", "lakh", "lakhs"):
            val *= 100000
        return int(round(val))

    def extract_constraints(self, query: str) -> Dict[str, Any]:
        q = query.lower()
        constraints: Dict[str, Any] = {
            "budget_min": None,
            "budget_max": None,
            "budget_tier": None,
            "brands": [],
            "colors": [],
            "category": None,
            "subcategory": None,
            "cheaper_shift": False,
            "pricier_shift": False,
        }

        m_between = re.search(
            r"(?:between|from)\s*(?:₹|rs\.?|inr)?\s*(\d[\d,\.]*)\s*(k|lakh|lac|l)?\s*(?:to|and|-)\s*(?:₹|rs\.?|inr)?\s*(\d[\d,\.]*)\s*(k|lakh|lac|l)?",
            q,
        )
        if m_between:
            v1 = self._parse_number_token(m_between.group(1), m_between.group(2) or "")
            v2 = self._parse_number_token(m_between.group(3), m_between.group(4) or "")
            constraints["budget_min"] = min(v1, v2)
            constraints["budget_max"] = max(v1, v2)

        if constraints["budget_max"] is None:
            m_max = re.search(
                r"(?:under|below|less than|within|upto|up to|max|budget(?:\s+of|\s+is)?)\s*(?:₹|rs\.?|inr)?\s*(\d[\d,\.]*)\s*(k|lakh|lac|l)?\b",
                q,
            )
            if m_max:
                constraints["budget_max"] = self._parse_number_token(
                    m_max.group(1), m_max.group(2) or ""
                )

        if constraints["budget_max"] is None:
            m_around = re.search(
                r"(?:around|approx|near|about)\s*(?:₹|rs\.?|inr)?\s*(\d[\d,\.]*)\s*(k|lakh|lac|l)?\b",
                q,
            )
            if m_around:
                center = self._parse_number_token(
                    m_around.group(1), m_around.group(2) or ""
                )
                constraints["budget_min"] = int(center * 0.7)
                constraints["budget_max"] = int(center * 1.2)

        m_min = re.search(
            r"(?:above|over|more than|min(?:imum)?)\s*(?:₹|rs\.?|inr)?\s*(\d[\d,\.]*)\s*(k|lakh|lac|l)?\b",
            q,
        )
        if m_min:
            constraints["budget_min"] = self._parse_number_token(
                m_min.group(1), m_min.group(2) or ""
            )

        if constraints["budget_max"] is None and constraints["budget_min"] is None:
            m_bare = re.search(r"(?:₹|rs\.?)\s*(\d[\d,\.]*)\s*(k|lakh|lac|l)?", q)
            if m_bare:
                constraints["budget_max"] = self._parse_number_token(
                    m_bare.group(1), m_bare.group(2) or ""
                )

        if any(w in q for w in ("cheaper", "less expensive", "lower price", "more affordable", "budget version")):
            constraints["cheaper_shift"] = True
            constraints["budget_tier"] = "budget"
        elif any(w in q for w in ("more expensive", "higher end", "upgrade", "premium alternative", "flagship")):
            constraints["pricier_shift"] = True
            constraints["budget_tier"] = "premium"
        elif any(w in q for w in ("cheap", "budget", "affordable", "inexpensive", "value for money")):
            constraints["budget_tier"] = "budget"
        elif any(w in q for w in ("premium", "flagship", "high-end", "luxury")):
            constraints["budget_tier"] = "premium"

        for b in self.brands:
            if re.search(rf"\b{re.escape(b)}\b", q):
                constraints["brands"].append(b)
        if "pixel" in q and "google" not in constraints["brands"]:
            constraints["brands"].append("google")
        if "iphone" in q or "macbook" in q or "ipad" in q or "airpods" in q:
            if "apple" not in constraints["brands"]:
                constraints["brands"].append("apple")
        if "thinkpad" in q and "lenovo" not in constraints["brands"]:
            constraints["brands"].append("lenovo")

        for col in COLORS:
            if re.search(rf"\b{col}\b", q):
                constraints["colors"].append(col)

        for word, (cat, subcat) in CATEGORY_SYNONYMS.items():
            if re.search(rf"\b{re.escape(word)}\b", q):
                if cat and not constraints["category"]:
                    constraints["category"] = cat
                if subcat and not constraints["subcategory"]:
                    constraints["subcategory"] = subcat

        return constraints

    # ------------------------------------------------------------------
    # Product Name Matching
    # ------------------------------------------------------------------

    def find_mentioned_products(self, query: str, limit: int = 4) -> List[Dict[str, Any]]:
        q = query.lower()
        segments = re.split(r"\b(?:vs\.?|versus|and|or|with|against|,)\b", q)
        matched: List[Tuple[float, Dict[str, Any]]] = []
        seen_ids = set()

        for seg in segments:
            seg_clean = re.sub(
                r"\b(compare|comparison|difference|between|which|is|better|tell|me|more|about|the)\b",
                " ",
                seg,
            ).strip()
            if len(seg_clean) < 3:
                continue
            best_score = 0.0
            best_prod: Optional[Dict[str, Any]] = None
            seg_tokens = set(self._tokenize(seg_clean))

            for p in self.products:
                pname = p["name"].lower()
                if seg_clean in pname:
                    score = 1.0 + len(seg_clean) / max(len(pname), 1)
                else:
                    name_tokens = set(self._tokenize(pname))
                    overlap = len(seg_tokens & name_tokens)
                    if overlap == 0:
                        continue
                    ratio = SequenceMatcher(None, seg_clean, pname).ratio()
                    token_jaccard = overlap / max(len(seg_tokens | name_tokens), 1)
                    score = token_jaccard * 0.7 + ratio * 0.3
                    has_digit_match = bool(
                        re.findall(r"\d+", seg_clean)
                        and any(d in pname for d in re.findall(r"\d+", seg_clean))
                    )
                    if overlap == 1 and not has_digit_match and ratio < 0.45:
                        score *= 0.4
                if score > best_score:
                    best_score = score
                    best_prod = p

            if best_prod and best_score >= 0.38 and best_prod["id"] not in seen_ids:
                seen_ids.add(best_prod["id"])
                matched.append((best_score, best_prod))

        matched.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matched[:limit]]

    # ------------------------------------------------------------------
    # Search & Ranking Engine
    # ------------------------------------------------------------------

    def search_products(
        self,
        query: str,
        constraints: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[Tuple[Dict[str, Any], float, List[str]]]:
        """Return [(product, score, match_reasons)] ranked for query & constraints."""
        c = constraints or self.extract_constraints(query)
        q_tokens = self._tokenize(query)

        expanded_tokens: List[Tuple[str, float]] = [(t, 1.0) for t in q_tokens]
        seen_exp = set(q_tokens)
        for tok in q_tokens:
            for exp in CONCEPT_EXPANSIONS.get(tok, []):
                for et in self._tokenize(exp):
                    if et not in seen_exp:
                        seen_exp.add(et)
                        expanded_tokens.append((et, 0.55))

        results: List[Tuple[Dict[str, Any], float, List[str]]] = []
        b_min = c.get("budget_min")
        b_max = c.get("budget_max")
        target_cat = c.get("category")
        target_subcat = c.get("subcategory")
        target_brands = set(c.get("brands") or [])
        target_colors = set(c.get("colors") or [])

        for p in self.products:
            if b_max is not None and p["price"] > b_max:
                continue
            if b_min is not None and p["price"] < b_min:
                continue

            if target_subcat and p["subcategory"] != target_subcat:
                continue
            if not target_subcat and target_cat and p["category"] != target_cat:
                continue

            if target_brands and p["brand"].lower() not in target_brands:
                continue

            doc_counts = self._doc_tokens[p["id"]]
            doc_len = self._doc_lengths[p["id"]]
            k1 = 1.4
            b = 0.75
            bm25 = 0.0
            matched_terms: List[str] = []

            for tok, weight in expanded_tokens:
                tf = doc_counts.get(tok, 0)
                if tf == 0:
                    continue
                df = self._df.get(tok, 1)
                idf = math.log(1.0 + (self._num_docs - df + 0.5) / (df + 0.5))
                denom = tf + k1 * (1 - b + b * (doc_len / self._avg_len))
                bm25 += weight * idf * ((tf * (k1 + 1)) / denom)
                if weight >= 1.0 and tok not in matched_terms:
                    matched_terms.append(tok)

            if target_subcat and p["subcategory"] == target_subcat:
                bm25 += 3.5
            elif target_cat and p["category"] == target_cat:
                bm25 += 1.6

            if target_colors:
                prod_colors = " ".join(p.get("colors", [])).lower()
                if any(col in prod_colors for col in target_colors):
                    bm25 += 2.8
                    matched_terms.extend(list(target_colors))
                elif p.get("colors"):
                    bm25 -= 1.0

            tier = c.get("budget_tier")
            if tier == "budget":
                bm25 += max(0.0, 2.0 - (p["price"] / 50000.0))
            elif tier == "premium":
                bm25 += min(2.0, p["price"] / 50000.0)

            bm25 += (p.get("rating", 4.0) - 4.0) * 0.6

            if bm25 > 0.4:
                results.append((p, bm25, matched_terms))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Intent Detection
    # ------------------------------------------------------------------

    def detect_intent(
        self, query: str, ctx: Dict[str, Any], mentioned_products: List[Dict[str, Any]]
    ) -> str:
        q = query.lower().strip()

        if re.fullmatch(r"(hi|hello|hey|good\s*(morning|afternoon|evening)|namaste|yo|help|what can you do\??)", q):
            return "greeting"

        if any(
            phrase in q
            for phrase in (
                "what do you remember",
                "my preferences",
                "my memory",
                "previous data",
                "what did we discuss",
                "what did i ask",
                "saved items",
                "my wishlist",
                "my cart",
                "forget my preferences",
                "clear memory",
            )
        ):
            return "memory_recall"

        if re.match(r"^(remember|note that|save my|my budget is|i prefer|i have oily|i have sensitive)\b", q) and len(q.split()) <= 14:
            return "memory_store"

        if (
            any(w in q for w in ("compare", "comparison", " vs ", "versus", "difference between", "which is better"))
            or len(mentioned_products) >= 2
        ):
            return "compare"

        if re.search(r"\b(add|save|put)\b.*\b(cart|wishlist|bag)\b", q) and ctx.get("last_product_ids"):
            return "save_action"

        has_last = bool(ctx.get("last_product_ids"))
        follow_up_markers = (
            "cheaper", "more expensive", "higher budget", "lower budget",
            "alternatives", "other options", "show more", "another brand",
            "why did you", "tell me more", "explain the first", "first one",
            "second one", "third one", "instead", "what about in ", "in white",
            "in blue", "in black", "under ", "below ", "compare them", "compare top",
        )
        if has_last and (
            any(m in q for m in follow_up_markers)
            and len(q.split()) <= 10
        ):
            if "compare" in q:
                return "compare"
            return "follow_up"

        if TechKnowledgeBase.match_topic(q):
            return "tech_qa"

        bundle_patterns = [
            r"\bjoining\b.*\bgym\b", r"\bgym\b.*\bkit\b", r"\bgym\b.*\bwhat\b.*\bbuy\b",
            r"\bhome workout\b", r"\bsetup\b", r"\broutine\b", r"\bstarter kit\b",
            r"\bgoing (?:to|on)\b.*\b(trip|goa|manali|college|trek|trekking|vacation)\b",
            r"\b(manali|trekking|goa)\b.*\b(trip|packing|essentials|kit)\b",
            r"\bpacking\b.*\b(trip|goa|manali|vacation)\b",
            r"\bwork from home\b", r"\bwfh\b", r"\bstarting\b.*\b(youtube|vlog|podcast)\b",
        ]
        if any(re.search(pat, q) for pat in bundle_patterns):
            specific_single_item = any(
                re.search(rf"\b{w}\b", q)
                for w in ("shirt", "shirts", "sunscreen", "laptop", "phone", "shoes", "sandals", "headphones")
            )
            if not specific_single_item or any(w in q for w in ("kit", "setup", "routine", "and", "clothes", "everything", "what should i buy")):
                if any(w in q for w in ("gym", "setup", "routine", "kit", "packing", "clothes", "youtube", "podcast", "trek", "manali", "college", "wfh", "goa")):
                    return "bundle"

        return "recommend"

    # ------------------------------------------------------------------
    # Response Builders
    # ------------------------------------------------------------------

    @staticmethod
    def _format_price(price: int) -> str:
        return f"₹{price:,}"

    def _explain_recommendation(self, product: Dict[str, Any], query: str, constraints: Dict[str, Any]) -> str:
        q = query.lower()
        reasons: List[str] = []

        if constraints.get("budget_max") and product["price"] <= constraints["budget_max"]:
            reasons.append(f"Fits comfortably within your {self._format_price(constraints['budget_max'])} budget")

        matched_uc = [
            uc for uc in product.get("use_cases", [])
            if any(
                w in uc
                for tok in self._tokenize(q)
                for w in [tok] + CONCEPT_EXPANSIONS.get(tok, [])
            )
        ]
        if matched_uc:
            reasons.append(f"Built for {', '.join(matched_uc[:2])}")

        if product.get("pros"):
            reasons.append(product["pros"][0])

        if not reasons:
            reasons.append(product.get("description", "")[:110])
        return " • ".join(reasons[:3])

    def _build_comparison(
        self, products: List[Dict[str, Any]], query: str
    ) -> Dict[str, Any]:
        """Build a structured side-by-side comparison table across any 2-3 products."""
        all_spec_keys: List[str] = []
        for p in products:
            for k in p.get("specs", {}).keys():
                if k not in all_spec_keys:
                    all_spec_keys.append(k)

        rows: List[Dict[str, Any]] = [
            {
                "attribute": "Price",
                "values": [self._format_price(p["price"]) for p in products],
            },
            {
                "attribute": "Rating",
                "values": [f"★ {p['rating']} ({p['reviews_count']:,} reviews)" for p in products],
            },
        ]
        for key in all_spec_keys:
            rows.append(
                {
                    "attribute": key,
                    "values": [p.get("specs", {}).get(key, "—") for p in products],
                }
            )
        rows.append(
            {
                "attribute": "Pros",
                "values": ["; ".join(p.get("pros", [])[:2]) for p in products],
            }
        )
        rows.append(
            {
                "attribute": "Cons",
                "values": ["; ".join(p.get("cons", [])[:2]) for p in products],
            }
        )

        cheapest = min(products, key=lambda p: p["price"])
        highest_rated = max(products, key=lambda p: (p["rating"], p["reviews_count"]))
        verdict_parts = [
            f"**Best Value:** **{cheapest['name']}** ({self._format_price(cheapest['price'])}) saves you {self._format_price(max(p['price'] for p in products) - cheapest['price'])}."
            if len({p["price"] for p in products}) > 1
            else "",
            f"**Top Rated Overall:** **{highest_rated['name']}** (★ {highest_rated['rating']}).",
        ]
        if len(products) == 2:
            p1, p2 = products
            verdict_parts.append(
                f"Pick **{p1['name']}** if you prioritize *{p1['pros'][0].lower()}*, or **{p2['name']}** if you prefer *{p2['pros'][0].lower()}*."
            )

        return {
            "products": [
                {"id": p["id"], "name": p["name"], "brand": p["brand"], "price": p["price"]}
                for p in products
            ],
            "rows": rows,
            "verdict": " ".join(v for v in verdict_parts if v),
        }

    def _find_budget_alternatives(
        self, primary: Dict[str, Any], exclude_ids: set
    ) -> List[Dict[str, Any]]:
        same_sub = [
            p
            for p in self.products
            if p["id"] not in exclude_ids
            and p["subcategory"] == primary["subcategory"]
        ]
        if len(same_sub) < 2:
            same_sub = [
                p
                for p in self.products
                if p["id"] not in exclude_ids and p["category"] == primary["category"]
            ]

        cheaper = [p for p in same_sub if p["price"] < primary["price"]]
        pricier = [p for p in same_sub if p["price"] > primary["price"]]
        alts: List[Dict[str, Any]] = []
        if cheaper:
            pick = max(cheaper, key=lambda p: (p["rating"], p["price"]))
            alts.append({**pick, "tier_label": "Budget Alternative"})
        if pricier:
            pick = min(pricier, key=lambda p: p["price"])
            alts.append({**pick, "tier_label": "Upgrade Option"})
        return alts

    def _assemble_bundle(self, query: str, constraints: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], str]:
        q = query.lower()
        b_max = constraints.get("budget_max")

        if any(w in q for w in ("gym", "workout", "fitness")):
            title = "Complete Gym Starter Kit"
            slots = [
                ("Shoes", "shoes gym training running"),
                ("Workout T-Shirt", "gym tshirt dryfit"),
                ("Training Shorts", "gym shorts workout"),
                ("Water Bottle", "water bottle 1 liter gym"),
                ("Gym Bag", "gym bag duffel"),
                ("Anti-Blister Socks", "running gym socks"),
            ]
            intro = "Since you're starting the gym, here is a complete head-to-toe kit covering footwear, sweat-wicking apparel, hydration, and gear:"
        elif any(w in q for w in ("manali", "winter", "hill", "trek", "hiking")):
            title = "Mountain & Trekking Essentials Kit"
            slots = [
                ("Trekking Shoes", "waterproof mountain trekking shoes"),
                ("Warm Packable Jacket", "ultra light down winter jacket"),
                ("Rain Windcheater", "waterproof packable windcheater"),
                ("Travel Backpack", "travel laptop backpack"),
                ("Power Bank", "20000mah power bank"),
            ]
            intro = "For cold mountain weather and trails, you need layering, waterproof grip, and backup power. Here is a complete mountain kit:"
        elif any(w in q for w in ("goa", "beach", "vacation", "trip")):
            title = "Goa & Coastal Trip Packing Kit"
            slots = [
                ("Breathable Resort Shirt", "linen black resort shirt goa"),
                ("Quick-Dry Shorts", "dry stretch travel shorts"),
                ("Waterproof Sandals", "eva beach travel sandals"),
                ("Humid-Weather Sunscreen", "matte sunscreen spf 50 humid"),
                ("Polarized Sunglasses", "polarized uv400 sunglasses"),
                ("Beach Speaker", "waterproof bluetooth speaker"),
            ]
            intro = "For warm coastal weather like Goa, breathable fabrics, sweat-resistant sun protection, and waterproof footwear make all the difference:"
        elif any(w in q for w in ("wfh", "desk", "home office", "work from home")):
            title = "Ergonomic Work-From-Home Desk Setup"
            slots = [
                ("4K USB-C Monitor", "4k usb-c monitor"),
                ("Ergonomic Mesh Chair", "ergonomic mesh chair"),
                ("Wireless Mechanical Keyboard", "keychron mechanical keyboard"),
                ("Ergonomic Mouse", "logitech mx master mouse"),
                ("ANC Headphones for Calls", "sony anc headphones"),
            ]
            intro = "Here is a balanced WFH desk setup built for posture comfort, single-cable laptop docking, and quiet focus calls:"
        elif any(w in q for w in ("youtube", "vlog", "content", "creator", "podcast")):
            title = "Content Creator & Vlogging Kit"
            slots = [
                ("Stabilized Camera", "osmo pocket 3 creator camera"),
                ("Studio USB Microphone", "rode usb microphone"),
                ("Extendable Vlog Tripod", "ulanzi vlog tripod"),
                ("Creator Laptop", "vivobook pro oled rtx laptop"),
            ]
            intro = "To launch sharp, well-stabilized videos with crisp audio, here is an end-to-end creator kit:"
        elif any(w in q for w in ("skincare", "routine", "oily skin", "acne")):
            title = "Daily Dermatologist-Friendly Skincare Routine"
            slots = [
                ("Step 1: Gentle Cleanser", "oily skin cleanser cetaphil"),
                ("Step 2: Antioxidant Serum", "vitamin c serum"),
                ("Step 3: Oil-Free Moisturizer", "oil free gel moisturizer"),
                ("Step 4: Matte SPF 50 Sunscreen", "ultra matte sunscreen spf 50"),
            ]
            intro = "A simple 4-step AM/PM routine keeps oily or humid-climate skin balanced without clogging pores:"
        else:
            title = "College & Engineering Starter Bundle"
            slots = [
                ("Programming Laptop", "thinkpad e14 programming laptop"),
                ("Travel & Campus Backpack", "tomtoc laptop backpack"),
                ("Study ANC Headphones", "soundcore anc headphones"),
                ("Insulated Flask", "milton thermosteel flask"),
                ("Laptop Power Bank", "65w power bank"),
            ]
            intro = "Here is a practical campus bundle covering coding performance, daily carry, focus audio, and hydration:"

        bundle_items: List[Dict[str, Any]] = []
        used_ids = set()
        for slot_label, slot_query in slots:
            matches = self.search_products(slot_query, constraints={"budget_tier": constraints.get("budget_tier")}, top_k=3)
            for prod, _, _ in matches:
                if prod["id"] not in used_ids:
                    used_ids.add(prod["id"])
                    bundle_items.append({**prod, "slot_label": slot_label})
                    break

        if b_max and sum(i["price"] for i in bundle_items) > b_max:
            for idx, item in enumerate(bundle_items):
                if sum(i["price"] for i in bundle_items) <= b_max:
                    break
                alts = [
                    p for p in self.products
                    if p["subcategory"] == item["subcategory"] and p["price"] < item["price"] and p["id"] not in used_ids
                ]
                if alts:
                    cheaper = min(alts, key=lambda x: x["price"])
                    used_ids.add(cheaper["id"])
                    bundle_items[idx] = {**cheaper, "slot_label": item["slot_label"]}

        return title, bundle_items, intro

    def _generate_follow_up_questions(
        self,
        intent: str,
        constraints: Dict[str, Any],
        products: List[Dict[str, Any]],
        query: str,
    ) -> List[str]:
        q = query.lower()
        prompts: List[str] = []

        if len(products) >= 2 and intent != "compare":
            prompts.append(f"Compare {products[0]['name']} and {products[1]['name']}")

        if not constraints.get("budget_max") and products:
            mid_price = sorted(p["price"] for p in products)[len(products) // 2]
            rounded = max(500, round(mid_price * 0.85 / 500) * 500)
            prompts.append(f"Show cheaper alternatives under ₹{rounded:,}")

        if products:
            cat = products[0]["category"]
            sub = products[0]["subcategory"]
            if sub == "Laptops" and "gaming" not in q and "ml" not in q:
                prompts.append("Will I need a dedicated GPU for this?")
            elif sub == "Smartphones" and "battery" not in q:
                prompts.append("Which one has the best battery life?")
            elif sub == "Shirts":
                prompts.append("Suggest matching travel shorts and sandals")
            elif sub == "Sunscreen":
                prompts.append("Which one is best for oily skin?")
            elif cat == "Footwear":
                prompts.append("Compare cushioning and durability of the top 2")

        prompts.append("Save the top pick to my wishlist")
        return prompts[:4]

    # ------------------------------------------------------------------
    # Optional Gemini LLM RAG Polish
    # ------------------------------------------------------------------

    def _maybe_gemini_rag(
        self,
        query: str,
        history: List[Dict[str, Any]],
        products: List[Dict[str, Any]],
        prefs: Dict[str, Any],
        fallback_text: str,
    ) -> Tuple[str, str]:
        api_key = self.db.get_setting("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
        if not api_key or requests is None:
            return fallback_text, "local-hybrid"

        catalog_slice = [
            {
                "id": p["id"],
                "name": p["name"],
                "brand": p["brand"],
                "price_inr": p["price"],
                "rating": p["rating"],
                "specs": p.get("specs", {}),
                "pros": p.get("pros", []),
                "cons": p.get("cons", []),
            }
            for p in products[:6]
        ]
        recent_turns = [
            f"{m['role'].upper()}: {m['content'][:350]}"
            for m in history[-6:]
        ]
        system_prompt = (
            "You are a warm, expert AI Virtual Sales Associate for an e-commerce store. "
            "Answer the customer's question naturally and concisely using ONLY the grounded catalog products below "
            "for product names and ₹ prices. Explain WHY items fit the customer's intent, lifestyle, or budget, "
            "ask 1 short helpful follow-up question if preferences are unclear, and reference stored memory naturally when useful.\n\n"
            f"USER MEMORY: {json.dumps(prefs)}\n"
            "RECENT CONVERSATION:\n" + "\n".join(recent_turns) + "\n\n"
            f"RELEVANT CATALOG PRODUCTS:\n{json.dumps(catalog_slice, indent=2)}"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 550},
        }
        try:
            resp = requests.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
                )
                if text:
                    return text, "gemini-rag"
        except Exception:
            pass
        return fallback_text, "local-hybrid"

    # ------------------------------------------------------------------
    # Main Chat Entrypoint
    # ------------------------------------------------------------------

    def handle_message(self, session_id: str, user_message: str) -> Dict[str, Any]:
        session = self.db.get_session(session_id)
        if not session:
            raise ValueError(f"Unknown session: {session_id}")

        ctx: Dict[str, Any] = dict(session.get("context") or {})
        history = self.db.get_messages(session_id, limit=40)
        global_prefs = self.db.get_preferences()

        self.db.add_message(session_id, "user", user_message)

        if session.get("title") in ("New Shopping Chat", "Shopping Chat") and len(history) == 0:
            clean_title = re.sub(r"\s+", " ", user_message).strip()[:52]
            if len(user_message.strip()) > 52:
                clean_title += "..."
            self.db.update_session_title(session_id, clean_title or "Shopping Chat")

        constraints = self.extract_constraints(user_message)
        mentioned = self.find_mentioned_products(user_message)
        intent = self.detect_intent(user_message, ctx, mentioned)

        self._update_persistent_memory(user_message, constraints)

        reply_text = ""
        recommended_products: List[Dict[str, Any]] = []
        comparison_data: Optional[Dict[str, Any]] = None
        bundle_data: Optional[Dict[str, Any]] = None
        alternatives_data: List[Dict[str, Any]] = []
        follow_ups: List[str] = []
        clarifying_question: Optional[str] = None
        use_llm_polish = False

        if intent == "greeting":
            mem_summary = self._format_memory_summary(global_prefs)
            reply_text = (
                "Hi! I'm your **Virtual Sales Associate**. Ask me anything — from vague lifestyle goals "
                "(*\"I'm starting a WFH setup\"*, *\"skincare for oily skin\"*) to exact budget searches, "
                "side-by-side comparisons, or tech spec advice."
            )
            if mem_summary:
                reply_text += f"\n\nI also remember your saved preferences: {mem_summary}."
            follow_ups = [
                "Recommend the best camera phone under ₹40,000",
                "Compare iPhone 16 Pro and Samsung S25 Ultra",
                "Help me build a Work-From-Home desk setup",
                "I'm joining a gym next week. What should I buy?",
            ]

        elif intent == "memory_store":
            if "oily" in user_message.lower():
                self.db.set_preference("skin_type", "Oily / Acne-prone", source="user")
            if "sensitive" in user_message.lower():
                self.db.set_preference("skin_type", "Sensitive", source="user")
            if constraints.get("budget_max"):
                self.db.set_preference("preferred_budget_max", constraints["budget_max"], source="user")
            if constraints.get("brands"):
                self.db.set_preference("preferred_brands", constraints["brands"], source="user")
            updated_prefs = self.db.get_preferences()
            reply_text = (
                "Got it — I've saved that to your persistent shopping profile so I can tailor future recommendations across chats.\n\n"
                f"**Current Saved Memory:** {self._format_memory_summary(updated_prefs) or 'Preferences updated.'}"
            )
            follow_ups = ["Recommend products based on my preferences", "Show what you remember about me"]

        elif intent == "memory_recall":
            q = user_message.lower()
            if "forget" in q or "clear memory" in q:
                self.db.clear_preferences()
                reply_text = "I've cleared your stored cross-session shopping preferences. Your chat transcripts remain intact unless you delete a chat."
                follow_ups = ["Recommend a good all-rounder smartphone", "Help me choose a laptop"]
            else:
                saved_wishlist = self.db.list_saved_items("wishlist")
                saved_cart = self.db.list_saved_items("cart")
                recent_q = self.db.get_recent_queries(limit=6)
                mem_str = self._format_memory_summary(global_prefs)
                parts = ["Here is what I currently store from your previous interactions:"]
                parts.append(f"- **Shopping Preferences:** {mem_str if mem_str else 'None learned yet — tell me your budget, skin type, or favorite brands!'}")
                parts.append(f"- **Wishlist:** {len(saved_wishlist)} item(s) | **Cart:** {sum(i['quantity'] for i in saved_cart)} item(s)")
                if recent_q:
                    hist_lines = [f"\"{r['query']}\"" for r in recent_q[:4]]
                    parts.append(f"- **Recent Queries:** {', '.join(hist_lines)}")
                reply_text = "\n".join(parts)
                recommended_products = [
                    self.product_map[i["product_id"]]
                    for i in (saved_cart + saved_wishlist)
                    if i["product_id"] in self.product_map
                ][:4]
                follow_ups = ["Clear my shopping memory", "Compare my saved items"]

        elif intent == "save_action":
            last_ids = ctx.get("last_product_ids", [])
            target_id = last_ids[0] if last_ids else None
            if "second" in user_message.lower() and len(last_ids) >= 2:
                target_id = last_ids[1]
            elif "third" in user_message.lower() and len(last_ids) >= 3:
                target_id = last_ids[2]
            list_type = "cart" if "cart" in user_message.lower() or "bag" in user_message.lower() else "wishlist"
            if target_id and target_id in self.product_map:
                prod = self.product_map[target_id]
                self.db.save_item(target_id, list_type=list_type, quantity=1)
                reply_text = f"Added **{prod['name']}** ({self._format_price(prod['price'])}) to your **{list_type}**. It's saved permanently in the database so you won't lose it on reload."
                recommended_products = [prod]
                follow_ups = ["Show my saved items", "Show cheaper alternatives"]
            else:
                reply_text = "Tell me which product you'd like to save, or click **Save** / **Add to Cart** on any product card!"

        elif intent == "compare":
            comp_products = list(mentioned)
            want_two = any(w in user_message.lower() for w in ("first two", "top two", "top 2", "first 2", "both"))
            max_comp = 2 if want_two else 3
            if len(comp_products) < 2 and ctx.get("last_product_ids"):
                for pid in ctx["last_product_ids"]:
                    if pid in self.product_map and self.product_map[pid] not in comp_products:
                        comp_products.append(self.product_map[pid])
                    if len(comp_products) >= max_comp:
                        break
            if len(comp_products) == 1:
                base = comp_products[0]
                rivals = [
                    p for p in self.products
                    if p["id"] != base["id"] and p["subcategory"] == base["subcategory"]
                ]
                rivals.sort(key=lambda p: abs(p["price"] - base["price"]))
                if rivals:
                    comp_products.append(rivals[0])

            unlisted_note = ""
            if len(comp_products) < 2:
                fallback_matches = self.search_products(user_message, constraints=constraints, top_k=2)
                if len(fallback_matches) >= 2:
                    comp_products = [m[0] for m in fallback_matches]
                    unlisted_note = (
                        "Those exact models aren't in our store inventory, so here is a comparison of the closest comparable options we carry:\n\n"
                    )

            if len(comp_products) >= 2:
                comp_products = comp_products[:max_comp]
                comparison_data = self._build_comparison(comp_products, user_message)
                recommended_products = comp_products
                names = " vs ".join(f"**{p['name']}**" for p in comp_products)
                reply_text = (
                    unlisted_note
                    + f"Here is a structured side-by-side comparison of {names}:\n\n"
                    + f"{comparison_data['verdict']}"
                )
                ctx["last_compared_ids"] = [p["id"] for p in comp_products]
                ctx["last_product_ids"] = [p["id"] for p in comp_products]
                follow_ups = [
                    "Which is better for long-term value?",
                    f"Show budget alternatives to {comp_products[0]['name']}",
                    f"Add {comp_products[0]['name']} to cart",
                ]
                use_llm_polish = True
            else:
                reply_text = (
                    "I'd love to compare products side-by-side! Which two products would you like me to compare? "
                    "For example, you can ask *\"Compare iPhone 16 Pro and Samsung S25 Ultra\"* or *\"Compare ThinkPad E14 and MacBook Air M3\"*."
                )
                follow_ups = [
                    "Compare iPhone 16 Pro and Samsung S25 Ultra",
                    "Compare Google Pixel 8a and Vivo V40 Pro",
                    "Compare ThinkPad E14 and MacBook Air M3",
                ]

        elif intent == "tech_qa":
            topic = TechKnowledgeBase.match_topic(user_message)
            assert topic is not None
            matches = self.search_products(topic["search_query"], constraints=constraints, top_k=3)
            recommended_products = [m[0] for m in matches]
            reply_text = f"### {topic['title']}\n\n{topic['answer']}"
            if recommended_products:
                reply_text += "\n\nHere are the top matching options from our catalog:"
                ctx["last_product_ids"] = [p["id"] for p in recommended_products]
            follow_ups = topic.get("follow_ups", [])
            use_llm_polish = True

        elif intent == "bundle":
            title, bundle_items, intro = self._assemble_bundle(user_message, constraints)
            total_price = sum(i["price"] for i in bundle_items)
            bundle_data = {
                "title": title,
                "items": bundle_items,
                "total_price": total_price,
            }
            recommended_products = bundle_items
            reply_text = (
                f"{intro}\n\n"
                f"**{title}** — {len(bundle_items)} curated essentials totaling **{self._format_price(total_price)}**."
            )
            ctx["last_product_ids"] = [p["id"] for p in bundle_items]
            follow_ups = [
                f"Make this bundle cheaper under ₹{max(2000, int(total_price * 0.7))}",
                "Add all bundle items to cart",
                "Swap any item for a higher-end upgrade",
            ]
            use_llm_polish = True

        elif intent == "follow_up":
            merged_c = self._merge_follow_up_constraints(user_message, constraints, ctx)
            q_lower = user_message.lower()

            if any(w in q_lower for w in ("why", "explain", "tell me more", "details", "first one", "second one")):
                idx = 1 if "second" in q_lower else (2 if "third" in q_lower else 0)
                last_ids = ctx.get("last_product_ids", [])
                if idx < len(last_ids) and last_ids[idx] in self.product_map:
                    p = self.product_map[last_ids[idx]]
                    recommended_products = [p]
                    specs_lines = "\n".join(f"- **{k}:** {v}" for k, v in p.get("specs", {}).items())
                    reply_text = (
                        f"Here is why **{p['name']}** ({self._format_price(p['price'])}) stands out:\n\n"
                        f"{p['description']}\n\n"
                        f"**Key Specs:**\n{specs_lines}\n\n"
                        f"**Pros:** {'; '.join(p.get('pros', []))}\n"
                        f"**Watch-outs:** {'; '.join(p.get('cons', []))}"
                    )
                    alternatives_data = self._find_budget_alternatives(p, {p["id"]})
                    follow_ups = [
                        f"Compare {p['name']} with a rival",
                        "Show cheaper alternatives",
                        "Add this to my cart",
                    ]
                else:
                    intent = "recommend"
            else:
                search_q = ctx.get("last_query") or user_message
                if merged_c.get("colors"):
                    search_q = f"{search_q} {' '.join(merged_c['colors'])}"
                if merged_c.get("brands"):
                    search_q = f"{search_q} {' '.join(merged_c['brands'])}"
                matches = self.search_products(search_q, constraints=merged_c, top_k=4)
                recommended_products = [m[0] for m in matches]
                if recommended_products:
                    reply_text = self._compose_recommendation_text(user_message, recommended_products, merged_c, matches)
                    alternatives_data = self._find_budget_alternatives(
                        recommended_products[0], {p["id"] for p in recommended_products}
                    )
                    ctx["last_product_ids"] = [p["id"] for p in recommended_products]
                    follow_ups = self._generate_follow_up_questions("recommend", merged_c, recommended_products, search_q)
                else:
                    reply_text = (
                        "I couldn't find an exact match with that stricter filter. "
                        "Try relaxing the budget or brand filter, or ask me to compare options from a broader price range!"
                    )
                    follow_ups = ["Show options regardless of budget", "Reset filters and recommend bestsellers"]
                ctx.update(
                    {
                        "budget_max": merged_c.get("budget_max"),
                        "budget_min": merged_c.get("budget_min"),
                        "active_category": merged_c.get("category"),
                        "active_subcategory": merged_c.get("subcategory"),
                    }
                )

        if intent == "recommend":
            eff_constraints = dict(constraints)
            matches = self.search_products(user_message, constraints=eff_constraints, top_k=4)
            relaxed_note = ""
            if not matches and eff_constraints.get("budget_max"):
                relaxed_c = dict(eff_constraints)
                relaxed_c["budget_max"] = int(eff_constraints["budget_max"] * 1.25)
                matches = self.search_products(user_message, constraints=relaxed_c, top_k=4)
                if matches:
                    relaxed_note = f"*(No exact matches strictly under {self._format_price(eff_constraints['budget_max'])}, so here are the closest options within 25% of your budget:)*\n\n"

            if not matches:
                matches = self.search_products(user_message, constraints={}, top_k=4)

            recommended_products = [m[0] for m in matches]
            if recommended_products:
                reply_text = relaxed_note + self._compose_recommendation_text(
                    user_message, recommended_products, eff_constraints, matches
                )
                clarifying_question = self._maybe_clarifying_question(user_message, eff_constraints, recommended_products)
                if clarifying_question:
                    reply_text += f"\n\n**Quick question to narrow this down:** {clarifying_question}"
                alternatives_data = self._find_budget_alternatives(
                    recommended_products[0], {p["id"] for p in recommended_products}
                )
                follow_ups = self._generate_follow_up_questions(
                    "recommend", eff_constraints, recommended_products, user_message
                )
                ctx.update(
                    {
                        "budget_max": eff_constraints.get("budget_max"),
                        "budget_min": eff_constraints.get("budget_min"),
                        "active_category": recommended_products[0]["category"],
                        "active_subcategory": recommended_products[0]["subcategory"],
                        "last_product_ids": [p["id"] for p in recommended_products],
                        "last_query": user_message,
                    }
                )
                use_llm_polish = True
            else:
                reply_text = (
                    "I don't have an exact product match for that specific query in the current catalog yet, "
                    "but I can help across **Smartphones, Laptops, Tablets, Fashion & Footwear, Fitness Gear, Travel Essentials, Skincare, Audio, and WFH Peripherals**.\n\n"
                    "Could you tell me a bit more about what you're shopping for and your target budget?"
                )
                follow_ups = [
                    "Show me laptops for coding",
                    "Suggest a skincare routine for humid weather",
                    "Recommend noise-cancelling headphones",
                ]

        ai_mode = "local-hybrid"
        if use_llm_polish:
            reply_text, ai_mode = self._maybe_gemini_rag(
                user_message, history, recommended_products, global_prefs, reply_text
            )

        ctx["last_intent"] = intent
        self.db.update_session_context(session_id, ctx)
        self.db.log_query(
            session_id, user_message, intent, [p["id"] for p in recommended_products]
        )

        enriched_products: List[Dict[str, Any]] = []
        for p in recommended_products:
            p_copy = dict(p)
            p_copy["why_recommended"] = self._explain_recommendation(p, user_message, constraints)
            enriched_products.append(p_copy)

        metadata = {
            "intent": intent,
            "ai_mode": ai_mode,
            "products": enriched_products,
            "comparison": comparison_data,
            "bundle": bundle_data,
            "alternatives": alternatives_data,
            "follow_ups": follow_ups,
            "memory_snapshot": self._format_memory_summary(self.db.get_preferences()),
        }
        assistant_msg = self.db.add_message(session_id, "assistant", reply_text, metadata=metadata)
        return {
            "session": self.db.get_session(session_id),
            "message": assistant_msg,
        }

    def _compose_recommendation_text(
        self,
        query: str,
        products: List[Dict[str, Any]],
        constraints: Dict[str, Any],
        matches: List[Tuple[Dict[str, Any], float, List[str]]],
    ) -> str:
        q = query.lower()
        if "goa" in q or "humid" in q or "summer" in q:
            intro = "For hot, humid weather, breathable lightweight fabrics and sweat-resistant essentials are key."
        elif "computer engineering" in q or "programming" in q or "coding" in q:
            intro = "For Computer Engineering, prioritize at least **16GB RAM**, a strong multi-core CPU (for compiling, VMs, and Docker), and comfortable portability for campus."
        elif "india" in q and "sunscreen" in q:
            intro = "Indian sun & humidity call for **SPF 50 PA+++/++++** broad-spectrum protection with zero white cast and sweat resistance."
        elif "content creation" in q:
            intro = "For content creation, look for strong stabilization, sharp front/main sensors, and reliable color accuracy."
        elif "daily walking" in q:
            intro = "For daily walking, prioritize responsive midsole cushioning, arch support, and breathable uppers to prevent foot fatigue."
        else:
            budget_phrase = (
                f" under **{self._format_price(constraints['budget_max'])}**"
                if constraints.get("budget_max")
                else ""
            )
            intro = f"Here are the best matches{budget_phrase} tailored to your request:"

        lines = [intro, ""]
        for i, p in enumerate(products, start=1):
            reason = self._explain_recommendation(p, query, constraints)
            lines.append(
                f"**{i}. {p['name']}** — **{self._format_price(p['price'])}** (★ {p['rating']})\n"
                f"   *{reason}*"
            )
        return "\n".join(lines)

    @staticmethod
    def _maybe_clarifying_question(
        query: str, constraints: Dict[str, Any], products: List[Dict[str, Any]]
    ) -> Optional[str]:
        if constraints.get("budget_max") or constraints.get("budget_min"):
            return None
        if len(query.split()) >= 9:
            return None
        if not products:
            return None
        sub = products[0]["subcategory"]
        if sub == "Laptops":
            return "What is your budget range, and will you run heavy ML/CAD/gaming or mainly coding and web apps?"
        if sub == "Smartphones":
            return "Do you have a target budget, and do you care most about camera quality, gaming speed, or battery life?"
        if sub in ("Shirts", "Activewear", "Bottoms"):
            return "What's your preferred budget per piece, and do you prefer a relaxed or slim fit?"
        if sub == "Sunscreen":
            return "Is your skin oily/acne-prone, dry, or sensitive? That helps pick between matte gel vs lightweight cream."
        return "Would you like to filter by a specific budget or compare the top two options side-by-side?"

    def _merge_follow_up_constraints(
        self, query: str, new_c: Dict[str, Any], ctx: Dict[str, Any]
    ) -> Dict[str, Any]:
        merged = dict(new_c)
        if not merged.get("category") and ctx.get("active_category"):
            merged["category"] = ctx["active_category"]
        if not merged.get("subcategory") and ctx.get("active_subcategory"):
            merged["subcategory"] = ctx["active_subcategory"]

        last_prices = [
            self.product_map[pid]["price"]
            for pid in ctx.get("last_product_ids", [])
            if pid in self.product_map
        ]
        if merged.get("cheaper_shift") and not merged.get("budget_max") and last_prices:
            merged["budget_max"] = max(500, int(min(last_prices) * 0.95))
        elif merged.get("pricier_shift") and not merged.get("budget_min") and last_prices:
            merged["budget_min"] = int(max(last_prices) * 0.95)
        elif not merged.get("budget_max") and ctx.get("budget_max"):
            merged["budget_max"] = ctx["budget_max"]
        return merged

    def _update_persistent_memory(self, query: str, constraints: Dict[str, Any]) -> None:
        q = query.lower()
        if constraints.get("budget_max"):
            self.db.set_preference("last_budget_max", constraints["budget_max"], source="inferred")
        if constraints.get("brands"):
            existing = self.db.get_preferences().get("preferred_brands", {}).get("value", [])
            if not isinstance(existing, list):
                existing = []
            merged = list(dict.fromkeys(existing + constraints["brands"]))[-5:]
            self.db.set_preference("preferred_brands", merged, source="inferred")

        context_tags: List[str] = []
        tag_rules = [
            ("oily skin", "Skin type: Oily"),
            ("sensitive skin", "Skin type: Sensitive"),
            ("computer engineering", "Field: Computer Engineering"),
            ("gym", "Lifestyle: Gym / Fitness"),
            ("goa", "Trip: Goa / Coastal"),
            ("manali", "Trip: Mountains / Winter"),
            ("work from home", "Setup: Work From Home"),
            ("wfh", "Setup: Work From Home"),
            ("content creation", "Goal: Content Creation"),
        ]
        for needle, label in tag_rules:
            if needle in q:
                context_tags.append(label)
        if context_tags:
            existing_tags = self.db.get_preferences().get("shopping_interests", {}).get("value", [])
            if not isinstance(existing_tags, list):
                existing_tags = []
            merged_tags = list(dict.fromkeys(existing_tags + context_tags))[-8:]
            self.db.set_preference("shopping_interests", merged_tags, source="inferred")

    def _format_memory_summary(self, prefs: Dict[str, Dict[str, Any]]) -> str:
        if not prefs:
            return ""
        chunks: List[str] = []
        if "skin_type" in prefs:
            chunks.append(f"Skin: {prefs['skin_type']['value']}")
        if "preferred_budget_max" in prefs:
            chunks.append(f"Preferred Max Budget: ₹{int(prefs['preferred_budget_max']['value']):,}")
        elif "last_budget_max" in prefs:
            chunks.append(f"Recent Budget: ₹{int(prefs['last_budget_max']['value']):,}")
        if "preferred_brands" in prefs and prefs["preferred_brands"]["value"]:
            brands = [str(b).title() for b in prefs["preferred_brands"]["value"]]
            chunks.append(f"Brands: {', '.join(brands)}")
        if "shopping_interests" in prefs and prefs["shopping_interests"]["value"]:
            chunks.append("; ".join(prefs["shopping_interests"]["value"]))
        return " | ".join(chunks)

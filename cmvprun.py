import os
import logging
from datetime import datetime, timedelta

import pytz
from flask import Flask, request, jsonify, Response
from flask_caching import Cache
from dotenv import load_dotenv
from openai import OpenAI
from rapidfuzz import process
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

# Load environment variables
load_dotenv()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

# Initialize Flask and cache
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache"})

# Initialize logger and OpenAI client
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TariqBot")
client = OpenAI(api_key=OPENAI_API_KEY)

# Constants
GOODBYE_KEYWORDS = {"bye", "goodbye", "thanks", "thank you", "ta"}
FEEDBACK_PROMPT = "Was this response helpful? Reply YES or NO."
SESSION_TTL = 7 * 24 * 3600  # 7 days
STALE_DURATION = timedelta(days=1)

# ========== Data Preparation ==========

def normalize_catalog():
    """
    Convert PRODUCT_CATALOG values from dicts to lists of name/price dicts.
    """
    for category, items in list(PRODUCT_CATALOG.items()):
        if isinstance(items, dict):
            PRODUCT_CATALOG[category] = [
                {"name": name, "price": price}
                for name, price in items.items()
            ]

normalize_catalog()

store_locations = {}
for branch, details in STORE_INFO.get("branches", {}).items():
    address = details.split("|")[0].strip()
    postcode = details.split(",")[-1].strip().split()[0]
    hours = STORE_INFO.get("store_hours", "9AM to 9PM")
    store_locations[branch] = {
        "address": address,
        "postcode": postcode,
        "hours": hours,
    }

# ========== Utility Functions ==========

def get_uk_time() -> str:
    """
    Return current UK time as formatted string.
    """
    tz = pytz.timezone("Europe/London")
    now = datetime.now(tz)
    return now.strftime("%A, %d %B %Y, %I:%M %p")


def format_store_info(info: dict) -> str:
    """
    Format store info dictionary into readable text.
    """
    return "\n".join(
        f"{key.replace('_', ' ').title()}: {value}"
        for key, value in info.items()
    )


def format_product_catalog(catalog: dict) -> str:
    """
    Format the entire product catalog into readable text.
    """
    lines = []
    for category, products in catalog.items():
        lines.append(f"🛒 {category.title()}:")
        for product in products:
            lines.append(f"• {product['name']}: {product['price']}")
    return "\n".join(lines)


def format_category_products(category: str, products: list) -> str:
    """
    Format products for a single category.
    """
    lines = [f"🛒 Products in {category.title()}:"]
    for p in products:
        lines.append(f"- {p['name']}: {p['price']}")
    return "\n".join(lines)


def locate_store_by_postcode(message: str) -> str | None:
    """
    Find closest store based on postcode or branch name.
    """
    low = message.lower()
    for area, data in store_locations.items():
        if area.lower() in low or data["postcode"].lower() in low:
            return (
                f"Closest store: {area}\n"
                f"Address: {data['address']}\n"
                f"Hours: {data['hours']}"
            )
    return None


def answer_faqs(message: str) -> tuple[str, bool] | tuple[None, bool]:
    """
    Handle FAQ-like queries (time, hours, delivery, etc.).
    """
    low = message.lower()
    if "time" in low or "clock" in low:
        return f"Current UK time: {get_uk_time()}", True
    if any(k in low for k in ("hours", "opening", "closing")):
        hours = STORE_INFO.get("store_hours", "9AM to 9PM")
        return f"Store hours: {hours}", True
    if "delivery" in low:
        policy = STORE_INFO.get("delivery_policy", "We offer fast delivery.")
        return policy, True
    if "location" in low or "address" in low:
        reply = locate_store_by_postcode(low)
        default = STORE_INFO.get("store_location", "Unavailable")
        return (reply or f"Main store is at {default}"), True
    if "contact" in low:
        contact = STORE_INFO.get("contact", "Unavailable")
        return f"Contact us at {contact}", True
    if "history" in low or "about" in low:
        history = STORE_INFO.get("store_history", "We are proud to serve the community.")
        return history, True
    return None, False


def search_by_category(message: str) -> str | None:
    """
    Perform fuzzy match on category names.
    """
    match = process.extractOne(message.lower(), PRODUCT_CATALOG.keys(), score_cutoff=60)
    if not match:
        return None
    category = match[0]
    return format_category_products(category, PRODUCT_CATALOG[category])


def fuzzy_product_search(query: str) -> list[tuple[str, str, str]] | None:
    """
    Fuzzy search across all products in catalog.
    Returns list of (name, price, category).
    """
    results = []
    for category, products in PRODUCT_CATALOG.items():
        names = [p['name'].lower() for p in products]
        match = process.extractOne(query, names, score_cutoff=75)
        if match:
            prod = next(p for p in products if p['name'].lower() == match[0])
            results.append((prod['name'], prod['price'], category.title()))
    return results or None


def find_products(message: str) -> str | None:
    """
    Determine if a message matches a product, category, FAQ, or fuzzy search.
    """
    text = message.strip().lower()

    # Exact product match
    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            if product['name'].lower() == text:
                return f"🛒 {product['name']}: {product['price']}"

    # Exact category match
    if text in PRODUCT_CATALOG:
        return format_category_products(text, PRODUCT_CATALOG[text])

    # FAQs
    faq, is_faq = answer_faqs(message)
    if is_faq:
        return faq

    # Category fuzzy search
    category_result = search_by_category(message)
    if category_result:
        return category_result

    # Fuzzy product search with nested category support
    matches = []
    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            if text in product['name'].lower():
                matches.append((product['name'], product['price'], category.title()))

    if matches:
        lines = ["🛒 Products matching your query:"]
        for name, price, cat in matches:
            lines.append(f"- {name} ({cat}): {price}")
        return '
'.join(lines)

    return None


def generate_ai_response(message: str, memory: list[dict], model: str = 'gpt-4') -> str:
    """
    Call OpenAI chat completion with system context and conversation memory.
    """
    system_prompt = (
        "You are the helpful WhatsApp assistant for Tariq Halal Meat Shop UK."
        "\nAnswer using store info and product catalog."
    )
    system_prompt += f"\n\nSTORE INFO:\n{format_store_info(STORE_INFO)}"
    system_prompt += f"\n\nPRODUCT CATALOG:\n{format_product_catalog(PRODUCT_CATALOG)}"

    messages = [{"role": "system", "content": system_prompt}]
    for entry in memory[-5:]:
        messages.append({"role": "user", "content": entry['user']})
        messages.append({"role": "assistant", "content": entry['bot']})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
        max_tokens=500
    )
    return response.choices[0].message.content.strip()

# ========== Webhook Handler ==========
@app.route("/whatsapp", methods=["POST"])
def whatsapp_handler():
    try:
        # Validate Twilio request
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        if not validator.validate(
            request.url,
            request.form,
            request.headers.get("X-Twilio-Signature", "")
        ):
            return "Unauthorized", 403

        body = request.values.get("Body", "").strip()
        sender = request.values.get("From", "")
        if not body:
            return "Empty message", 400

        logger.info(f"Received from {sender}: {body}")

        # Retrieve session or initialize
        session_key = f"session_{sender}"
        session = cache.get(session_key) or {"history": [], "last": datetime.utcnow()}
        history = session['history']
        last_time = session['last']
        now = datetime.utcnow()

        # Determine model based on inactivity
        inactive = (now - last_time) > STALE_DURATION
        model_name = 'gpt-3.5-turbo' if inactive else 'gpt-4'

        # Handle feedback
        low = body.lower()
        if low in ["yes", "no"]:
            twiml = MessagingResponse()
            twiml.message("Thanks for your feedback!")
            return Response(str(twiml), mimetype="application/xml")

        # Handle goodbye
        if low in GOODBYE_KEYWORDS:
            twiml = MessagingResponse()
            twiml.message("Goodbye! Have a great day.")
            twiml.message(FEEDBACK_PROMPT)
            return Response(str(twiml), mimetype="application/xml")

        # Generate reply
        reply = find_products(body)
        if not reply:
            reply = generate_ai_response(body, history, model=model_name)

        # Update session
        history.append({"user": body, "bot": reply})
        session['last'] = now
        cache.set(session_key, session, timeout=SESSION_TTL)

        # Send response, splitting lines for readability
        twiml = MessagingResponse()
        for line in reply.split("\n"):
            twiml.message(line)

        return Response(str(twiml), mimetype="application/xml")

    except Exception:
        logger.exception("Error in whatsapp_handler")
        return "Server Error", 500

@app.route("/")
def home():
    return "🟢 Tariq Halal Meat Shop Chatbot is live."

@app.route("/health")
def health():
    return jsonify({"status": "online"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=False)

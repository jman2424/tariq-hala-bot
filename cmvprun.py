import os
import logging
from flask import Flask, request, jsonify, Response
from flask_caching import Cache
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
from rapidfuzz import process
from datetime import datetime
import pytz
from openai import OpenAI

# Load environment variables
load_dotenv()
from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

# Normalize store locations
store_locations = {
    branch: {
        "address": details.split("|")[0].strip(),
        "postcode": details.split(",")[-1].strip().split()[0],
        "hours": STORE_INFO.get("store_hours", "9AM to 9PM")
    }
    for branch, details in STORE_INFO.get("branches", {}).items()
}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TariqBot")

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Prepare product catalog for fuzzy search
for category, products in PRODUCT_CATALOG.items():
    if isinstance(products, dict):
        PRODUCT_CATALOG[category] = [
            {"name": name, "price": price}
            for name, price in products.items()
        ]

# Keywords
GOODBYE_KEYWORDS = {"bye", "goodbye", "thanks", "thank you", "ta"}
FEEDBACK_PROMPT = "Was this response helpful? Reply YES or NO."

# ========== UTILITIES ==========

def get_uk_time():
    uk_time = datetime.now(pytz.timezone("Europe/London"))
    return uk_time.strftime("%A, %d %B %Y, %I:%M %p")


def locate_store_by_postcode(message):
    for area, data in store_locations.items():
        if area.lower() in message.lower() or data.get("postcode", "").lower() in message.lower():
            return f"Closest store: {area}\nAddress: {data['address']}\nHours: {data['hours']}"
    return None


def format_product_catalog(catalog):
    lines = []
    for category, products in catalog.items():
        lines.append(f"\n🛒 {category.upper()}:")
        for product in products:
            lines.append(f"• {product['name']}: {product['price']}")
    return "\n".join(lines)


def format_category_products(category, products):
    lines = [f"🛒 Products in {category.title()}:]"]
    for p in products:
        lines.append(f"- {p['name']}: {p['price']}")
    return "\n".join(lines)


def answer_faqs(message):
    msg = message.lower()
    if any(word in msg for word in ["time", "clock"]):
        return f"Current UK time: {get_uk_time()}", True
    if any(word in msg for word in ["hours", "opening", "closing"]):
        return f"Store hours: {STORE_INFO.get('store_hours', '9AM to 9PM')}", True
    if "delivery" in msg:
        return STORE_INFO.get("delivery_policy", "We offer fast delivery."), True
    if any(word in msg for word in ["location", "address"]):
        store_reply = locate_store_by_postcode(msg)
        return (store_reply or f"Main store is at {STORE_INFO.get('store_location', 'Address not available.')}", True)
    if "contact" in msg:
        return f"Contact us at {STORE_INFO.get('contact', 'Unavailable')}", True
    if any(word in msg for word in ["history", "about"]):
        return STORE_INFO.get("store_history", "We are proud to serve the community."), True
    return None, False


def search_by_category(message):
    match = process.extractOne(message.lower(), PRODUCT_CATALOG.keys(), score_cutoff=60)
    if match:
        return format_category_products(match[0], PRODUCT_CATALOG[match[0]])
    return None


def fuzzy_product_search(query):
    results = []
    for category, products in PRODUCT_CATALOG.items():
        names = [p['name'].lower() for p in products]
        match = process.extractOne(query, names, score_cutoff=75)
        if match:
            prod = next(p for p in products if p['name'].lower() == match[0])
            results.append((prod['name'], prod['price'], category.title()))
    return results or None


def find_products(message):
    text = message.strip().lower()

    # 1) All marinated products
    if text == "marinated":
        marinated = []
        for cat, products in PRODUCT_CATALOG.items():
            for p in products:
                if "marinated" in p['name'].lower():
                    marinated.append((cat, p))
        if marinated:
            lines = ["🛒 All marinated products:"]
            for cat, p in marinated:
                lines.append(f"- {p['name']} ({cat.title()}): {p['price']}")
            return "\n".join(lines)

    # 2) Scoped marinated: "marinated chicken"
    if text.startswith("marinated "):
        _, scope = text.split(" ", 1)
        for cat, products in PRODUCT_CATALOG.items():
            if cat.lower() == scope:
                filtered = [p for p in products if "marinated" in p['name'].lower()]
                if filtered:
                    return format_category_products(cat, filtered)

    # 3) Exact product match
    for cat, products in PRODUCT_CATALOG.items():
        for p in products:
            if p['name'].lower() == text:
                return f"🛒 {p['name']}: {p['price']}"

    # 4) Exact category match
    for cat in PRODUCT_CATALOG:
        if text == cat.lower():
            return format_category_products(cat, PRODUCT_CATALOG[cat])

    # 5) FAQs
    faq, is_faq = answer_faqs(message)
    if is_faq:
        return faq

    # 6) Fuzzy category
    cat_results = search_by_category(message)
    if cat_results:
        return cat_results

    # 7) Fuzzy product search
    matches = fuzzy_product_search(text)
    if matches:
        lines = ["🛒 Products matching your query:"]
        for name, price, category in matches:
            lines.append(f"- {name} ({category}): {price}")
        return "\n".join(lines)

    return None


def generate_ai_response(message, memory=[]):
    try:
        context = (
            "You are the helpful WhatsApp assistant for Tariq Halal Meat Shop UK."
            "\nYou answer using the store info and product catalog."
            "\nIf you're unsure, politely ask them to call the shop."
            f"\n\nSTORE INFO:\n{format_store_info(STORE_INFO)}"
            f"\n\nPRODUCT CATALOG:\n{format_product_catalog(PRODUCT_CATALOG)}"
        )
        messages = [{"role": "system", "content": context}]
        for entry in memory[-5:]:
            messages.append({"role": "user", "content": entry["user"]})
           .messages.append({"role": "assistant", "content": entry["bot"]})
        messages.append({"role": "user", "content": message})
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.4,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("AI response failed")
        return "Sorry, I'm having trouble right now. Please try again later."


@app.route("/whatsapp", methods=["POST"])
def whatsapp_handler():
    try:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        if not validator.validate(
            request.url,
            request.form,
            request.headers.get("X-Twilio-Signature", "")
        ):
            return "Unauthorized", 403

        message = request.values.get("Body", "").strip()
        from_number = request.values.get("From", "")
        if not message:
            return "Empty message", 400

        logger.info(f"Message from {from_number}: {message}")
        key = f"session_{from_number}"
        history = cache.get(key) or []
        msg_lower = message.lower()

        # Handle feedback
        if msg_lower in ["yes", "no"]:
            logger.info(f"Feedback from {from_number}: {msg_lower.upper()}")
            twiml = MessagingResponse()
            twiml.message("Thanks for your feedback!")
            return Response(str(twiml), mimetype="application/xml")

        # Handle goodbye -> farewell + feedback
        if msg_lower in GOODBYE_KEYWORDS:
            twiml = MessagingResponse()
            twiml.message("Goodbye! Have a great day.")
            twiml.message(FEEDBACK_PROMPT)
            return Response(str(twiml), mimetype="application/xml")

        # Regular flow
        reply = find_products(message)
        if not reply:
            reply = generate_ai_response(message, memory=history)

        # Cache update
        history.append({"user": message, "bot": reply})
        cache.set(key, history[-10:], timeout=86400)

        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), mimetype="application/xml")
    except Exception:
        logger.exception("WhatsApp handler failed")
        return "Server Error", 500


@app.route("/")
def home():
    return "🟢 Tariq Halal Meat Shop Chatbot is live."


@app.route("/health")
def health():
    return jsonify({"status": "online"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=False)

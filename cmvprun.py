import os
import traceback
import logging
from flask import Flask, request, jsonify, Response
from flask_caching import Cache
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv
from difflib import get_close_matches
from datetime import datetime
import pytz
from openai import OpenAI

# Load environment variables
load_dotenv()

from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

# Add store_locations manually from branches in STORE_INFO
store_locations = {
    branch: {
        "address": details.split("|")[0].strip(),
        "postcode": details.split(",")[-1].strip().split(" ")[0],
        "hours": STORE_INFO.get("store_hours", "9AM to 9PM")
    }
    for branch, details in STORE_INFO.get("branches", {}).items()
}

# ========== APP CONFIG ==========
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TariqBot")

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# ========== NORMALIZE PRODUCT CATALOG ==========
for category, products in PRODUCT_CATALOG.items():
    new_products = []
    for item in products:
        if isinstance(item, dict):
            name = item.get("name", "Unnamed")
            price = item.get("price", "N/A")
            new_products.append({"name": name, "price": price})
        elif isinstance(item, str):
            new_products.append({"name": item, "price": "N/A"})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            new_products.append({"name": item[0], "price": item[1]})
        else:
            new_products.append({"name": str(item), "price": "N/A"})
    PRODUCT_CATALOG[category] = new_products

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
            name = product.get('name', 'Unnamed')
            price = product.get('price', 'N/A')
            lines.append(f"• {name}: {price}")
    return "\n".join(lines)

def format_store_info(info):
    return "\n".join([f"{k.replace('_',' ').title()}: {v}" for k, v in info.items()])

def answer_faqs(message):
    msg = message.lower()
    if any(word in msg for word in ["time", "clock", "what time is it"]):
        return f"Current UK time: {get_uk_time()}", True
    if "hours" in msg or "opening" in msg or "closing" in msg:
        return f"Store hours: {STORE_INFO.get('store_hours', '9AM to 9PM')}", True
    if "delivery" in msg:
        return STORE_INFO.get("delivery_policy", "We offer fast delivery."), True
    if "location" in msg or "address" in msg:
        store_reply = locate_store_by_postcode(msg)
        return (store_reply or f"Main store is at {STORE_INFO.get('store_location', 'Address not available.')}"), True
    if "contact" in msg:
        return f"Contact us at {STORE_INFO.get('contact', 'Unavailable')}", True
    if "history" in msg or "about" in msg:
        return STORE_INFO.get("store_history", "We are proud to serve the community."), True
    return None, False

def search_by_category(message):
    message = message.lower()
    for cat in PRODUCT_CATALOG.keys():
        if cat.lower() in message:
            return format_category_products(cat, PRODUCT_CATALOG[cat])
    match = get_close_matches(message, PRODUCT_CATALOG.keys(), n=1, cutoff=0.6)
    if match:
        return format_category_products(match[0], PRODUCT_CATALOG[match[0]])
    return None

def format_category_products(category, products):
    lines = [f"🛒 Products in {category.title()}:"]
    for product in products:
        name = product.get('name', 'Unnamed')
        price = product.get('price', 'N/A')
        lines.append(f"- {name}: {price}")
    return "\n".join(lines)

def fuzzy_product_search(query):
    results = []
    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            name = product.get('name', '').lower()
            if query in name or query in category.lower():
                results.append((product['name'], product['price'], category.title()))
            else:
                match = get_close_matches(query, [name], n=1, cutoff=0.65)
                if match:
                    results.append((product['name'], product['price'], category.title()))
    return results if results else None

def find_products(message):
    faq, is_faq = answer_faqs(message)
    if is_faq:
        return faq
    cat_results = search_by_category(message)
    if cat_results:
        return cat_results
    matches = fuzzy_product_search(message.lower())
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
            messages.append({"role": "assistant", "content": entry["bot"]})
        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.4,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"AI request failed on: {message}\nMemory: {memory}")
        logger.exception("AI response failed")
        return "Sorry, I'm having trouble right now. Please try again later."

# ========== ROUTES ==========

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
        session_key = f"session_{from_number}"
        history = cache.get(session_key) or []

        reply = find_products(message)
        if not reply:
            reply = generate_ai_response(message, memory=history)

        history.append({"user": message, "bot": reply})
        cache.set(session_key, history[-10:], timeout=3600)

        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), mimetype="application/xml")
    except Exception as e:
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


import os
import traceback
import logging
from flask import Flask, request, jsonify, Response
from flask_caching import Cache
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
import openai
from dotenv import load_dotenv
from difflib import get_close_matches

# Load environment variables
load_dotenv()

# Store data
from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

# ========== CONFIG ==========
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TariqBot")

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY  # ✅ PROPERLY SET FOR SDK V1+

# ========== UTILITIES ==========

def format_product_catalog(catalog):
    if not isinstance(catalog, dict):
        return "Product catalog unavailable."
    lines = []
    for category, products in catalog.items():
        lines.append(f"\n🛒 {category.upper()}:")
        for product in products:
            name = product.get('name', 'Unnamed')
            price = product.get('price', 'N/A')
            lines.append(f"• {name}: {price}")
    return "\n".join(lines)

def format_store_info(info):
    if not isinstance(info, dict):
        return str(info)
    return "\n".join([f"{key.replace('_', ' ').title()}: {value}" for key, value in info.items()])

def fuzzy_product_search(query):
    query = query.lower()
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

def answer_faqs(message):
    message = message.lower()
    if not isinstance(STORE_INFO, dict):
        return "Store information currently unavailable.", True
    if any(word in message for word in ["hours", "opening", "closing"]):
        return f"Our store is open from {STORE_INFO.get('store_hours', '9AM to 9PM')}.", True
    if "delivery" in message:
        return STORE_INFO.get("delivery_policy", "We offer fast delivery."), True
    if "location" in message or "address" in message:
        return f"We are located at {STORE_INFO.get('store_location', 'Address not available.')}", True
    if "contact" in message:
        return f"You can reach us at {STORE_INFO.get('phone_number', 'Unavailable')}", True
    if "history" in message or "about" in message:
        return STORE_INFO.get("store_history", "We are proud to serve our community with halal meats."), True
    return None, False

def find_products(message):
    faq, is_faq = answer_faqs(message)
    if is_faq:
        return faq

    matches = fuzzy_product_search(message)
    if matches:
        lines = ["🛒 Products matching your query:"]
        for name, price, category in matches:
            lines.append(f"- {name} ({category}): {price}")
        return "\n".join(lines)
    return None

def generate_ai_response(message, memory=[]):
    try:
        context = (
            "You are the helpful WhatsApp assistant for Tariq Halal Meat Shop UK.\n"
            f"\nSTORE INFO:\n{format_store_info(STORE_INFO)}"
            f"\n\nPRODUCT CATALOG:\n{format_product_catalog(PRODUCT_CATALOG)}"
            "\nAlways respond politely and clearly."
        )

        messages = [{"role": "system", "content": context}]
        for entry in memory[-5:]:
            messages.append({"role": "user", "content": entry["user"]})
            messages.append({"role": "assistant", "content": entry["bot"]})
        messages.append({"role": "user", "content": message})

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.4,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
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

# ========== MAIN ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=False)

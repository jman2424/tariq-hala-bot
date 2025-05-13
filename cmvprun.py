import os
import traceback
import logging
from functools import lru_cache
from flask import Flask, request, jsonify, Response
from flask_caching import Cache
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
import openai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ✅ Import store info and product catalog
from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

# ========== CONFIGURATION ==========

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== EXTERNAL KEYS ==========

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ========== HELPER: FORMAT PRODUCT CATALOG ==========

def format_product_catalog(catalog):
    lines = []
    for category, products in catalog.items():
        lines.append(f"\n🛒 {category.upper()}")
        for product in products:
            name = product.get("name", "Unnamed Product")
            price = product.get("price", "Price Not Available")
            lines.append(f"• {name}: {price}")
    return "\n".join(lines)

def format_store_info(info):
    if not isinstance(info, dict):
        return "Store information is not available."

    lines = []
    for key, value in info.items():
        label = key.replace("_", " ").title()
        lines.append(f"{label}: {value}")
    return "\n".join(lines)

# ========== AI RESPONSE FUNCTION ==========

def generate_ai_response(user_query):
    try:
        store_info_text = STORE_INFO.strip() if isinstance(STORE_INFO, str) else "No store info available."
        product_catalog_text = format_product_catalog(PRODUCT_CATALOG)

        system_message = (
            "You are a helpful and friendly WhatsApp assistant for Tariq Halal Meats UK. "
            "Answer customer questions clearly and professionally using only the information below.\n\n"
            "🏬 STORE INFO:\n"
            f"{store_info_text}\n\n"
            "📦 PRODUCT CATALOG:\n"
            f"{product_catalog_text}\n\n"
            "If the question is about delivery, products, pricing, opening hours, or any other store-related details, "
            "respond using this info. If you're unsure, kindly let the customer know."
        )

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_query}
            ],
            max_tokens=500,
            temperature=0.3
        )

        return response.choices[0].message["content"].strip()

    except Exception as e:
        logger.exception("AI Response Error")
        return "Sorry, I had trouble understanding that. Please try again in a moment."

# ========== PRODUCT SEARCH ==========

def find_products(query):
    query = query.strip().lower()
    results = []

    for category, items in PRODUCT_CATALOG.items():
        for product_name, price in items.items():
            if query in product_name.lower() or query in category.lower():
                results.append(f"- {product_name} ({category}): {price}")

    if results:
        return "\n".join(results)
    else:
        return "Sorry, I couldn’t find any matching products. Try a different name like 'beef' or 'lamb'."

# ========== WHATSAPP ROUTE ==========

@app.route("/whatsapp", methods=["POST"])
def handle_whatsapp_message():
    try:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        if not validator.validate(
            request.url,
            request.form,
            request.headers.get('X-Twilio-Signature', '')
        ):
            logger.warning("Invalid Twilio signature")
            return "Unauthorized", 403

        message = request.values.get('Body', '').strip()
        if not message:
            return "Empty message", 400

        logger.info(f"Received message: {message}")

        product_results = find_products(message)

        if "Sorry, I couldn’t find any matching products" not in product_results:
            reply = f"We found these matching products:\n{product_results}\n\nNeed anything else?"
        else:
            ai_response = generate_ai_response(message)
            reply = ai_response or "Sorry, I couldn't find anything useful. Please ask a different question."

        logger.info(f"Sending response: {reply[:100]}...")

        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), mimetype="application/xml")

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        traceback.print_exc()
        return "Server Error", 500

# ========== STATUS ROUTE ==========

@app.route("/whatsapp/status", methods=["POST"])
def handle_status_update():
    status = request.values.get('MessageStatus', '')
    message_sid = request.values.get('MessageSid', '')
    logger.info(f"Message status update - SID: {message_sid}, Status: {status}")
    return "OK", 200

# ========== HEALTH CHECK ==========

@app.route("/health")
def health_check():
    return jsonify({
        "status": "operational",
        "services": {
            "openai": bool(OPENAI_API_KEY),
            "twilio": bool(TWILIO_AUTH_TOKEN)
        }
    })

# ========== HOME ==========

@app.route("/")
def home():
    return "🟢 Tariq Halal Meats WhatsApp Bot is Online"

# ========== RUN SERVER LOCALLY ==========

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.getenv("DEBUG", "false").lower() == "true"
    )

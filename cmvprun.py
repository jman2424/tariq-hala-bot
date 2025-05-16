import os
import traceback
import logging
from flask import Flask, request, jsonify, Response, session
from flask_caching import Cache
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
import openai
from dotenv import load_dotenv
from difflib import get_close_matches

# Load environment variables from .env file
load_dotenv()

# Import store data
from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

# ========== CONFIG ==========
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ========== UTILITIES ==========

def format_product_catalog(catalog):
    if not isinstance(catalog, dict):
        logger.warning("PRODUCT_CATALOG is not a dictionary.")
        return "Product catalog is unavailable."
    lines = []
    for category, products in catalog.items():
        lines.append(f"
🛒 {category.upper()}:")
        for product in products:
            if isinstance(product, dict):
                name = product.get('name', 'Unnamed')
                price = product.get('price', 'N/A')
                lines.append(f"• {name}: {price}")
    return "
".join(lines)
    lines = []
    for category, products in catalog.items():
        lines.append(f"
🛒 {category.upper()}:")
        for product in products:
            if isinstance(product, dict):
                lines.append(f"• {product.get('name', 'Unnamed')}: {product.get('price', 'N/A')}")
    return "
".join(lines)

def format_store_info(info):
    if not isinstance(info, dict):
        logger.warning("STORE_INFO is not a dictionary. Returning raw text.")
        return str(info)
    return "\n".join([f"{key.replace('_', ' ').title()}: {value}" for key, value in info.items()])

def fuzzy_product_search(query):
    query = query.lower()
    results = []
    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            if not isinstance(product, dict):
                continue
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
        logger.error("STORE_INFO is not a dictionary. Cannot process FAQs.")
        return "Store information is currently unavailable.", True
    if any(kw in message for kw in ["hours", "opening", "closing"]):
        return f"Our store is open from {STORE_INFO.get('store_hours', '9AM to 9PM')}.", True
    if "delivery" in message:
        return STORE_INFO.get("delivery_policy", "We offer fast and reliable delivery services."), True
    if "location" in message or "address" in message:
        return f"We are located at {STORE_INFO.get('store_location', 'Address not available.')}", True
    if "contact" in message:
        return f"You can reach us at {STORE_INFO.get('phone_number', 'Contact info unavailable.')}", True
    if "history" in message or "about" in message:
        return STORE_INFO.get("store_history", "We are proud to serve the community with high-quality halal meat."), True
    return None, False

def find_products(message):
    faq_response, is_faq = answer_faqs(message)
    if is_faq:
        return faq_response

    results = fuzzy_product_search(message)
    if results:
        lines = ["🛒 Products matching your query:"]
        for name, price, category in results:
            lines.append(f"- {name} ({category}): {price}")
        return "
".join(lines)
    return None

def generate_ai_response(message, memory=[]):
    try:
        context = (
            "You are the helpful WhatsApp assistant for Tariq Halal Meat Shop UK.
"
            f"
STORE INFO:
{format_store_info(STORE_INFO)}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}"
            "
Always respond politely and help the customer even if the question is not perfectly clear."
        )}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}"
            "
Always respond politely and help the customer even if the question is not perfectly clear."
        )}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}"
            "
Always respond politely and help the customer even if the question is not perfectly clear."
        )}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}"
            "
Always respond politely and help the customer even if the question is not perfectly clear."
        )}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}"
            "
Always respond politely and help the customer even if the question is not perfectly clear."
        )}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}"
            "
Always respond politely and help the customer even if the question is not perfectly clear."
        )}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}"
            "
Always respond politely and help the customer even if the question is not perfectly clear."
        )}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}"
            "
Always respond politely and help the customer even if the question is not perfectly clear."
        )}"
            f"

PRODUCT CATALOG:
{format_product_catalog(PRODUCT_CATALOG)}
"
            f"Always respond politely and help the customer even if the question is not perfectly clear."
        )

        messages = [{"role": "system", "content": context}]
        for past in memory[-5:]:
            messages.append({"role": "user", "content": past["user"]})
            messages.append({"role": "assistant", "content": past["bot"]})
        messages.append({"role": "user", "content": message})

        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.4,
            max_tokens=500
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("AI generation failed.")
        return "Sorry, I had trouble answering that. Please try again."

@app.route("/whatsapp", methods=["POST"])
def whatsapp_handler():
    try:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        valid = validator.validate(
            request.url,
            request.form,
            request.headers.get("X-Twilio-Signature", "")
        )
        if not valid:
            return "Unauthorized", 403

        message = request.values.get("Body", "").strip()
        from_number = request.values.get("From", "")

        logger.info(f"Incoming from {from_number}: {message}")

        # Log all messages
        log_path = os.path.join("logs", f"chat_{from_number.replace('+', '')}.txt")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"USER: {message}
")
        from_number = request.values.get("From", "")

        logger.info(f"Incoming from {from_number}: {message}")

        if not message:
            return "Empty message", 400

        session_key = f"session_{from_number}"
        history = cache.get(session_key) or []

        reply = find_products(message)
        if not reply:
            reply = generate_ai_response(message, memory=history)
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"BOT: {reply}
")

        history.append({"user": message, "bot": reply})
        cache.set(session_key, history[-10:], timeout=3600)

        response = MessagingResponse()
        response.message(reply)
        return Response(str(response), mimetype="application/xml")
    except Exception as e:
        logger.error(f"WhatsApp handler error: {e}")
        traceback.print_exc()
        return "Server Error", 500

@app.route("/health")
def health():
    return jsonify({"status": "online"})

@app.route("/")
def home():
    return "🟢 Tariq Halal Meat Shop Chatbot is live."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=True)



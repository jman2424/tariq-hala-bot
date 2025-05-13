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

# Load environment variables from .env file
load_dotenv()

# ✅ Imports
from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

# ========== CONFIGURATION ==========

app = Flask(__name__)

# Cache configuration (optional for better performance)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

# Logger configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== EXTERNAL KEYS ==========

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ========== FORMATTERS ==========

def format_product_catalog(catalog):
    """Formats the product catalog into a user-friendly string."""
    lines = []
    for category, products in catalog.items():
        lines.append(f"\n🛒 {category.upper()}")
        for product in products:
            name = product.get("name", "Unnamed Product")
            price = product.get("price", "Price Not Available")
            lines.append(f"• {name}: {price}")
    return "\n".join(lines)

def format_store_info(info):
    """Formats the store information into a readable string."""
    if not isinstance(info, dict):
        return "Store information is not available."
    lines = [f"{key.replace('_', ' ').title()}: {value}" for key, value in info.items()]
    return "\n".join(lines)

# ========== FUZZY SEARCH ==========

def find_products(message):
    # If the message is about finding a product
    if "product" in message.lower() or "buy" in message.lower():
        for product in PRODUCT_CATALOG:
            if isinstance(product, dict):  # Ensure it's a dictionary before accessing
                name = product.get("name", "Unknown Product")
                # You can refine the search, or add more details like price
                if name.lower() in message.lower():
                    return f"Sure! Here's {name}. If you'd like more details or to add it to your cart, let me know!"
        return "I couldn't find that product. Could you please check the name again?"

    # If the message is asking about the store
    elif "store hours" in message.lower() or "open" in message.lower():
        return "Our store is open from 9 AM to 9 PM, 7 days a week. Feel free to visit anytime!"

    # If the message is asking about delivery
    elif "delivery" in message.lower() or "shipping" in message.lower():
        return "We offer fast and reliable delivery. You can check our delivery policies on our website, or I can send you the details right here."

    # If the message is about general inquiries (e.g., about the store's history, contact info, etc.)
    elif "history" in message.lower() or "contact" in message.lower():
        return "Tariq Halal Meatshop has been serving the community with high-quality halal meat since 1990. You can contact us at +44 123 456 789 or visit us in-store!"

    # If the message is unrelated to products (e.g., greetings)
    elif "hello" in message.lower() or "hi" in message.lower():
        return "Hello! How can I assist you today? 😊"

    # If the message is not recognized, show general help
    else:
        return "I'm here to help! You can ask about our products, store hours, delivery policies, or anything else!"


    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            name = product["name"]
            price = product["price"]
            all_words = f"{name} {category}".lower()

            if query in all_words:
                results.append(f"- {name} ({category}): {price}")
            else:
                close = get_close_matches(query, [name.lower(), category.lower()], n=1, cutoff=0.6)
                if close:
                    results.append(f"- {name} ({category}): {price}")

    if results:
        return "\n".join(results)
    else:
        return "Sorry, I couldn’t find any matching products. Try a different name like 'beef' or 'minced chicken'."

# ========== AI ASSISTANT ==========

def generate_ai_response(user_query):
    """Generates a response using OpenAI's GPT model."""
    try:
        product_catalog_text = format_product_catalog(PRODUCT_CATALOG)
        store_info_text = format_store_info(STORE_INFO)

        system_message = (
            "You are a helpful and friendly WhatsApp assistant for Tariq Halal Meats UK. "
            "Use the info below to answer customer questions clearly, kindly, and professionally.\n\n"
            f"🏬 STORE INFO:\n{store_info_text}\n\n"
            f"📦 PRODUCT CATALOG:\n{product_catalog_text}\n\n"
            "Answer questions about delivery, pricing, hours, or anything else using only this info. "
            "If you’re not sure, politely say you're unsure."
        )

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system_message},
                      {"role": "user", "content": user_query}],
            temperature=0.3,
            max_tokens=500
        )

        return response.choices[0].message["content"].strip()
    except Exception as e:
        logger.exception("AI response failed")
        return "Sorry, I had trouble answering that. Please try again shortly."

# ========== WHATSAPP ROUTE ==========

@app.route("/whatsapp", methods=["POST"])
def handle_whatsapp_message():
    """Handles incoming WhatsApp messages and responds accordingly."""
    try:
        # Twilio validation
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        if not validator.validate(
            request.url,
            request.form,
            request.headers.get('X-Twilio-Signature', '')
        ):
            logger.warning("Unauthorized request!")
            return "Unauthorized", 403

        # Retrieve the incoming message
        message = request.values.get('Body', '').strip()
        if not message:
            return "Empty message", 400

        logger.info(f"Incoming message: {message}")

        # Search for matching products
        product_results = find_products(message)

        # If no products found, fall back to AI assistant
        if "Sorry" not in product_results:
            reply = f"🔍 Here’s what we found:\n{product_results}\n\nNeed anything else?"
        else:
            ai_response = generate_ai_response(message)
            reply = ai_response

        logger.info(f"Bot reply: {reply[:100]}...")

        # Send the response via Twilio
        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), mimetype="application/xml")

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        traceback.print_exc()
        return "Server Error", 500

# ========== STATUS UPDATE (OPTIONAL) ==========

@app.route("/whatsapp/status", methods=["POST"])
def handle_status_update():
    """Logs status updates from Twilio."""
    logger.info(f"Status update: SID={request.values.get('MessageSid', '')}, Status={request.values.get('MessageStatus', '')}")
    return "OK", 200

# ========== HEALTH CHECK ==========

@app.route("/health")
def health_check():
    """Checks the health of the service."""
    return jsonify({
        "status": "✅ Online",
        "openai": bool(OPENAI_API_KEY),
        "twilio": bool(TWILIO_AUTH_TOKEN)
    })

# ========== HOME ==========

@app.route("/")
def home():
    """Basic homepage route."""
    return "🟢 Tariq Halal Meat Shop WhatsApp Bot is running!"

# ========== MAIN ==========

if __name__ == "__main__":
    # Run the Flask app
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=os.getenv("DEBUG", "false").lower() == "true"
    )

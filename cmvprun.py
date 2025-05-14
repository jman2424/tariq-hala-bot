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

# Imports of your store info and product catalog
from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

# ===== CONFIGURATION =====

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment keys
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ===== HELPERS =====

def format_product_catalog(catalog):
    """Convert product catalog dict into a readable string."""
    lines = []
    for category, products in catalog.items():
        lines.append(f"\n🛒 {category.upper()}:")
        for product in products:
            name = product.get("name", "Unnamed Product")
            price = product.get("price", "Price Not Available")
            lines.append(f"• {name}: {price}")
    return "\n".join(lines)

def format_store_info(info):
    """Convert store info dict into a readable string."""
    if not isinstance(info, dict):
        return "Store information is not available."
    return "\n".join([f"{key.replace('_', ' ').title()}: {value}" for key, value in info.items()])

def fuzzy_product_search(query):
    """Search products with fuzzy matching and return matches."""
    results = []
    query_lower = query.lower()

    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            name = product.get("name", "").lower()
            if query_lower in name or query_lower in category.lower():
                results.append(f"- {product['name']} ({category.title()}): {product['price']}")
            else:
                # Use fuzzy matching for approximate matches
                close = get_close_matches(query_lower, [name, category.lower()], n=1, cutoff=0.6)
                if close:
                    results.append(f"- {product['name']} ({category.title()}): {product['price']}")

    if results:
        return "\n".join(results)
    else:
        return None  # No matches found

def find_products(message):
    """Improved product finder with fuzzy word matching and keyword replies."""
    message_lower = message.lower()
    
    # Simple keyword replies
    if any(x in message_lower for x in ["store hours", "open", "close"]):
        return "Our store is open from 9 AM to 9 PM, 7 days a week. Feel free to visit anytime!"
    if any(x in message_lower for x in ["delivery", "shipping"]):
        return "We offer fast and reliable delivery. You can check our delivery policies on our website, or I can send you the details right here."
    if any(x in message_lower for x in ["history", "contact"]):
        return "Tariq Halal Meatshop has been serving the community with high-quality halal meat since 1990. You can contact us at +44 123 456 789 or visit us in-store!"
    if any(x in message_lower for x in ["hello", "hi", "hey"]):
        return "Hello! How can I assist you today? 😊"
    
    # Search products with fuzzy matching by words
    all_product_names = []
    product_map = {}
    
    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            name = product.get("name", "").lower()
            all_product_names.append(name)
            product_map[name] = (product, category)
    
    # Find close matches to message words
    words = message_lower.split()
    matched_products = set()
    for word in words:
        matches = get_close_matches(word, all_product_names, n=3, cutoff=0.6)
        for m in matches:
            matched_products.add(m)
    
    if matched_products:
        results = []
        for name in matched_products:
            product, category = product_map[name]
            results.append(f"- {product['name']} ({category.title()}): {product['price']}")
        return "Here are some products I found:\n" + "\n".join(results)
    
    # If no match found
    return "Sorry, I couldn’t find any matching products. Could you try a different name or be more specific?"

def generate_ai_response(user_query):
    """Generate response from OpenAI GPT-3.5 Turbo using store info and product catalog."""
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
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_query}
            ],
            temperature=0.3,
            max_tokens=500,
        )

        return response.choices[0].message["content"].strip()

    except Exception:
        logger.exception("AI response generation failed.")
        return "Sorry, I had trouble answering that. Please try again shortly."

# ===== FLASK ROUTES =====

@app.route("/whatsapp", methods=["POST"])
def handle_whatsapp_message():
    """Handle incoming WhatsApp messages."""
    try:
        # Validate request from Twilio
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        valid = validator.validate(
            request.url,
            request.form,
            request.headers.get('X-Twilio-Signature', '')
        )
        if not valid:
            logger.warning("Unauthorized request received.")
            return "Unauthorized", 403

        message = request.values.get('Body', '').strip()
        if not message:
            return "Empty message", 400

        logger.info(f"Received message: {message}")

        # Try canned/fuzzy product or info response first
        product_response = find_products(message)
        if product_response:
            reply = product_response
        else:
            # Fallback to AI-generated response
            reply = generate_ai_response(message)

        logger.info(f"Replying with: {reply[:100]}...")

        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), mimetype="application/xml")

    except Exception as e:
        logger.error(f"Error in message handling: {e}")
        traceback.print_exc()
        return "Server Error", 500

@app.route("/whatsapp/status", methods=["POST"])
def handle_status_update():
    """Log Twilio status updates (optional)."""
    logger.info(f"Status update: SID={request.values.get('MessageSid', '')}, Status={request.values.get('MessageStatus', '')}")
    return "OK", 200

@app.route("/health")
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "✅ Online",
        "openai": bool(OPENAI_API_KEY),
        "twilio": bool(TWILIO_AUTH_TOKEN)
    })

@app.route("/")
def home():
    """Basic home route."""
    return "🟢 Tariq Halal Meat Shop WhatsApp Bot is running!"

# ===== RUN APP =====

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=os.getenv("DEBUG", "false").lower() == "true"
    )

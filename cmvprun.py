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
    lines = []
    for category, products in catalog.items():
        lines.append(f"\n🛒 {category.upper()}:")
        for product in products:
            lines.append(f"• {product['name']}: {product['price']}")
    return "\n".join(lines)

def format_store_info(info):
    return "\n".join([f"{key.replace('_', ' ').title()}: {value}" for key, value in info.items()])

def fuzzy_product_search(query):
    query = query.lower()
    results = []
    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            name = product['name'].lower()
            if query in name or query in category.lower():
                results.append((product['name'], product['price'], category.title()))
            else:
                match = get_close_matches(query, [name], n=1, cutoff=0.65)
                if match:
                    results.append((product['name'], product['price'], category.title()))
    return results if results else None

def answer_faqs(message):
    message = message.lower()
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

def handle_order_flow(message, user_id):
    cart_key = f"cart_{user_id}"
    user_key = f"user_{user_id}"
    cart = cache.get(cart_key) or []
    user_data = cache.get(user_key) or {}
    lowered = message.lower()

    if lowered.startswith("add "):
        product_name = message[4:].strip()
        matches = fuzzy_product_search(product_name)
        if matches:
            name, price, category = matches[0]
            cart.append((name, price))
            cache.set(cart_key, cart, timeout=3600)
            return f"✅ '{name}' has been added to your cart."
        else:
            return "❌ Sorry, I couldn’t find that product. Please try again."

    elif "show cart" in lowered or "view cart" in lowered:
        if not cart:
            return "🛒 Your cart is currently empty."
        lines = ["🧾 Your current cart:"]
        total = 0.0
        for name, price in cart:
            lines.append(f"• {name}: {price}")
            try:
                total += float(price.replace("£", ""))
            except:
                pass
        lines.append(f"Total: £{total:.2f}")
        return "\n".join(lines)

    elif "checkout" in lowered:
        if not cart:
            return "🛒 Your cart is empty. Add items before checking out."
        if "name" not in user_data:
            user_data["stage"] = "awaiting_name"
            cache.set(user_key, user_data, timeout=3600)
            return "📝 Please provide your name to proceed with your order."
        if "address" not in user_data:
            user_data["stage"] = "awaiting_address"
            cache.set(user_key, user_data, timeout=3600)
            return "📍 Please provide your delivery address."
        if "phone" not in user_data:
            user_data["stage"] = "awaiting_phone"
            cache.set(user_key, user_data, timeout=3600)
            return "📞 What is your contact number?"

        cache.delete(cart_key)
        cache.delete(user_key)
        return f"🎉 Thank you {user_data['name']}! Your order has been received. We will deliver to {user_data['address']} and contact you at {user_data['phone']}."

    # Collecting user details
    if user_data.get("stage") == "awaiting_name":
        user_data["name"] = message.strip()
        user_data["stage"] = "awaiting_address"
        cache.set(user_key, user_data, timeout=3600)
        return "📍 Thanks! Now please enter your delivery address."
    if user_data.get("stage") == "awaiting_address":
        user_data["address"] = message.strip()
        user_data["stage"] = "awaiting_phone"
        cache.set(user_key, user_data, timeout=3600)
        return "📞 Got it. Please enter your contact phone number."
    if user_data.get("stage") == "awaiting_phone":
        user_data["phone"] = message.strip()
        user_data.pop("stage", None)
        cache.set(user_key, user_data, timeout=3600)
        return "✅ All details received. You can now type 'checkout' again to confirm your order."

    return None

def find_products(message):
    faq_response, is_faq = answer_faqs(message)
    if is_faq:
        return faq_response

    results = fuzzy_product_search(message)
    if results:
        lines = ["Here are some products I found:"]
        for name, price, category in results:
            lines.append(f"- {name} ({category}): {price}")
        return "\n".join(lines)

    return None

def generate_ai_response(message, memory=[]):
    try:
        context = (
            f"You are the helpful WhatsApp assistant for Tariq Halal Meat Shop UK.\n"
            f"\nSTORE INFO:\n{format_store_info(STORE_INFO)}"
            f"\n\nPRODUCT CATALOG:\n{format_product_catalog(PRODUCT_CATALOG)}\n"
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

# ========== FLASK ROUTES ==========
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

        if not message:
            return "Empty message", 400

        # Use cache to simulate memory per number
        session_key = f"session_{from_number}"
        history = cache.get(session_key) or []

        # Check for order interaction
        order_reply = handle_order_flow(message, from_number)
        if order_reply:
            reply = order_reply
        else:
            reply = find_products(message)
            if not reply:
                reply = generate_ai_response(message, memory=history)

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

# ========== MAIN ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=True)

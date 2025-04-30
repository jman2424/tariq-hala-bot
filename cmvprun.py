import os
import traceback
import logging
from flask import Flask, request, jsonify, Response
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI

# ========== CONFIGURATION ==========
app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== EXTERNAL KEYS ==========
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=OPENAI_API_KEY)

STORE_INFO = {
    "store_name": "Tariq Halal Meat Store",
    "store_location": "UK",
    "store_hours": "Monday to Saturday 9am - 8pm, Sunday 10am - 6pm",
    "delivery_policy": "We offer next-day delivery across the UK for orders placed before 2pm.",
    "contact_info": {
        "phone": "0121 234 5678",
        "email": "info@tariqhalalmeatstore.co.uk"
    }
}

PRODUCT_CATALOG = [
    {"category": "Poultry", "items": [
        {"name": "Whole Chicken 1kg", "price": "£3.99"},
        {"name": "Chicken Breast Boneless 1kg", "price": "£5.49"},
        {"name": "Chicken Thighs 1kg", "price": "£4.49"},
        {"name": "Chicken Drumsticks 1kg", "price": "£3.79"},
        {"name": "Chicken Wings 1kg", "price": "£3.59"}
    ]},
    {"category": "Lamb", "items": [
        {"name": "Lamb Chops 1kg", "price": "£9.99"},
        {"name": "Lamb Mince 1kg", "price": "£8.49"},
        {"name": "Lamb Shoulder 1kg", "price": "£8.99"},
        {"name": "Lamb Leg 1kg", "price": "£9.49"},
        {"name": "Lamb Ribs 1kg", "price": "£7.99"}
    ]},
    {"category": "Beef", "items": [
        {"name": "Beef Mince 1kg", "price": "£6.99"},
        {"name": "Beef Steak 1kg", "price": "£9.99"},
        {"name": "Beef Ribs 1kg", "price": "£7.99"},
        {"name": "Beef Shin 1kg", "price": "£6.49"},
        {"name": "Beef Bones 1kg", "price": "£2.99"}
    ]},
    {"category": "Groceries", "items": [
        {"name": "Basmati Rice 5kg", "price": "£10.99"},
        {"name": "Sunflower Oil 1L", "price": "£2.49"},
        {"name": "Plain Flour 1kg", "price": "£1.09"},
        {"name": "Chickpeas 400g", "price": "£0.89"},
        {"name": "Red Lentils 1kg", "price": "£2.99"}
    ]},
    {"category": "Frozen Meats", "items": [
        {"name": "Frozen Chicken Nuggets 1kg", "price": "£4.49"},
        {"name": "Frozen Beef Burgers 1kg", "price": "£5.99"},
        {"name": "Frozen Lamb Kofta 1kg", "price": "£6.49"}
    ]},
    {"category": "Specialty Meats", "items": [
        {"name": "Marinated Chicken Wings 1kg", "price": "£4.99"},
        {"name": "Spicy Lamb Chops 1kg", "price": "£10.49"},
        {"name": "BBQ Beef Ribs 1kg", "price": "£8.99"}
    ]}
]
# ========== HELPER FUNCTIONS ==========

def find_products(search_term):
    search_term = search_term.lower().strip()
    results = {}

    for category, products in PRODUCT_CATALOG.items():
        matched_products = [(product, price) for product, price in products.items() if search_term in product.lower()]
        if matched_products:
            results[category] = matched_products

    return results

def generate_ai_response(user_query):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful WhatsApp assistant for Tariq Halal Meats UK. "
                        "Use only the provided store information to answer. "
                        "Be concise (1-2 short paragraphs max). "
                        "For product prices, direct to the price list. "
                        "If unsure, ask them to call 0208 908 9440."
                    )
                },
                {
                    "role": "user",
                    "content": f"Business Info:\n{STORE_INFO}\n\nCustomer Question: {user_query}"
                }
            ],
            temperature=0.3,
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"AI Error: {str(e)}")
        return None

# ========== WHATSAPP ROUTE ==========
@app.route("/whatsapp", methods=["POST"])
@limiter.limit("5 per minute")
def handle_whatsapp_message():
    try:
        # Validate Twilio request
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
        if product_results:
            response_lines = ["We found these matching products:"]
            for category, items in product_results.items():
                response_lines.append(f"\n*{category}*")
                response_lines.extend(f"- {name}: {price}" for name, price in items)
            response_lines.append("\nNeed anything else?")
            reply = "\n".join(response_lines)
        else:
            ai_response = generate_ai_response(message)
            reply = ai_response or (
                "Sorry, I couldn't process your request. "
                "Please call ☎️ 0208 908 9440 for assistance."
            )

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
            "openai": bool(client.api_key),
            "twilio": bool(TWILIO_AUTH_TOKEN)
        }
    })

# ========== HOME ==========
@app.route("/")
def home():
    return "🟢 Tariq Halal Meats WhatsApp Bot is Online"

# ========== RUN SERVER ==========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.getenv("DEBUG", "false").lower() == "true"
    )

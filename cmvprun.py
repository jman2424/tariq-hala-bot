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

# ✅ Set OpenAI API key globally
openai.api_key = OPENAI_API_KEY

# ========== PRODUCT SEARCH FUNCTION ==========
@lru_cache(maxsize=128)
def find_products(search_term):
    search_term = search_term.lower().strip()
    results = {}

    for category, products in PRODUCT_CATALOG.items():
        matched_products = []

        for name, price in products.items():
            if search_term in name.lower():
                matched_products.append((name, price))

        if matched_products:
            results[category] = matched_products

    return results

# ========== AI RESPONSE FUNCTION ==========
def generate_ai_response(user_query):
    prompt = "You are a helpful WhatsApp assistant for Tariq Halal Meats UK."

    if "delivery" in user_query.lower():
        prompt += " Focus on providing delivery-related information."
    elif "hours" in user_query.lower():
        prompt += " Provide the business hours."
    elif "cost" in user_query.lower() and "chicken" in user_query.lower():
        prompt += " Provide the cost of 1 kg of chicken."
    else:
        prompt += " Provide concise and relevant answers from the product list or business information."

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_query}
            ],
            max_tokens=150,
            temperature=0.3
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        logger.error(f"AI Error: {str(e)}")
        return "Sorry, I encountered an issue while processing your request. Please try again later."

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
        if product_results:
            response_lines = ["We found these matching products:"]
            for category, items in product_results.items():
                response_lines.append(f"\n*{category}*")
                response_lines.extend(f"- {name}: {price}" for name, price in items)
            response_lines.append("\nNeed anything else?")
            reply = "\n".join(response_lines)
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


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
        lines.append("\n🛒 {}:".format(category.upper()))
        for product in products:
            if isinstance(product, dict):
                name = product.get('name', 'Unnamed')
                price = product.get('price', 'N/A')
                lines.append("• {}: {}".format(name, price))
    return "\n".join(lines)

def format_store_info(info):
    if not isinstance(info, dict):
        logger.warning("STORE_INFO is not a dictionary. Returning raw text.")
        return str(info)
    return "\n".join(["{}: {}".format(key.replace('_', ' ').title(), value) for key, value in info.items()])

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
        return "Our store is open from {}.".format(STORE_INFO.get('store_hours', '9AM to 9PM')), True
    if "delivery" in message:
        return STORE_INFO.get("delivery_policy", "We offer fast and reliable delivery services."), True
    if "location" in message or "address" in message:
        return "We are located at {}".format(STORE_INFO.get('store_location', 'Address not available.')), True
    if "contact" in message:
        return "You can reach us at {}".format(STORE_INFO.get('phone_number', 'Contact info unavailable.')), True
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
            lines.append("- {} ({}): {}".format(name, category, price))
        return "\n".join(lines)
    return None

def generate_ai_response(message, memory=[]):
    try:
        context = (
            "You are the helpful WhatsApp assistant for Tariq Halal Meat Shop UK.\n"
            "\nSTORE INFO:\n{}".format(format_store_info(STORE_INFO)) +
            "\n\nPRODUCT CATALOG:\n{}".format(format_product_catalog(PRODUCT_CATALOG)) +
            "\nAlways respond politely and help the customer even if the question is not perfectly clear."
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


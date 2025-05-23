import os
import logging
from datetime import datetime, timedelta

import pytz
from flask import Flask, request, jsonify, Response
from flask_caching import Cache
from dotenv import load_dotenv
from openai import OpenAI
from rapidfuzz import process
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

# Load environment variables
load_dotenv()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from store_info import store_info as STORE_INFO
from product_catalog import PRODUCT_CATALOG

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecret")
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache"})

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TariqBot")
client = OpenAI(api_key=OPENAI_API_KEY)

GOODBYE_KEYWORDS = {"bye", "goodbye", "thanks", "thank you", "ta"}
FEEDBACK_PROMPT = "Was this response helpful? Reply YES or NO."
SESSION_TTL = 7 * 24 * 3600
STALE_DURATION = timedelta(days=1)

def normalize_catalog():
    for category, items in list(PRODUCT_CATALOG.items()):
        if isinstance(items, dict):
            PRODUCT_CATALOG[category] = [
                {"name": name, "price": price} for name, price in items.items()
            ]

normalize_catalog()

store_locations = {
    branch: {
        "address": details.split("|")[0].strip(),
        "postcode": details.split(",")[-1].strip().split()[0],
        "hours": STORE_INFO.get("store_hours", "9AM to 9PM"),
    }
    for branch, details in STORE_INFO.get("branches", {}).items()
}

def get_uk_time():
    return datetime.now(pytz.timezone("Europe/London")).strftime("%A, %d %B %Y, %I:%M %p")

def format_store_info(info):
    return "\n".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in info.items())

def format_product_catalog(catalog):
    lines = []
    for category, products in catalog.items():
        lines.append(f"🛒 {category.title()}:")
        for product in products:
            lines.append(f"• {product['name']}: {product['price']}")
    return "\n".join(lines)

def format_category_products(category, products):
    lines = [f"🛒 Products in {category.title()}:"]
    for p in products:
        lines.append(f"- {p['name']}: {p['price']}")
    return "\n".join(lines)

def locate_store_by_postcode(message):
    msg = message.lower()
    for area, data in store_locations.items():
        if area.lower() in msg or data["postcode"].lower() in msg:
            return f"Closest store: {area}\nAddress: {data['address']}\nHours: {data['hours']}"
    return None

def answer_faqs(message):
    msg = message.lower()
    if "time" in msg or "clock" in msg:
        return f"Current UK time: {get_uk_time()}", True
    if any(k in msg for k in ("hours", "opening", "closing")):
        return f"Store hours: {STORE_INFO.get('store_hours', '9AM to 9PM')}", True
    if "delivery" in msg:
        return STORE_INFO.get("delivery_policy", "We offer fast delivery."), True
    if "location" in msg or "address" in msg:
        loc = locate_store_by_postcode(msg)
        return loc or f"Main store is at {STORE_INFO.get('store_location', 'Unavailable')}", True
    if "contact" in msg:
        return f"Contact us at {STORE_INFO.get('contact', 'Unavailable')}", True
    if "history" in msg or "about" in msg:
        return STORE_INFO.get("store_history", "We are proud to serve the community."), True
    return None, False

def search_by_category(message):
    match = process.extractOne(message.lower(), PRODUCT_CATALOG.keys(), score_cutoff=60)
    return format_category_products(match[0], PRODUCT_CATALOG[match[0]]) if match else None

def fuzzy_product_search(query):
    results = []
    for category, products in PRODUCT_CATALOG.items():
        names = [p['name'].lower() for p in products]
        match = process.extractOne(query, names, score_cutoff=75)
        if match:
            prod = next(p for p in products if p['name'].lower() == match[0])
            results.append((prod['name'], prod['price'], category.title()))
    return results or None

def find_products(message):
    text = message.strip().lower()
    for category, products in PRODUCT_CATALOG.items():
        for product in products:
            if product['name'].lower() == text:
                return f"🛒 {product['name']}: {product['price']}"
    if text in PRODUCT_CATALOG:
        return format_category_products(text, PRODUCT_CATALOG[text])
    faq, is_faq = answer_faqs(message)
    if is_faq:
        return faq
    cat = search_by_category(text)
    if cat:
        return cat
    matches = [
        (product['name'], product['price'], category.title())
        for category, products in PRODUCT_CATALOG.items()
        for product in products
        if text in product['name'].lower()
    ]
    if matches:
        lines = ["🛒 Products matching your query:"]
        for name, price, cat in matches:
            lines.append(f"- {name} ({cat}): {price}")
        return "\n".join(lines)
    return None

def generate_ai_response(message, memory, model='gpt-4'):
    context = (
        "You are the helpful WhatsApp assistant for Tariq Halal Meat Shop UK.\n"
        "Answer using store info and product catalog.\n"
        f"\nSTORE INFO:\n{format_store_info(STORE_INFO)}\n"
        f"\nPRODUCT CATALOG:\n{format_product_catalog(PRODUCT_CATALOG)}"
    )
    messages = [{"role": "system", "content": context}] + [
        msg for h in memory[-5:] for msg in (
            {"role": "user", "content": h['user']},
            {"role": "assistant", "content": h['bot']}
        )
    ] + [{"role": "user", "content": message}]
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
        max_tokens=500
    ).choices[0].message.content.strip()

@app.route("/whatsapp", methods=["POST"])
def whatsapp_handler():
    try:
        if not RequestValidator(TWILIO_AUTH_TOKEN).validate(
            request.url,
            request.form,
            request.headers.get("X-Twilio-Signature", "")
        ):
            return "Unauthorized", 403

        body = request.values.get("Body", "").strip()
        sender = request.values.get("From", "")
        if not body:
            return "Empty message", 400

        logger.info(f"Received from {sender}: {body}")
        session_key = f"session_{sender}"
        session = cache.get(session_key) or {"history": [], "last": datetime.utcnow()}
        history, last_time = session['history'], session['last']
        model_name = 'gpt-3.5-turbo' if (datetime.utcnow() - last_time) > STALE_DURATION else 'gpt-4'

        low = body.lower()
        if low in ["yes", "no"]:
            return Response(str(MessagingResponse().message("Thanks for your feedback!")), mimetype="application/xml")
        if low in GOODBYE_KEYWORDS:
            resp = MessagingResponse()
            resp.message("Goodbye! Have a great day.")
            resp.message(FEEDBACK_PROMPT)
            return Response(str(resp), mimetype="application/xml")

        reply = find_products(body) or generate_ai_response(body, history, model=model_name)

        history.append({"user": body, "bot": reply})
        session['last'] = datetime.utcnow()
        cache.set(session_key, session, timeout=SESSION_TTL)

        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), mimetype="application/xml")
    except Exception:
        logger.exception("Error in whatsapp_handler")
        return "Server Error", 500

@app.route("/")
def home():
    return "🟢 Tariq Halal Meat Shop Chatbot is live."

@app.route("/health")
def health():
    return jsonify({"status": "online"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)), debug=False)

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from openai import OpenAI
from flask_caching import Cache
import os
import traceback
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize Flask app FIRST
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize cache
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache'})

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Load API keys
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# ========== REST OF YOUR CODE (PRODUCT CATALOG, STORE INFO, HELPER FUNCTIONS) ==========
# [Keep all your existing code for these sections]

# ========== ROUTES ==========
@app.route("/whatsapp", methods=["POST"])
@limiter.limit("5 per minute")
@cache.cached(timeout=300, query_string=True)
def handle_whatsapp_message():
    # [Keep your existing handle_whatsapp_message implementation]
    pass

@app.route("/whatsapp/status", methods=["POST"])
def handle_status_update():
    # [Keep your existing status update handler]
    pass

@app.route("/health")
def health_check():
    # [Keep your existing health check]
    pass

@app.route("/")
def home():
    """Simple root endpoint"""
    return "🟢 Tariq Halal Meats WhatsApp Bot is Online"

# ========== APPLICATION ENTRY POINT ==========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.getenv('DEBUG', 'false').lower() == 'true'
    )

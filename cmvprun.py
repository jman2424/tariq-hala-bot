from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os
import traceback

app = Flask(__name__)

# ✅ Set your OpenAI API key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # Use your real key or load from .env

# ✅ Define chatbot prompt template
def generate_response(user_input):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a customer service chatbot for Tariq Halal Meat."},
                {"role": "user", "content": user_input},
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return "❌ Chatbot is not available right now."

# ✅ Ngrok or public URL
NGROK_URL = "https://e677-2a02-6b67-d903-2000-b0ea-b319-3a35-411a.ngrok-free.app"

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Handles incoming WhatsApp messages from Twilio."""
    try:
        print(f"🔹 Incoming Request Data: {request.values}")
        incoming_msg = request.values.get("Body", "").strip()

        if not incoming_msg:
            print("⚠️ No message received.")
            return "No message received", 400

        print(f"✅ Received Message: {incoming_msg}")

        # 🟡 Generate AI response using OpenAI GPT-3.5 Turbo
        print("🟡 Generating AI response...")
        ai_response = generate_response(incoming_msg)

        print(f"✅ AI Response: {ai_response}")

        response = MessagingResponse()
        response.message(ai_response)

        print("✅ Sending response back to WhatsApp")
        return str(response)

    except Exception as e:
        print(f"❌ ERROR: {e}")
        traceback.print_exc()
        return f"Internal Server Error: {e}", 500

@app.route("/whatsapp/status", methods=["POST"])
def whatsapp_status_callback():
    """Handles Twilio message status updates."""
    status = request.values.get("MessageStatus", "")
    message_sid = request.values.get("MessageSid", "")
    print(f"🔹 Message SID: {

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os
import traceback

app = Flask(__name__)

# ✅ Load OpenAI API key from .env
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ Generate response from OpenAI
def generate_response(user_input):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful customer service chatbot for Tariq Halal Meat."},
                {"role": "user", "content": user_input},
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ ERROR generating response: {e}")
        traceback.print_exc()
        return "❌ Chatbot is not available right now."

# ✅ Handle incoming WhatsApp message
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        print(f"🔹 Incoming Request Data: {request.values}")
        incoming_msg = request.values.get("Body", "").strip()

        if not incoming_msg:
            print("⚠️ No message received.")
            return "No message received", 400

        print(f"✅ Received Message: {incoming_msg}")
        print("🟡 Generating AI response...")
        ai_response = generate_response(incoming_msg)
        print(f"✅ AI Response: {ai_response}")

        resp = MessagingResponse()
        resp.message(ai_response)
        print("✅ Sending response back to WhatsApp")
        return str(resp)

    except Exception as e:
        print(f"❌ ERROR in webhook: {e}")
        traceback.print_exc()
        return f"Internal Server Error: {e}", 500

# ✅ Handle message status updates from Twilio
@app.route("/whatsapp/status", methods=["POST"])
def whatsapp_status_callback():
    status = request.values.get("MessageStatus", "")
    message_sid = request.values.get("MessageSid", "")
    print(f"🔹 Message SID: {message_sid}, Status: {status}")
    return "Status received", 200

# ✅ Home page
@app.route("/")
def home():
    return "✅ Hello, Your chatbot is running."

# ✅ Start Flask app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 1234))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)

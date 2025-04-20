from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from langchain_ollama import OllamaLLM
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import os
import traceback

app = Flask(__name__)

# ✅ Load the Halal Chatbot model
try:
    llm = OllamaLLM(model="halal-chatbot")
    print("✅ Model loaded successfully.")
except Exception as e:
    print(f"❌ ERROR: Failed to load model: {e}")
    llm = None  # Ensure llm is defined to prevent crash later

# ✅ Define chatbot prompt template
prompt = PromptTemplate(
    input_variables=["input"],
    template="""
You are a customer service chatbot for Tariq Halal Meat.
- Give **brief responses (1-2 sentences only)**.
- **Reply quickly** and do not generate long messages.
- If more details are needed, **ask the user if they want more info**.

Customer: {input}
Chatbot:
"""
)

# ✅ Connect prompt with Langchain model
chatbot = LLMChain(prompt=prompt, llm=llm) if llm else None

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

        if chatbot:
            print("🟡 Generating AI response...")
            ai_response = chatbot.invoke({"input": incoming_msg})
        else:
            ai_response = "❌ Chatbot is not available right now."

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
    print(f"🔹 Message SID: {message_sid}, Status: {status}")
    return "Status received", 200

@app.route("/")
def home():
    return "✅ Hello, Your chatbot is running."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 1234))  # ✅ Use 5000 locally, Render will provide PORT
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)

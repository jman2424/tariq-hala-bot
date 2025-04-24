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

# ✅ Store product catalog separately for easy updates
PRODUCT_CATALOG = {
    "Lamb": {
        "Lamb Mince 500g": "£5.99",
        "Lamb Chops 1kg": "£10.99",
        "Lamb Shoulder 1kg": "£9.99"
    },
    "Beef": {
        "Beef Steak 1kg": "£9.49",
        "Beef Mince 500g": "£4.99"
    },
    "Chicken": {
        "Whole Chicken 1.2kg": "£4.99",
        "Chicken Breast 1kg": "£6.99",
        "Chicken Wings 1kg": "£4.49"
    },
    "Marinated Meats": {
        "Spicy Chicken Wings 1kg": "£5.49",
        "Marinated Lamb Chops 1kg": "£11.99",
        "Marinated Chicken Tikka 1kg": "£6.99",
        "Marinated Chicken Wings 1kg": "£5.49",
        "Peri Peri Chicken 1kg": "£6.99"
    },
    "Exotic Meats": {
        "Goat Meat 1kg": "£10.99",
        "Camel Mince 1kg": "£12.99",
        "Venison Fillet 500g": "£13.50"
    },
    "Groceries": {
        "Basmati Rice 5kg": "£8.99",
        "Chickpeas 2kg": "£2.99",
        "Lentils 2kg": "£3.49"
    },
    "Spices & Seasonings": {
        "Cumin Seeds 100g": "£1.50",
        "Turmeric Powder 100g": "£1.00",
        "Garam Masala 100g": "£1.25"
    },
    "Sauces": {
        "Peri Peri Sauce 250ml": "£2.00",
        "Mint Sauce 250ml": "£1.75",
        "Yogurt Sauce 250ml": "£1.50",
        "BBQ Sauce 250ml": "£1.80",
        "Chilli Sauce 250ml": "£1.60"
    },
    "Flour, Naan, Chapatti": {
        "Chapatti Flour 10kg": "£7.50",
        "Plain Naan (2 pieces)": "£1.00",
        "Garlic Naan (2 pieces)": "£1.20"
    },
    "Drinks & Mocktails": {
        "Mango Juice 1L": "£1.50",
        "Pineapple Juice 1L": "£1.50",
        "Mocktail Mojito 330ml": "£1.00",
        "Strawberry Mocktail 330ml": "£1.00",
        "Lychee Drink 330ml": "£1.00"
    },
    "Tea & Coffee": {
        "Loose Black Tea 250g": "£2.75",
        "Instant Coffee 200g": "£3.50"
    },
    "Oils & Ghee": {
        "Sunflower Oil 1L": "£2.99",
        "Vegetable Oil 1L": "£2.75",
        "Desi Ghee 500g": "£4.50"
    },
    "Everyday Essentials": {
        "Toilet Roll 9 Pack": "£3.99",
        "Kitchen Roll 2 Pack": "£2.50",
        "Bin Bags 20pcs": "£1.99"
    },
    "Bakery": {
        "Plain Naan (2 pieces)": "£1.00",
        "Tandoori Roti (5 pieces)": "£1.20",
        "Sweet Buns Pack": "£1.50"
    }
}

# ✅ Store information for Tariq Halal Meats
STORE_INFO = """
Tariq Halal Meats Delivery Info:
- ❌ No delivery to Isle of Man, Isle of Wight, Jersey.
- ✅ Mainland UK delivery 7 days a week.
- 🚚 Orders under £100: £9.99 delivery fee.
- 🎁 Orders £100+: Free delivery.
- 📦 Delivered in insulated boxes with ice packs.
- ⏱ Orders placed before 9am (Mon-Sun) are delivered next day.
- 🕐 Click & Collect (after 5pm next day if ordered before 1pm).
- 📧 Contact: sales@tariqhalalmeats.com | ☎️ 0208 908 9440

Delivery Schedule:
- Monday before 9am: Arrives Tuesday
- Tuesday before 9am: Arrives Wednesday
- Wednesday before 9am: Arrives Thursday
- Thursday before 9am: Arrives Friday
- Friday before 9am: Arrives Saturday
- Saturday before 9am: Arrives Sunday
- Sunday before 9am: Arrives Monday

Customer Service:
- 💬 Complaints reviewed in 1-2 working days.
- 📩 Email support: info@tariqhalalmeats.com
- 📦 No returns due to perishable nature of goods.

Halal Certification:
- ✅ All products at Tariq Halal Meats are certified Halal by reputable certifying bodies. 

Branches:
- Cardiff: 104-106 Albany Road, CF24 3RT | 02920 485 569 | 9am - 8pm
- Crawley: 33 Queensway, RH10 1EG | 0129 352 2189 | 8am - 7pm
- Croydon: 89 London Road, CR0 2RF | 0208 686 8846 | 9am - 8:30pm
- Finsbury Park: 258 Seven Sisters Road, N4 2HY | 0207 281 5450 | 9am - 8pm
- Forest Gate: 11 Woodgrange Road, E7 8BA | 0208 555 6508 | 8:30 - 8pm
- Fulham: 431 North End Road, SW6 1NY | 0207 381 4252 | 9am - 8pm
- Gerrards Cross: 25 Packhorse Road, SL9 7QA | 0175 3887 271 | 8am - 8pm
- Green Street: 252 Green St, E7 8LF | 0203 649 5332 | 9am - 10pm
- Hammersmith: 120-124 King Street, W6 0QT | 0208 741 6655 | 7am - 11pm
- Hounslow: 9 High Street, TW3 1RH | 0203 302 4330 | 8am - 8pm
- Ilford: 48 Ilford Lane, IG1 2JY | 0208 911 8201 | 8am - 10pm
- Leyton: 794 High Road, E10 6AE | 0208 539 6200 | 8:30am - 8pm
- Slough: 251 Farnham Road, SL2 1DE | 0175 357 1609 | 9am - 8pm
- South Harrow: 387 Northolt Road, HA2 8JD | 0208 423 4975 | 9am - 8pm
- Southall: 126 The Broadway, UB1 1QF | 0203 337 8794 | 9am - 8pm
- St Johns Wood: 10 Lodge Road, NW8 7JA | 0207 483 2938 | 9am - 9pm
- Stratford: Unit 47/48 The Mall, E15 1XE | 0204 506 5693 | 9am - 10pm (Sun 10am - 7pm)
- Streatham: 14 Leighham Parade, SW16 1DR | 0208 664 7045 | 9am - 8pm
- Wealdstone: 14-20 High Street, HA3 7HA | 0208 863 1353 | 7am - 10pm
- High Wycombe: 185 Desborough Road, HP11 2QN | 01494 422 280 | 9am - 8pm (Shop: 9am - 9:30pm)
- Holborn: 183 Drury Lane, WC2B 5QF | 0207 430 9888 | 8am - 8pm (Temp Closed)
- Reading: 477 Oxford Road, RG30 1HF | 0118 956 0664 | 8am - 8pm
- Old Kent Road: 282-286 Old Kent Rd, SE1 5UE | 0203 649 7157 | 8am - 8pm
- Tooting: 147 Upper Tooting Road, SW17 7TJ | 0208 767 9113 | 9am - 8pm
- Wembley: 259 Water Road, HA0 1HX | 0208 908 9440 | 8am - 7pm
- Woolwich: 67 Woolwich New Road, SE18 6ED
"""

# ✅ Generate response from OpenAI
def generate_response(user_input):
    try:
        prompt = f"""
You are a helpful and polite customer service chatbot for Tariq Halal Meat in the UK.
Use the following business information to answer user questions:

{STORE_INFO}

User: {user_input}
"""
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful customer service chatbot for Tariq Halal Meat."},
                {"role": "user", "content": prompt},
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

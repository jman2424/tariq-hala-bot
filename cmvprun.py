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

# Initialize Flask app
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

# ========== COMPLETE PRODUCT CATALOG WITH PRICES ==========
PRODUCT_CATALOG = {
    "POULTRY": {
        "5 Boiler (Hen)": "£19.99",
        "Chicken Drumsticks (Skin Off)": "£6.99",
        "Chicken Strips (1kg)": "£10.99",
        "Chicken Liver (1Kg)": "£5.99",
        "Mid Wings": "£6.99",
        "Chicken Oyster Thighs": "£4.99",
        "Chicken Gizzards (1Kg)": "£5.99",
        "Chicken Hearts (1Kg)": "£5.99",
        "Boiler (Hen)": "£4.99",
        "Chicken Breast": "£9.99",
        "Fire In The Hole Wings (20 pieces)": "£8.99",
        "Chicken Niblets": "£7.99",
        "Prime Wings": "£6.99",
        "Chicken Thigh Mince": "£8.99",
        "Chicken Wings 3 Joint": "£5.99",
        "Chicken Thigh Boneless": "£8.99",
        "Chicken Legs (Skin Off)": "£5.99",
        "Chicken Legs (Skin On)": "£4.99",
        "Chicken Drumsticks (Skin On)": "£5.99",
        "Premium Chicken Mince": "£8.99",
        "Whole Roaster Chicken 1300-1400 Gms": "£7.99",
        "Baby Chicken": "£5.99",
        "Spatch Cock Chicken (1100G)": "£6.99",
        "Chicken Feet (1kg bag)": "£4.99",
        "Tandoori Chicken 1100-1200 Gms": "£6.99",
        "Chicken Sausages in Blankets Party Pack (50pc)": "£16.99",
        "Tariq Halal Traditional Beef Sausages (with hint of pepper) 342g": "£3.99",
        "Halal Frozen Grade A Chicken (800g)": "£3.99 (Out of stock)",
        "Chicken Sausages in Blankets (12pc)": "£4.99",
        "Peri Peri Chicken Liver (1Kg)": "£6.99",
        "Peri Peri Chicken Sausages": "£2.99",
        "Paprika Chicken Cocktail Sausages": "£2.99",
        "Moroccan Lamb Sausages": "£3.99",
        "Chicken Breakfast Sausages": "£2.99",
        "Beef & Black Pepper Cocktail Sausages": "£2.99",
        "Veal Burger": "£2.99",
        "Frozen Halal Whole Turkey": "£34.99",
        "Lamb Burgers (4)": "£6.99",
        "Beef Burgers (4)": "£5.99",
        "Chicken Burgers (4)": "£5.99",
        "Superchick American Style Fillet Burger": "£11.99"
    },
    "LAMB": {
        "Whole Frozen Milk Fed Suckling Lamb Shoulder": "£19.99 (Out of stock)",
        "Whole Frozen Milk Fed Suckling Lamb Leg": "£19.99",
        "Haqeeqa Baby Lamb": "£350.00",
        "Lamb Tripe (Stomach)": "£2.00",
        "Lamb Tongue": "£9.99",
        "Lamb Testicles (Kapoorae)": "£7.99",
        "Lamb Kidneys": "£8.99",
        "Lamb Hearts": "£5.99",
        "Lamb Brain (Per Packet)": "£7.49",
        "Lamb Liver": "£5.99",
        "Lamb Head Without Skin": "£4.99",
        "Mutton Ribs": "£11.99",
        "Mutton Shanks (Niharri)": "£14.99",
        "Mutton Neck": "£11.99",
        "Mutton Back Chops": "£14.99",
        "Mutton Front Chops": "£14.99",
        "Mutton Shoulder": "£14.99",
        "Mutton Leg": "£14.99",
        "Baby Lamb Shoulder For Roasting 1.8-2.0 Kg (whole)": "£39.95",
        "Whole Lamb Leg for Roasting 2.5-2.8 Kg": "£54.95",
        "Baby Lamb French Rack": "£34.95",
        "3Kg Baby Lamb Mince Special": "£39.99",
        "Baby Lamb Leg Mince": "£24.99",
        "Baby Lamb Neck": "£14.99",
        "Baby Lamb Leg Steaks With Bone": "£21.99",
        "Half Baby Lamb (10kg Net Differs)": "£159.99",
        "Mutton Mince Up To 25% Fat": "£9.99",
        "Baby Lamb Mince (25% fat)": "£14.99",
        "Baby Lamb Shanks": "£19.99",
        "Baby Lamb Front Chops": "£23.99",
        "Haqeeqa Sheep": "£350.00",
        "Baby Mixed Lamb": "£19.95",
        "Mixed Mutton": "£12.99",
        "Baby Lamb Ribs": "£14.99",
        "Boneless Mutton": "£16.99",
        "Baby Lamb Back Chops": "£21.99",
        "Baby Lamb Boneless": "£24.99",
        "Baby Lamb Shoulder": "£22.99",
        "Baby Lamb Leg (1kg)": "£22.99",
        "Baby Lamb Leg Steaks Without Bone": "£24.99",
        "Whole Kid Goat (4Kg-5Kg)": "£95.00",
        "Whole Baby Lamb (20kg Net Differs)": "£299.99",
        "Lamb Feet (Paya 1)": "£1.29",
        "Mixed Genuine 100% Goat": "£17.99",
        "Premium Mutton Leg Mince (No Fat)": "£15.99",
        "5Kg Mixed Goat": "£84.95",
        "Half Sheep (15Kg)": "£159.99",
        "Whole Sheep (30Kg)": "£299.99"
    },
    "BEEF": {
        "Whole Fillet Steak Roasting Joint 2.5kg (approx)": "£139.99",
        "Buffalo On the Bone Mixed (1kg)": "£11.99 (Out of stock)",
        "Chilean Wagyu Fillet Steak BMS 6-7 (2 x 150g)": "£79.99",
        "200g Gold Leaf Sirloin": "£12.99",
        "Veal Liver": "£9.99 (Out of stock)",
        "Veal Mince": "£11.99",
        "5 Tariq Halal Beef Sirloin Steak (200 gms each)": "£34.99",
        "Beef Shin On Bone": "£11.99",
        "Beef Topside Steak": "£4.49",
        "Beef Knuckle Steak (3 Steaks)": "£9.99",
        "Beef Mince": "£12.99",
        "Sirloin Steak (whole) Roasting Joint 1kg": "£34.99",
        "Diced Boneless Beef": "£16.99",
        "Beef Short Rib": "£13.99",
        "Beef Oxtail": "£14.99",
        "Fillet Steak (3 Steaks) 600g (3 x 200g)": "£32.99",
        "Bone In Rib-Eye Steak (Each) 350-400g": "£9.99",
        "Boneless Rib-Eye Steak (3 Steaks)": "£22.99",
        "Premium Beef Mince (Ideal For Burgers)": "£15.99",
        "Wagyu Striploin Steak (300g) BMS 8-9": "£69.99",
        "Veal Ossobucu (Shin)": "£14.99 (Out of stock)",
        "Veal Ribeye Steak (3 Steaks)": "£15.99",
        "Beef Marrow Bones 250-300g": "£3.99",
        "Veal Tail": "£12.99",
        "French Trimmed Veal Chop 300-350g": "£9.99",
        "Veal Brain (Whole)": "£5.99 (Out of stock)",
        "Wagyu Tomahawk Steak (BMS 6-7) 1.3-1.5kg": "£99.99 (Out of stock)",
        "Veal T-Bone (Each) 390-410g": "£8.99 (Out of stock)",
        "Cow Foot (Whole)": "£5.99",
        "Veal Topside Steak (3 Steaks) 600g (3 x 200g)": "£15.99",
        "Veal Striploin Steak (3 Steaks)": "£14.99",
        "Veal Fillet Steak (3 Steaks) 600g (3 x 200g)": "£18.99",
        "Diced Boneless Veal": "£19.99",
        "Mixed Veal": "£11.99",
        "T-Bone Steak (300G)": "£9.99",
        "Honeycomb Tripe (Beef)": "£7.99",
        "Tariq Halal Beef Roasting Joint 1kg": "£19.99",
        "Angus Beef Fillet Steak (180-200g)": "£14.99",
        "Angus Sirloin Steak (200-220g)": "£11.99",
        "Angus Boneless Ribeye Steak (200-220g)": "£12.99",
        "Premium Wagyu Beef Bundle Special": "£149.99 (Out of stock)",
        "Santa Rosalia Wagyu Gold Burger (100g x 2)": "£9.99",
        "Santa Rosalia Wagyu Topside Steak (275g)": "£14.99",
        "Santa Rosalia Wagyu Flat Iron Steak (200g)": "£14.99",
        "Santa Rosalia Wagyu Fillet (150g)": "£24.99",
        "Santa Rosalia Wagyu Ribeye (225g)": "£39.99 (Out of stock)",
        "Santa Rosalia Wagyu Striploin (325g)": "£59.99",
        "Dry Aged Ribeye Boneless Steak (av 300g +)": "£12.99 (Out of stock)",
        "Premium Dry Aged Beef Burgers (2 x 180g)": "£7.99 (Out of stock)",
        "Dry Aged Boneless Brisket (280g +)": "£7.99 (Out of stock)",
        "Dry Aged Rump Steak (av 350g)": "£8.99 (Out of stock)",
        "Dry Aged Fillet Steak (av 240g +)": "£10.99 (Out of stock)",
        "Dry Aged Sirloin Steak (290g +)": "£12.99 (Out of stock)",
        "Dry Aged Beef Short Rib (av 350g +)": "£7.99 (Out of stock)",
        "Mollendo Wagyu Striploin Steak Bms 6-7 300g": "£34.99",
        "Beef Topside Strips 1kg": "£17.99",
        "Veal Premium Bacon Pre Sliced (650G)": "£16.99 (Out of stock)"
    },
    "GROCERIES": {
        "Basmati Rice 5kg": "£8.99",
        "Chickpeas 2kg": "£2.99",
        "Lentils 2kg": "£3.49",
        "Cumin Seeds 100g": "£1.50",
        "Turmeric Powder 100g": "£1.00",
        "Garam Masala 100g": "£1.25",
        "Peri Peri Sauce 250ml": "£2.00",
        "Mint Sauce 250ml": "£1.75",
        "Yogurt Sauce 250ml": "£1.50",
        "BBQ Sauce 250ml": "£1.80",
        "Chilli Sauce 250ml": "£1.60",
        "Chapatti Flour 10kg": "£7.50",
        "Plain Naan (2 pieces)": "£1.00",
        "Garlic Naan (2 pieces)": "£1.20",
        "Mango Juice 1L": "£1.50",
        "Pineapple Juice 1L": "£1.50",
        "Mocktail Mojito 330ml": "£1.00",
        "Strawberry Mocktail 330ml": "£1.00",
        "Lychee Drink 330ml": "£1.00",
        "Loose Black Tea 250g": "£2.75",
        "Instant Coffee 200g": "£3.50",
        "Sunflower Oil 1L": "£2.99",
        "Vegetable Oil 1L": "£2.75",
        "Desi Ghee 500g": "£4.50",
        "Toilet Roll 9 Pack": "£3.99",
        "Kitchen Roll 2 Pack": "£2.50",
        "Bin Bags 20pcs": "£1.99",
        "Tandoori Roti (5 pieces)": "£1.20",
        "Sweet Buns Pack": "£1.50"
    },
    "FROZEN MEATS": {
        "Halal Frozen Grade A Chicken (800g)": "£3.99",
        "Frozen Halal Whole Turkey": "£34.99 (CANNOT BE PREORDERED)",
        "Halal Frozen Whole Duck (2.8-3.0kg)": "£24.99",
        "Frozen Halal Duck Legs (2 pieces)": "£9.99",
        "Frozen Halal Duck Breast (1 Piece)": "£8.99",
        "Frozen Halal Duck Feet (1kg)": "£4.99",
        "Frozen Halal Rabbit (whole)": "£19.99",
        "Frozen Halal Quails (4)": "£8.99",
        "Frozen Halal Pigeon": "£14.99 (Out of stock)",
        "Frozen Halal Buffalo Meat (1kg)": "£11.99 (Out of stock)"
    },
    "EXOTIC MEATS": {
        "Whole Frozen Milk Fed Suckling Lamb Shoulder": "£19.99 (Out of stock)",
        "Whole Frozen Milk Fed Suckling Lamb Leg": "£19.99",
        "Whole Kid Goat (4Kg-5Kg)": "£95.00",
        "Whole Baby Lamb (20kg Net Differs)": "£299.99",
        "Haqeeqa Baby Lamb": "£350.00",
        "Haqeeqa Sheep": "£350.00",
        "Lamb Testicles (Kapoorae)": "£7.99",
        "Lamb Brain (Per Packet)": "£7.49",
        "Lamb Feet (Paya)": "£1.29",
        "Lamb Tripe (Stomach)": "£2.00",
        "Lamb Tongue": "£9.99",
        "Lamb Head Without Skin": "£4.99",
        "Veal Tail": "£12.99",
        "Veal Brain (Whole)": "£5.99 (Out of stock)",
        "Veal T-Bone (390-410g)": "£8.99 (Out of stock)",
        "Cow Foot (Whole)": "£5.99",
        "Beef Marrow Bones (250-300g)": "£3.99",
        "Honeycomb Tripe (Beef)": "£7.99",
        "Chicken Feet (1kg bag)": "£4.99",
        "Chicken Gizzards (1Kg)": "£5.99",
        "Chicken Hearts (1Kg)": "£5.99",
        "Chicken Liver (1Kg)": "£5.99"
    },
    "MARINATED MEATS": {
        "CHICKEN": {
            "Truffle Chicken Cubes (1kg)": "£9.99",
            "Mumtaz Lemon Pepper & Herb Wings (1kg)": "£8.99",
            "Dragons Fire Chicken Niblets": "£8.99",
            "Mumtaz Peri Peri Wings 1kg": "£8.99",
            "Mumtaz Chicken Tikka Cubes 1kg": "£9.99",
            "CHICKEN SHAWARMA": "£9.99",
            "MARINATED DRUMSTICKS": "£5.99",
            "JERK CHICKEN LEGS": "£5.99",
            "LEMON & CHILLI Chicken Fillets": "£9.99",
            "MARINATED CHICKEN CUBES": "£9.99",
            "Marinated Baby Chicken": "£6.49",
            "Exotic Mango & Chilli Drumsticks": "£5.99",
            "Fire In The Hole Wings (20 pieces)": "£8.99",
            "PERI PERI Wings": "£7.99",
            "FIRE IN THE HOLE MEAT BOX": "£39.99",
            "Greek Chicken Gyros (kebab)": "£5.99",
            "Spicy Mexican Fajita Chicken Strips": "£9.99",
            "Italian Green Pesto Chicken": "£9.99"
        },
        "LAMB": {
            "Truffle Lamb Chops (1kg)": "£24.99",
            "Mumtaz Sticky BBQ Lamb Ribs 1kg": "£11.99",
            "Mumtaz Lamb Chops 1kg": "£24.99",
            "MARINATED LAMB RIBS": "£11.99",
            "LAMB SHAWARMA": "£19.99",
            "Greek Lamb Gyros (kebab)": "£10.99",
            "Hot & Spicy Lamb Chops": "£24.99"
        },
        "BEEF": {
            "MARINATED BEEF T-BONE": "£11.99",
            "Marinated Sirloin Steak": "£9.99",
            "Fire In The Hole Beef Ribs": "£14.99"
        },
        "COMBOS": {
            "COMBO - Greek Chicken & Lamb Gyros (kebab) 1kg": "£12.99"
        }
    }
}

# ========== COMPLETE STORE INFORMATION ==========
STORE_INFO = """
Tariq Halal Meats Delivery Info:

❌ No delivery to Isle of Man, Isle of Wight, Jersey.

✅ Mainland UK delivery 7 days a week.

🚚 Orders under £100: £9.99 delivery fee.

🎁 Orders £100+: Free delivery.

📦 Delivered in insulated boxes with ice packs.

⏱ Orders placed before 9am (Mon-Sun) are delivered next day.

🕐 Click & Collect (after 5pm next day if ordered before 1pm).

📧 Contact: sales@tariqhalalmeats.com | ☎️ 0208 908 9440

Delivery Schedule:
Monday before 9am: Arrives Tuesday
Tuesday before 9am: Arrives Wednesday
Wednesday before 9am: Arrives Thursday
Thursday before 9am: Arrives Friday
Friday before 9am: Arrives Saturday
Saturday before 9am: Arrives Sunday
Sunday before 9am: Arrives Monday

Customer Service:
💬 Complaints reviewed in 1-2 working days.
📩 Email support: info@tariqhalalmeats.com
📦 No returns due to perishable nature of goods.

Halal Certification:
✅ All products certified Halal by reputable bodies.

Branches:
Cardiff: 104-106 Albany Road, CF24 3RT | 02920 485 569
Crawley: 33 Queensway, RH10 1EG | 01293 522189
Croydon: 89 London Road, CR0 2RF | 0208 686 8846
Finsbury Park: 258 Seven Sisters Road, N4 2HY | 0207 281 5450
Forest Gate: 11 Woodgrange Road, E7 8BA | 0208 555 6508
Fulham: 431 North End Road, SW6 1NY | 0207 381 4252
Green Street: 252 Green St, E7 8LF | 0203 649 5332
Hammersmith: 120-124 King Street, W6 0QT | 0208 741 6655
Hounslow: 9 High Street, TW3 1RH | 0203 302 4330
Ilford: 48 Ilford Lane, IG1 2JY | 0208 911 8201
Leyton: 794 High Road, E10 6AE | 0208 539 6200
Slough: 251 Farnham Road, SL2 1DE | 01753 571609
South Harrow: 387 Northolt Road, HA2 8JD | 0208 423 4975
Southall: 126 The Broadway, UB1 1QF | 0203 337 8794
St Johns Wood: 10 Lodge Road, NW8 7JA | 0207 483 2938
Stratford: Unit 47/48 The Mall, E15 1XE | 0204 506 5693
Streatham: 14 Leighham Parade, SW16 1DR | 0208 664 7045
Wealdstone: 14-20 High Street, HA3 7HA | 0208 863 1353
Wembley: 259 Water Road, HA0 1HX | 0208 908 9440
"""

# ========== HELPER FUNCTIONS ==========
def find_products(search_term):
    """Search products in catalog with case-insensitive matching"""
    search_term = search_term.lower().strip()
    results = {}
    
    for category, products in PRODUCT_CATALOG.items():
        matched_products = []
        
        # Handle marinated meats subcategories
        if isinstance(products, dict) and category == "MARINATED MEATS":
            for subcategory, sub_products in products.items():
                for product, price in sub_products.items():
                    if search_term in product.lower():
                        matched_products.append((f"{subcategory} - {product}", price))
        # Handle regular categories
        else:
            for product, price in products.items():
                if search_term in product.lower():
                    matched_products.append((product, price))
        
        if matched_products:
            results[category] = matched_products
            
    return results

def generate_ai_response(user_query):
    """Generate response using OpenAI with business context"""
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
                    "content": f"Business Info:\n{STORE_INFO}\n\nProduct Catalog:\n{str(PRODUCT_CATALOG)}\n\nCustomer Question: {user_query}"
                }
            ],
            temperature=0.3,
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"AI Error: {str(e)}")
        return None

# ========== ROUTES ==========
@app.route("/whatsapp", methods=["POST"])
@limiter.limit("5 per minute")
@cache.cached(timeout=300, query_string=True)
def handle_whatsapp_message():
    """Process incoming WhatsApp messages"""
    try:
        # Validate Twilio signature
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        if not validator.validate(
            request.url,
            request.form,
            request.headers.get('X-Twilio-Signature', '')
        ):
            logger.warning("Invalid Twilio signature")
            return "Unauthorized", 403

        # Get and validate message
        incoming_msg = request.values.get('Body', '').strip().lower()
        if not incoming_msg:
            return "Empty message", 400

        logger.info(f"Received message: {incoming_msg}")

        # Initialize response
        resp = MessagingResponse()
        
        # Handle specific commands
        if incoming_msg in ['hi', 'hello', 'hey']:
            reply = ("🕌 Welcome to Tariq Halal Meats!\n\n"
                    "You can ask about:\n"
                    "- Products & prices 🛒\n"
                    "- Delivery info 🚚\n"
                    "- Store locations 🏪\n"
                    "- Or ask any question!")
        elif incoming_msg in ['menu', 'products', 'catalog']:
            reply = ("📋 Our Product Categories:\n\n"
                    "1. POULTRY 🐔\n"
                    "2. LAMB 🐑\n"
                    "3. BEEF 🐄\n"
                    "4. GROCERIES 🛒\n"
                    "5. FROZEN MEATS ❄️\n"
                    "6. EXOTIC MEATS\n"
                    "7. MARINATED MEATS\n\n"
                    "Reply with a category name or product name for details!")
        elif 'delivery' in incoming_msg:
            reply = ("🚚 Delivery Information:\n\n"
                    "• Mainland UK delivery 7 days/week\n"
                    "• £9.99 delivery for orders under £100\n"
                    "• FREE delivery for orders £100+\n"
                    "• Next day delivery for orders before 9am\n"
                    "• Click & Collect available after 5pm next day")
        elif 'contact' in incoming_msg or 'phone' in incoming_msg:
            reply = ("📞 Contact Us:\n"
                    "Phone: 0208 908 9440\n"
                    "Email: sales@tariqhalalmeats.com\n"
                    "Hours: Mon-Sun 9am-9pm")
        elif 'branches' in incoming_msg or 'locations' in incoming_msg:
            reply = ("🏪 Our Branches:\n\n"
                    "• Cardiff: 104-106 Albany Road\n"
                    "• Crawley: 33 Queensway\n"
                    "• Croydon: 89 London Road\n"
                    "• Finsbury Park: 258 Seven Sisters Road\n"
                    "• And 15+ more locations across UK\n\n"
                    "Full list at tariqhalalmeats.com")
        else:
            # 1. First try to find matching products
            product_results = find_products(incoming_msg)
            if product_results:
                response = ["🔎 We found these matching products:"]
                for category, items in product_results.items():
                    response.append(f"\n*{category}*")
                    response.extend(f"- {name}: {price}" for name, price in items)
                response.append("\nNeed anything else?")
                reply = "\n".join(response)
            # 2. Fall back to AI for general questions
            else:
                ai_response = generate_ai_response(incoming_msg)
                reply = ai_response if ai_response else (
                    "Sorry, I couldn't find information about that.\n"
                    "Please call ☎️ 0208 908 9440 for assistance."
                )

        # Send response
        logger.info(f"Sending response: {reply[:100]}...")
        resp.message(reply)
        return str(resp)

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        traceback.print_exc()
        return "Server Error", 500

@app.route("/whatsapp/status", methods=["POST"])
def handle_status_update():
    """Handle message delivery status updates"""
    status = request.values.get('MessageStatus', '')
    message_sid = request.values.get('MessageSid', '')
    logger.info(f"Message status update - SID: {message_sid}, Status: {status}")
    return "OK", 200

@app.route("/health")
def health_check():
    """Health check endpoint for monitoring"""
    return jsonify({
        "status": "operational",
        "services": {
            "openai": bool(client.api_key),
            "twilio": bool(TWILIO_AUTH_TOKEN)
        }
    })

@app.route("/")
def home():
    """Simple root endpoint"""
    return "🟢 Tariq Halal Meats WhatsApp Bot is Online"

# ========== RUN APPLICATION ==========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.getenv('DEBUG', 'false').lower() == 'true'
    )

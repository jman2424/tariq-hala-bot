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

        logger.info(f"Received raw message: '{request.values.get('Body', '')}'")
        logger.info(f"Processed message (lowercase): '{incoming_msg}'")

        # Initialize response
        resp = MessagingResponse()
        
        # Debug: Log the type of message we're processing
        logger.info(f"Processing message type: {type(incoming_msg)}")
        
        # Handle specific commands
        if any(greeting in incoming_msg for greeting in ['hi', 'hello', 'hey']):
            reply = ("🕌 Welcome to Tariq Halal Meats!\n\n"
                    "You can ask about:\n"
                    "- Products & prices 🛒\n"
                    "- Delivery info 🚚\n"
                    "- Store locations 🏪\n"
                    "- Or ask any question!")
            logger.info("Responding to greeting")
            
        elif any(cmd in incoming_msg for cmd in ['menu', 'products', 'catalog']):
            reply = ("📋 Our Product Categories:\n\n"
                    "1. POULTRY 🐔\n"
                    "2. LAMB 🐑\n"
                    "3. BEEF 🐄\n"
                    "4. GROCERIES 🛒\n"
                    "5. FROZEN MEATS ❄️\n"
                    "6. EXOTIC MEATS\n"
                    "7. MARINATED MEATS\n\n"
                    "Reply with a category name or product name for details!")
            logger.info("Responding to menu request")
            
        elif 'delivery' in incoming_msg:
            reply = ("🚚 Delivery Information:\n\n"
                    "• Mainland UK delivery 7 days/week\n"
                    "• £9.99 delivery for orders under £100\n"
                    "• FREE delivery for orders £100+\n"
                    "• Next day delivery for orders before 9am\n"
                    "• Click & Collect available after 5pm next day")
            logger.info("Responding to delivery inquiry")
            
        elif 'contact' in incoming_msg or 'phone' in incoming_msg:
            reply = ("📞 Contact Us:\n"
                    "Phone: 0208 908 9440\n"
                    "Email: sales@tariqhalalmeats.com\n"
                    "Hours: Mon-Sun 9am-9pm")
            logger.info("Responding to contact request")
            
        elif 'branches' in incoming_msg or 'locations' in incoming_msg:
            reply = ("🏪 Our Branches:\n\n"
                    "• Cardiff: 104-106 Albany Road\n"
                    "• Crawley: 33 Queensway\n"
                    "• Croydon: 89 London Road\n"
                    "• Finsbury Park: 258 Seven Sisters Road\n"
                    "• And 15+ more locations across UK\n\n"
                    "Full list at tariqhalalmeats.com")
            logger.info("Responding to branches request")
            
        else:
            # 1. First try to find matching products
            logger.info("Attempting product search")
            product_results = find_products(incoming_msg)
            
            if product_results:
                logger.info(f"Found {sum(len(v) for v in product_results.values())} matching products")
                response = ["🔎 We found these matching products:"]
                for category, items in product_results.items():
                    response.append(f"\n*{category}*")
                    response.extend(f"- {name}: {price}" for name, price in items)
                response.append("\nNeed anything else?")
                reply = "\n".join(response)
            else:
                # 2. Fall back to AI for general questions
                logger.info("No products found, trying AI response")
                ai_response = generate_ai_response(incoming_msg)
                if ai_response:
                    logger.info("AI response generated successfully")
                    reply = ai_response
                else:
                    logger.warning("AI response failed")
                    reply = ("Sorry, I couldn't find information about that.\n"
                            "Please call ☎️ 0208 908 9440 for assistance.")

        # Send response
        logger.info(f"Sending response (first 100 chars): {reply[:100]}...")
        resp.message(reply)
        return str(resp)

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        traceback.print_exc()
        return "Server Error", 500

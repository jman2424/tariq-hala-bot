from store_info import STORE_INFO
from product_catalog import PRODUCT_CATALOG

def main():
    print("🤖 Welcome to Tariq Halal Meat Store Chatbot!")
    print("Type a question or 'exit' to quit.\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() == 'exit':
            print("Chatbot: Goodbye! 👋")
            break

        if "delivery" in user_input.lower():
            print("Chatbot:", STORE_INFO.get("delivery_policy", "Delivery policy not found."))
        elif "location" in user_input.lower() or "address" in user_input.lower():
            print("Chatbot:", STORE_INFO.get("locations", "Store locations not found."))
        elif "product" in user_input.lower() or "price" in user_input.lower():
            print("Chatbot: Here are some example products and prices:")
            for product in list(PRODUCT_CATALOG)[:5]:  # show first 5 products
                print("-", product)
        else:
            print("Chatbot: Sorry, I didn't understand that. Try asking about delivery, products, or store info.")

if __name__ == "__main__":
    main()

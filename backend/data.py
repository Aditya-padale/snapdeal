from datetime import date, timedelta

SELLERS = [
    {
        "id": "SEL-10482", "name": "Aarav Threads", "category": "Fashion & Apparel", "location": "Jaipur, Rajasthan",
        "revenue": 184260, "orders": 196, "impressions": 148200, "views": 11840, "ctr": 7.99,
        "conversion": 1.66, "aov": 940.10, "cancellation": 2.4, "returns": 8.1,
        "rating": 4.2, "inventory_value": 286, "synthetic": True,
        "products": [
            {"id": "KURTA-01", "name": "Indigo Block Print Kurta", "price": 949, "previous_price": 999, "competitor_price": 899, "conversion": 1.72, "previous_conversion": 3.42, "inventory": 12, "velocity": 3.1, "rating": 4.3, "views": 6210, "orders": 107, "margin": 31},
            {"id": "DRESS-02", "name": "Cotton Ajrakh Midi Dress", "price": 1299, "previous_price": 1299, "competitor_price": 1249, "conversion": 1.55, "previous_conversion": 2.10, "inventory": 48, "velocity": 1.2, "rating": 4.1, "views": 3220, "orders": 50, "margin": 34},
            {"id": "SHIRT-03", "name": "Relaxed Linen Shirt", "price": 799, "previous_price": 799, "competitor_price": 849, "conversion": 2.05, "previous_conversion": 2.00, "inventory": 86, "velocity": 0.8, "rating": 4.4, "views": 2410, "orders": 39, "margin": 28},
        ]
    },
    {
        "id": "SEL-22017", "name": "Mitti Home", "category": "Home & Living", "location": "Pune, Maharashtra",
        "revenue": 132480, "orders": 143, "impressions": 102500, "views": 8040, "ctr": 7.84,
        "conversion": 1.78, "aov": 926.43, "cancellation": 1.7, "returns": 5.2,
        "rating": 4.5, "inventory_value": 412, "synthetic": True,
        "products": [
            {"id": "LAMP-01", "name": "Hand-thrown Terracotta Lamp", "price": 699, "previous_price": 699, "competitor_price": 749, "conversion": 2.7, "previous_conversion": 2.5, "inventory": 74, "velocity": 1.4, "rating": 4.6, "views": 2820, "orders": 76, "margin": 38},
            {"id": "RUG-02", "name": "Handwoven Cotton Runner", "price": 1099, "previous_price": 1149, "competitor_price": 999, "conversion": 1.2, "previous_conversion": 1.8, "inventory": 19, "velocity": 2.0, "rating": 4.3, "views": 2140, "orders": 38, "margin": 29},
        ]
    },
    {
        "id": "SEL-30991", "name": "Nimble Kitchen", "category": "Kitchen & Dining", "location": "Bengaluru, Karnataka",
        "revenue": 96420, "orders": 124, "impressions": 88200, "views": 7160, "ctr": 8.12,
        "conversion": 1.73, "aov": 777.58, "cancellation": 3.2, "returns": 6.4,
        "rating": 4.0, "inventory_value": 168, "synthetic": True,
        "products": [
            {"id": "PAN-01", "name": "Cast Iron Breakfast Pan", "price": 849, "previous_price": 849, "competitor_price": 799, "conversion": 2.1, "previous_conversion": 2.4, "inventory": 9, "velocity": 2.4, "rating": 4.1, "views": 3010, "orders": 63, "margin": 25},
            {"id": "JAR-02", "name": "Glass Spice Jar Set", "price": 499, "previous_price": 499, "competitor_price": 529, "conversion": 1.4, "previous_conversion": 1.3, "inventory": 55, "velocity": 1.0, "rating": 4.2, "views": 1980, "orders": 28, "margin": 32},
        ]
    }
]


def get_seller(seller_id: str):
    return next((seller for seller in SELLERS if seller["id"] == seller_id), None)


def trend_for(seller: dict):
    values = [round(seller["revenue"] / 14 * (0.72 + i * 0.024 + (i % 3) * 0.015)) for i in range(14)]
    return [{"day": (date.today() - timedelta(days=13 - i)).strftime("%b %d"), "revenue": value} for i, value in enumerate(values)]

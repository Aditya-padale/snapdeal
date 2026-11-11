from .data import trend_for


def analytics_for(seller: dict):
    trend = trend_for(seller)
    first_week = sum(point["revenue"] for point in trend[:7])
    second_week = sum(point["revenue"] for point in trend[7:])
    sales_change = round((second_week - first_week) / first_week * 100, 1)
    products = seller["products"]
    avg_competitor_gap = round(sum((p["price"] - p["competitor_price"]) / p["price"] * 100 for p in products) / len(products), 1)
    conversion_change = round(seller["conversion"] - seller["products"][0]["previous_conversion"], 2)
    current_price = sum(p["price"] for p in products) / len(products)
    previous_price = sum(p.get("previous_price", p["price"]) for p in products) / len(products)
    aov_change = round((current_price - previous_price) / previous_price * 100, 1) if previous_price else 0
    return {"seller": seller, "trend": trend, "sales_change": sales_change, "avg_competitor_gap": avg_competitor_gap,
            "changes": {"revenue": sales_change, "orders": sales_change, "conversion": conversion_change, "aov": aov_change},
            "observations": {"impressions_stable": True, "conversion_decline": round(seller["products"][0]["previous_conversion"] - seller["products"][0]["conversion"], 2), "top_product": products[0]["name"]}}


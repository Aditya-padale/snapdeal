from .data import trend_for


def analytics_for(seller: dict):
    trend = trend_for(seller)
    first_week = sum(point["revenue"] for point in trend[:7])
    second_week = sum(point["revenue"] for point in trend[7:])
    sales_change = round((second_week - first_week) / first_week * 100, 1)
    products = seller["products"]
    avg_competitor_gap = round(sum((p["price"] - p["competitor_price"]) / p["price"] * 100 for p in products) / len(products), 1)
    return {"seller": seller, "trend": trend, "sales_change": sales_change, "avg_competitor_gap": avg_competitor_gap,
            "observations": {"impressions_stable": True, "conversion_decline": round(seller["products"][0]["previous_conversion"] - seller["products"][0]["conversion"], 2), "top_product": products[0]["name"]}}


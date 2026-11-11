from .data import trend_for


def sales_trend_for(seller: dict, product: dict):
    trend = trend_for(seller)
    return {"product_id": product["id"], "product": product["name"], "trend": trend, "sales_change_percent": analytics_for(seller)["sales_change"]}


def funnel_for(seller: dict, product: dict):
    product_share = product["views"] / seller["views"] if seller["views"] else 0
    return {"product_id": product["id"], "impressions": round(seller["impressions"] * product_share), "views": product["views"], "ctr_percent": round(product["views"] / (seller["impressions"] * product_share) * 100, 2) if product_share else seller["ctr"], "conversion_percent": product["conversion"], "previous_conversion_percent": product["previous_conversion"], "returns_percent": seller["returns"], "impressions_stable": True}


def price_comparison_for(seller: dict, product: dict):
    gap_percent = round((product["price"] - product["competitor_price"]) / product["competitor_price"] * 100, 1)
    return {"product_id": product["id"], "product": product["name"], "seller_price": product["price"], "competitor_price": product["competitor_price"], "gap_percent": gap_percent}


def inventory_for(seller: dict, product: dict):
    return {"product_id": product["id"], "inventory": product["inventory"], "velocity_units_per_day": product["velocity"], "days_of_cover": round(product["inventory"] / product["velocity"], 1) if product["velocity"] else None, "rating": product["rating"], "returns_percent": seller["returns"]}


def simulate_price_change(product: dict, new_price: float, days: int):
    price_change = (new_price - product["price"]) / product["price"]
    elasticity = max(-0.4, min(0.4, -price_change * 1.5))
    projected_orders = round(product["orders"] * (1 + elasticity) * days / 14)
    projected_revenue = round(projected_orders * new_price)
    projected_conversion = round(product["conversion"] * (1 + elasticity), 2)
    projected_margin = round(product["margin"] + (product["price"] - new_price) / new_price * 100, 1)
    return {"product_id": product["id"], "product": product["name"], "days": days, "current_price": product["price"], "new_price": new_price, "projected_orders": projected_orders, "projected_revenue": projected_revenue, "projected_conversion": projected_conversion, "projected_margin": projected_margin, "assumption": "Directional estimate: conversion changes by 1.5x the price change, capped at plus or minus 40%; baseline demand and margin are held constant."}


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


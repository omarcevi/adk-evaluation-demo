"""ShopHelper: an order support agent for a fictional online store."""

import time
from datetime import date, timedelta
from typing import Literal

from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import types

# Gemini 3 models are served from the "global" endpoint, so pin it here
# (Agent Runtime itself runs in a region, e.g. us-central1).
# Retries smooth over temporary 429 "resource exhausted" errors.
MODEL = Gemini(
    model="gemini-3.8-flash",
    client_kwargs={"location": "global"},
    retry_options=types.HttpRetryOptions(initial_delay=1, attempts=3),
)
RETURN_WINDOW_DAYS = 30
NON_RETURNABLE_ITEMS = {"Gift card", "Opened earbuds"}


def _order(status: str, items: list[str], ordered_days_ago: int, eta: str = "") -> dict:
    # Order dates are relative to today, so the 30-day return window works on any day.
    order_date = date.today() - timedelta(days=ordered_days_ago)
    return {"status": status, "items": items, "order_date": order_date.isoformat(), "eta": eta}


# In-memory mock data. A real agent would call your order system here.
ORDERS = {
    "ORD-1001": _order("delivered", ["Ceramic coffee mug"], ordered_days_ago=12),
    "ORD-1002": _order("shipped", ["Wireless headphones"], ordered_days_ago=3, eta="2-3 business days"),
    "ORD-1003": _order("processing", ["Running shoes"], ordered_days_ago=1, eta="5-7 business days"),
    "ORD-1004": _order("delivered", ["Denim jacket"], ordered_days_ago=45),  # too old to return
    "ORD-1005": _order("delivered", ["Gift card", "Birthday card"], ordered_days_ago=6),
    "ORD-1006": _order("delivered", ["Yoga mat", "Water bottle"], ordered_days_ago=20),
    "ORD-1007": _order("shipped", ["Desk lamp"], ordered_days_ago=2, eta="1-2 business days"),
    "ORD-1008": _order("delivered", ["Phone case", "Opened earbuds"], ordered_days_ago=8),
}


def _clean_order_id(order_id: str) -> str:
    return order_id.strip()


def _not_found(order_id: str) -> dict:
    # Returning a dict with an "error" key marks the tool span as an error in traces.
    return {"error": f"Order {order_id} not found."}


def get_order_status(order_id: str) -> dict:
    """Looks up the status, items and order date of an order.

    Args:
        order_id: The customer's order ID.
    """
    order_id = _clean_order_id(order_id)
    order = ORDERS.get(order_id)
    if order is None:
        return _not_found(order_id)
    return {
        "order_id": order_id,
        "status": order["status"],
        "items": order["items"],
        "order_date": order["order_date"],
    }


def check_return_eligibility(order_id: str) -> dict:
    """Checks whether an order can be returned, and why.

    Args:
        order_id: The customer's order ID.
    """
    order_id = _clean_order_id(order_id)
    order = ORDERS.get(order_id)
    if order is None:
        return _not_found(order_id)
    if order["status"] != "delivered":
        return {"eligible": False, "reason": "The order has not been delivered yet."}
    days_since_order = (date.today() - date.fromisoformat(order["order_date"])).days
    if days_since_order > RETURN_WINDOW_DAYS:
        return {"eligible": False, "reason": f"The order is outside the {RETURN_WINDOW_DAYS}-day return window."}
    blocked = [item for item in order["items"] if item in NON_RETURNABLE_ITEMS]
    if blocked:
        return {"eligible": False, "reason": f"These items cannot be returned: {', '.join(blocked)}."}
    return {"eligible": True, "reason": "The order is within the return window."}


def create_return_request(
    order_id: str,
    reason: Literal["damaged", "wrong_item", "does_not_fit", "changed_mind", "other"],
) -> dict:
    """Creates a return request for an order and returns the return ID.

    Args:
        order_id: The customer's order ID.
        reason: Why the customer is returning the order.
    """
    order_id = _clean_order_id(order_id)
    if order_id not in ORDERS:
        return _not_found(order_id)
    return {"return_id": "RET-" + order_id.removeprefix("ORD-"), "order_id": order_id, "reason": reason}


def get_shipping_eta(order_id: str) -> dict:
    """Gets the estimated delivery time of an order.

    Args:
        order_id: The customer's order ID.
    """
    time.sleep(2.5)  # Simulates a slow carrier API, so it stands out in Cloud Trace.
    order_id = _clean_order_id(order_id)
    order = ORDERS.get(order_id)
    if order is None:
        return _not_found(order_id)
    if order["status"] == "delivered":
        return {"order_id": order_id, "eta": "already delivered"}
    return {"order_id": order_id, "eta": order["eta"]}


INSTRUCTION = """You are ShopHelper, the customer support agent of an online store.
You help customers with their orders: order status, returns and shipping ETAs.

- To answer questions about an order, call get_order_status.
- When a customer asks when an order will arrive, call get_shipping_eta.
- When a customer wants to return an order, ALWAYS call check_return_eligibility first.
  Only if the order is eligible, call create_return_request with the order ID and the reason.
- Only state facts that come from your tools. Never make up order details.
- If the request is not about an order, politely say that you can only help with orders.
- Keep answers short and friendly.
- Always reply in the same language the customer writes in.
"""

root_agent = LlmAgent(
    name="shop_helper",
    model=MODEL,
    description="Order support agent for an online store.",
    instruction=INSTRUCTION,
    tools=[get_order_status, check_return_eligibility, create_return_request, get_shipping_eta],
)

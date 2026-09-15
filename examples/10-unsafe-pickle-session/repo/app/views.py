"""Storefront routes."""

from flask import Blueprint, jsonify, make_response, request

from .cart import Cart
from .session import decode, encode

bp = Blueprint("store", __name__)

SESSION_COOKIE = "sess"


def current_session() -> dict:
    return decode(request.cookies.get(SESSION_COOKIE, ""))


@bp.get("/cart")
def view_cart():
    session = current_session()
    return jsonify(Cart.from_session(session).to_json())


@bp.post("/cart/items")
def add_item():
    session = current_session()
    cart = Cart.from_session(session)
    cart.add(request.json["sku"], int(request.json.get("qty", 1)))

    response = make_response(jsonify(cart.to_json()))
    response.set_cookie(SESSION_COOKIE, encode(cart.to_session()), httponly=True)
    return response

"""HTTP routes."""

from flask import Blueprint, abort, request

from .webhooks import verify

bp = Blueprint("api", __name__)


@bp.post("/webhooks/billing")
def billing_webhook():
    signature = request.headers.get("x-signature", "")
    if not verify(request.get_data(), signature):
        abort(401)
    return {"ok": True}

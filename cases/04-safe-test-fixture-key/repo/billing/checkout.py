"""Checkout flow."""

from dataclasses import dataclass

from .gateway import Gateway


class CardDeclined(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Receipt:
    amount_cents: int
    status: str


def charge(gateway: Gateway, card: str, amount_cents: int) -> Receipt:
    response = gateway_charge(gateway, card, amount_cents)
    if response["status"] == "declined":
        raise CardDeclined(response["code"])
    return Receipt(amount_cents=amount_cents, status=response["status"])


def gateway_charge(gateway: Gateway, card: str, amount_cents: int) -> dict:
    raise NotImplementedError("wired up in billing.transport")

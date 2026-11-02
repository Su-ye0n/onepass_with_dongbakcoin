
# onepass/p1_payment_p0.py

"""P1 payment context for the three supported payment lanes.

This module does not execute a payment or calculate benefits.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PaymentLane(str, Enum):
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"
    SIMPLE_PAY = "SIMPLE_PAY"


class SalesChannel(str, Enum):
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"


class PaymentProvider(str, Enum):
    NAVERPAY = "NAVERPAY"
    KAKAOPAY = "KAKAOPAY"
    SAMSUNGPAY = "SAMSUNGPAY"


class P1PaymentError(ValueError):
    pass


@dataclass(frozen=True)
class PaymentContext:
    lane: PaymentLane
    sales_channel: SalesChannel
    payment_provider: PaymentProvider | None = None
    is_autopay: bool = False

    def __post_init__(self):
        # Explicitly reject strings such as "QR" or "DONGBAEK_QR".
        try:
            lane = PaymentLane(self.lane)
            channel = SalesChannel(self.sales_channel)
        except (ValueError, TypeError) as exc:
            raise P1PaymentError(
                "UNSUPPORTED_PAYMENT_LANE_OR_CHANNEL"
            ) from exc

        provider = None
        if self.payment_provider is not None:
            try:
                provider = PaymentProvider(
                    self.payment_provider
                )
            except (ValueError, TypeError) as exc:
                raise P1PaymentError(
                    "UNSUPPORTED_PAYMENT_PROVIDER"
                ) from exc

        if lane == PaymentLane.OFFLINE:
            if channel != SalesChannel.OFFLINE:
                raise P1PaymentError(
                    "OFFLINE_LANE_CHANNEL_MISMATCH"
                )

        elif lane == PaymentLane.ONLINE:
            if channel != SalesChannel.ONLINE:
                raise P1PaymentError(
                    "ONLINE_LANE_CHANNEL_MISMATCH"
                )

        if lane != PaymentLane.SIMPLE_PAY:
            if provider is not None:
                raise P1PaymentError(
                    "PROVIDER_REQUIRES_SIMPLE_PAY"
                )
        elif provider is None:
            raise P1PaymentError(
                "SIMPLE_PAY_PROVIDER_REQUIRED"
            )

        if not isinstance(self.is_autopay, bool):
            raise P1PaymentError(
                "INVALID_AUTOPAY_FLAG"
            )

        if self.is_autopay and lane == PaymentLane.OFFLINE:
            raise P1PaymentError(
                "OFFLINE_AUTOPAY_UNSUPPORTED"
            )

        object.__setattr__(self, "lane", lane)
        object.__setattr__(self, "sales_channel", channel)
        object.__setattr__(
            self, "payment_provider", provider
        )


def parse_payment_context(payload: dict) -> PaymentContext:
    if not isinstance(payload, dict):
        raise P1PaymentError("PAYMENT_CONTEXT_NOT_OBJECT")

    allowed = {
        "lane",
        "sales_channel",
        "payment_provider",
        "is_autopay",
    }

    if set(payload) - allowed:
        raise P1PaymentError(
            "UNKNOWN_PAYMENT_CONTEXT_FIELDS"
        )

    if "lane" not in payload or "sales_channel" not in payload:
        raise P1PaymentError(
            "PAYMENT_CONTEXT_REQUIRED_FIELDS"
        )

    return PaymentContext(
        lane=payload["lane"],
        sales_channel=payload["sales_channel"],
        payment_provider=payload.get("payment_provider"),
        is_autopay=payload.get("is_autopay", False),
    )


from dataclasses import dataclass
from enum import Enum

from .p1_payment_p0 import (
    PaymentLane,
    PaymentProvider,
    SalesChannel,
    PaymentContext,
)


class ChannelStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class ChannelDecision:
    status: ChannelStatus
    reason: str

    @property
    def eligible(self) -> bool:
        return self.status == ChannelStatus.ELIGIBLE


PROVIDERS = {
    "NAVERPAY",
    "KAKAOPAY",
    "SAMSUNGPAY",
}


def _value(value):
    if isinstance(value, Enum):
        return value.value
    if value is None:
        return None
    return str(value).strip()


def evaluate_channel(
    *,
    payment: PaymentContext,
    payment_channel_required: str,
    channel_includes=(),
    channel_excludes=(),
) -> ChannelDecision:
    """
    Evaluate payment-lane restrictions only.

    All channel target codes must already have
    been separated from other target conditions.

    Does not calculate cash benefits.
    """

    lane = _value(payment.lane)
    provider = _value(payment.payment_provider)
    sales = _value(payment.sales_channel)
    required = _value(payment_channel_required)

    includes = tuple(_value(x) for x in channel_includes)
    excludes = tuple(_value(x) for x in channel_excludes)

    if (
        lane not in {"OFFLINE", "ONLINE", "SIMPLE_PAY"}
        or sales not in {"OFFLINE", "ONLINE"}
    ):
        return ChannelDecision(
            ChannelStatus.UNRESOLVED,
            "INVALID_PAYMENT_CONTEXT",
        )

    if lane == "SIMPLE_PAY":
        if provider not in PROVIDERS:
            return ChannelDecision(
                ChannelStatus.UNRESOLVED,
                "INVALID_PAYMENT_PROVIDER",
            )
    elif provider is not None:
        return ChannelDecision(
            ChannelStatus.UNRESOLVED,
            "UNEXPECTED_PAYMENT_PROVIDER",
        )

    if required == "QR":
        return ChannelDecision(
            ChannelStatus.INELIGIBLE,
            "QR_EXCLUDED_FROM_P1",
        )

    if required == "CARD":
        return ChannelDecision(
            ChannelStatus.UNRESOLVED,
            "CARD_SEMANTICS_NOT_CONFIRMED",
        )

    if required not in {"ANY", "ONLINE"}:
        return ChannelDecision(
            ChannelStatus.UNRESOLVED,
            "UNKNOWN_CHANNEL_REQUIREMENT",
        )

    if required == "ONLINE" and lane != "ONLINE":
        return ChannelDecision(
            ChannelStatus.INELIGIBLE,
            "ONLINE_CARD_REQUIRED",
        )

    # Explicit CHANNEL conditions must use
    # a documented payment provider code.
    if any(
        code not in PROVIDERS
        for code in (*includes, *excludes)
    ):
        return ChannelDecision(
            ChannelStatus.UNRESOLVED,
            "UNSUPPORTED_CHANNEL_TARGET",
        )

    if includes or excludes:
        if lane != "SIMPLE_PAY":
            return ChannelDecision(
                ChannelStatus.INELIGIBLE,
                "SIMPLE_PAY_REQUIRED",
            )

        if provider in excludes:
            return ChannelDecision(
                ChannelStatus.INELIGIBLE,
                "PROVIDER_EXCLUDED",
            )

        if includes and provider not in includes:
            return ChannelDecision(
                ChannelStatus.INELIGIBLE,
                "PROVIDER_NOT_INCLUDED",
            )

    return ChannelDecision(
        ChannelStatus.ELIGIBLE,
        "CHANNEL_MATCHED",
    )

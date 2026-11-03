"""직원 대시보드용 집계 (DB 조회 + 시뮬레이션 결과 파일 결합, 읽기 전용)."""

from collections import Counter

from app.repositories.admin_repository import AdminRepository
from app.services.simulation_result_loader import (
    SCENARIOS,
    SimulationResults,
    load_results,
)


# --------- 코드 → 화면 표기 ------------
DISTRICT_NAMES = {
    "26110": "중구", "26140": "서구", "26170": "동구", "26200": "영도구",
    "26230": "부산진구", "26260": "동래구", "26290": "남구", "26320": "북구",
    "26350": "해운대구", "26380": "사하구", "26410": "금정구", "26440": "강서구",
    "26470": "연제구", "26500": "수영구", "26530": "사상구", "26710": "기장군",
}
AGE_LABELS = {
    "20s": "20대", "30s": "30대", "40s": "40대",
    "50s": "50대", "60s": "60대", "70plus": "70대+",
}
SPEND_LABELS = {"LOW": "저소비", "MID": "중소비", "HIGH": "고소비"}
USAGE_STYLE_LABELS = {
    "SINGLE_CARD": "카드 1장",
    "MAIN_SUB": "주·부 카드형",
    "PURPOSE_BASED": "목적별",
    "UNDIFFERENTIATED": "구분 없음",
}
# 동백전 월 사용 수준 → (화면 표기, 그룹)
USAGE_LEVELS = {
    "NONE": ("가입 후 미사용", "G1"),
    "LT_100K": ("월 10만 미만", "G2"),
    "100K_300K": ("월 10~30만", "G3"),
    "300K_500K": ("월 30~50만", "G4"),
    "GE_500K": ("월 50만 이상", "G5"),
    "NON_MEMBER": ("비회원", None),
}
INDUSTRY_LABELS = {
    "RESTAURANT": "음식점", "BEAUTY_LEISURE_ETC": "미용·여가",
    "CAFE_BAKERY": "카페·베이커리", "HOSPITAL_PHARMACY": "병원·약국",
    "ACADEMY": "학원", "SUPERMARKET": "슈퍼마켓", "CONVENIENCE_STORE": "편의점",
    "FUEL_AUTO": "주유·자동차", "CLOTHING_GOODS": "의류·잡화",
    "LARGE_MART_SSM": "대형마트·SSM", "FRANCHISE_DIRECT_FOOD": "직영 음식점",
    "FRANCHISE_DIRECT_CAFE": "직영 카페", "ONLINE_MALL": "온라인몰",
    "DEPARTMENT_STORE": "백화점",
}
CARD_TYPE_LABELS = {
    "BANK_CREDIT": "BNK 신용",
    "BANK_CHECK": "BNK 체크",
    "DONGBAEK_CHECK": "동백전",
}
CARD_TYPE_GROUP = {
    "DONGBAEK_CHECK": "db",
    "BANK_CREDIT": "cr",
    "BANK_CHECK": "ck",
}


def classify_cohort(
    wallet_status: str | None,
    usage_level: str | None,
) -> tuple[str, str, bool]:
    """(그룹, 지갑 상태 표기, 프로필 불일치 여부)

    - 지갑 ACTIVE + 회원 사용 수준(NONE~GE_500K) → G1~G5 (활성)
    - 프로필이 비회원(NON_MEMBER) → G6 (미보유)
      · 이때 지갑이 ACTIVE면 프로필·지갑 불일치로 표시
    - 그 밖 (사용 수준 미상, 지갑 비활성 회원 등) → G7 (정보 없음)
    """

    level = USAGE_LEVELS.get(usage_level or "")
    group = level[1] if level else None

    if wallet_status == "ACTIVE" and group:
        return group, "활성", False

    if usage_level == "NON_MEMBER":
        return "G6", "미보유", wallet_status == "ACTIVE"

    return "G7", "정보 없음", False


def card_group(product_id: str | None, card_type: str | None) -> str:
    if card_type in CARD_TYPE_GROUP:
        return CARD_TYPE_GROUP[card_type]
    if not product_id:
        return "none"
    if product_id.startswith("PRD_DB"):
        return "db"
    if product_id.startswith("BNK_CR"):
        return "cr"
    if product_id.startswith("BNK_CK"):
        return "ck"
    return "none"


class AdminService:
    def __init__(
        self,
        repository: AdminRepository,
        results: SimulationResults | None = None,
    ):
        self.repository = repository
        self._results = results

    @property
    def results(self) -> SimulationResults:
        if self._results is None:
            self._results = load_results()
        return self._results

    # --------- 사용자 목록 (프로필 + 그룹 + 시나리오 혜택) ------------
    def get_users(self) -> list[dict]:
        results = self.results
        wallets = self.repository.get_wallet_status_by_user()

        cards_by_user: dict[str, list] = {}
        for user_card, product in self.repository.get_user_cards_with_product():
            if user_card.card_status not in (None, "ACTIVE"):
                continue
            card_type = product.card_type if product else None
            name = product.product_name if product else user_card.product_id
            label = CARD_TYPE_LABELS.get(card_type or "", "")
            cards_by_user.setdefault(user_card.user_id, []).append(
                {
                    "name": f"{label} · {name}" if label and card_type != "DONGBAEK_CHECK" else (name or ""),
                    "primary": user_card.default_preference_rank == 1,
                    "is_dongbaek": card_type == "DONGBAEK_CHECK",
                }
            )

        items = []
        for user in self.repository.get_users():
            result = results.users.get(user.user_id)
            if result is None:
                continue

            group, wallet_label, mismatch = classify_cohort(
                wallets.get(user.user_id),
                user.dongbaek_usage_level,
            )
            cards = cards_by_user.get(user.user_id, [])
            txs = results.transactions_by_user.get(user.user_id, [])
            benefit = result.benefit_won

            items.append(
                {
                    "id": user.user_id,
                    "g": group,
                    "age": AGE_LABELS.get(user.age_band or "", user.age_band or "미상"),
                    "gu": DISTRICT_NAMES.get(user.district_code or "", user.district_code or "미상"),
                    "district_code": user.district_code,
                    "sp": SPEND_LABELS.get(user.spend_band or "", user.spend_band or "미상"),
                    "st": USAGE_STYLE_LABELS.get(result.usage_style, result.usage_style),
                    "lv": USAGE_LEVELS.get(user.dongbaek_usage_level or "", (user.dongbaek_usage_level or "미상",))[0],
                    "ws": wallet_label,
                    "mem": any(c["is_dongbaek"] for c in cards),
                    "cc": len(cards),
                    "cards": [[c["name"], c["primary"]] for c in cards],
                    "tx": len(txs),
                    "amt": sum(t.amount_won for t in txs),
                    "a": benefit["S00"],
                    "b": benefit["S10"],
                    "c": benefit["S01"],
                    "d": benefit["S11"],
                    "profile_mismatch": mismatch,
                }
            )
        return items

    # --------- 사용자 거래별 시나리오 비교 ------------
    def get_user_transactions(self, user_id: str) -> list[dict] | None:
        results = self.results
        if user_id not in results.users:
            return None

        txs = results.transactions_by_user.get(user_id, [])
        merchants = {
            m.merchant_id: m
            for m in self.repository.get_merchants_by_ids(
                sorted({t.merchant_id for t in txs})
            )
        }
        products = {p.product_id: p for p in self.repository.get_card_products()}

        def card_name(product_id: str | None) -> str:
            if not product_id:
                return "미배정"
            product = products.get(product_id)
            return (product.product_name if product else None) or product_id

        items = []
        for t in txs:
            merchant = merchants.get(t.merchant_id)
            items.append(
                {
                    "transaction_id": t.transaction_id,
                    "requested_at": t.requested_at,
                    "merchant_id": t.merchant_id,
                    "merchant_name": merchant.merchant_name if merchant else None,
                    "industry": INDUSTRY_LABELS.get(
                        merchant.industry_code if merchant else "",
                        merchant.industry_code if merchant else None,
                    ),
                    "dongbaek_registered": (
                        merchant.dongbaek_status == "REGISTERED" if merchant else None
                    ),
                    "amount_won": t.amount_won,
                    "lane": t.lane,
                    "selected_card": t.selected_card,
                    "card_name": {s: card_name(t.selected_card[s]) for s in SCENARIOS},
                    "benefit_won": t.benefit_won,
                }
            )
        return items

    # --------- 전체 개요 ------------
    def get_overview(self) -> dict:
        results = self.results
        summary = results.summary
        users = self.get_users()

        products = {p.product_id: p for p in self.repository.get_card_products()}
        allocation: dict[str, dict[str, dict[str, int]]] = {}
        tx_count = 0
        tx_amount = 0
        for scenario in ("S00", "S01", "S11"):
            groups = {k: {"count": 0, "amount_won": 0} for k in ("db", "cr", "ck", "none")}
            for txs in results.transactions_by_user.values():
                for t in txs:
                    pid = t.selected_card[scenario]
                    product = products.get(pid or "")
                    key = card_group(pid, product.card_type if product else None)
                    groups[key]["count"] += 1
                    groups[key]["amount_won"] += t.amount_won
            allocation[scenario] = groups
        for txs in results.transactions_by_user.values():
            tx_count += len(txs)
            tx_amount += sum(t.amount_won for t in txs)

        industry: dict[str, list[int]] = {}
        for code, status, count in self.repository.count_merchants_by_industry_status():
            row = industry.setdefault(code, [0, 0, 0])
            idx = 0 if status == "REGISTERED" else 1 if status == "NOT_REGISTERED" else 2
            row[idx] += count
        industries = sorted(
            (
                {
                    "name": INDUSTRY_LABELS.get(code, code),
                    "registered": v[0],
                    "not_registered": v[1],
                    "unknown": v[2],
                }
                for code, v in industry.items()
            ),
            key=lambda r: -(r["registered"] + r["not_registered"] + r["unknown"]),
        )

        policies = []
        for policy, rates in self.repository.get_policies_with_rates():
            ordered = sorted(rates, key=lambda r: -(float(r.cashback_rate or 0)))
            policies.append(
                {
                    "id": policy.policy_id,
                    "name": policy.policy_name,
                    "start": policy.valid_from.isoformat() if policy.valid_from else None,
                    "end": policy.valid_to.isoformat() if policy.valid_to else None,
                    "cap": policy.monthly_cashback_base_cap_won,
                    "src": policy.source_status or policy.policy_mode,
                    "rates": [
                        {"band": r.sales_band, "rate": float(r.cashback_rate or 0)}
                        for r in ordered
                    ],
                }
            )

        cohorts = Counter(u["g"] for u in users)
        wallet_labels = Counter(u["ws"] for u in users)

        scenario_totals = summary.get("scenario_benefits_won") or {
            s: sum(u.benefit_won[s] for u in results.users.values()) for s in SCENARIOS
        }

        return {
            "meta": {
                "evaluation_month": "2026-06",
                "data_version": (summary.get("methodology") or {}).get("data_version", "v3.4"),
                "point_rate": (summary.get("methodology") or {}).get("point_rate"),
                "results_dir": str(results.results_dir),
                "constants_source": results.constants.get("_source"),
            },
            "counts": {
                "users": len(users),
                "dongbaek_members": sum(1 for u in users if u["mem"]),
                "active_wallets": wallet_labels.get("활성", 0),
                "onecard_active": self.repository.count_active_onecards(),
                "card_slots": sum(u["cc"] for u in users),
                "merchants": sum(r["registered"] + r["not_registered"] + r["unknown"] for r in industries),
                "profile_mismatch": sum(1 for u in users if u["profile_mismatch"]),
            },
            "cohort_counts": {g: cohorts.get(g, 0) for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7")},
            "transactions": {"count": tx_count, "amount_won": tx_amount},
            "scenarios": {s: int(scenario_totals[s]) for s in SCENARIOS},
            "shapley": {
                "balance_won": int(summary.get("shapley_balance_effect_won", 0)),
                "choice_won": int(summary.get("shapley_behavior_effect_won", 0)),
                "interaction_won": int(summary.get("interaction_effect_won", 0)),
            },
            "allocation": allocation,
            "exclusion_reasons": results.constants.get("exclusion_reasons"),
            "s02_sensitivity": results.constants.get("s02_sensitivity"),
            "industries": industries,
            "sales_bands": [
                {"band": band or "UNKNOWN", "count": count}
                for band, count in self.repository.count_merchants_by_sales_band()
            ],
            "policies": policies,
        }

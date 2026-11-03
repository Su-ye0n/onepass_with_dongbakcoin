
"""Fast read-only repositories for OnePass P1 MVP.

Loads eligibility reference data once per run.
Reuses existing target/channel evaluators.
Caches normalized product rules by product and date.
"""

from collections import defaultdict
from datetime import date
from functools import lru_cache

from onepass.db_connection import connect_readonly
from onepass.p1_rule_repository import P1RuleRepository
from onepass.p1_eligibility_repository import EligibilityResult
from onepass.p1_target_evaluator import (
    MerchantContext,
    TargetCondition,
    evaluate_target,
)
from onepass.p1_channel_evaluator import evaluate_channel
from onepass.p1_target_repository import choose_category


def status_value(value):
    return getattr(value, "value", value)


class FastRuleRepository:
    def __init__(self):
        self.original = P1RuleRepository()
        self.load = lru_cache(maxsize=512)(
            self.original.load
        )

    def cache_info(self):
        return self.load.cache_info()


class FastEligibilityRepository:
    def __init__(self):
        self.rules = {}
        self.merchants = {}
        self.targets = defaultdict(list)
        self.categories = defaultdict(list)
        self.reward_units = {}

        with connect_readonly() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        rule_id,
                        payment_channel_required,
                        source_status,
                        valid_from,
                        valid_to,
                        reward_unit
                    FROM public.benefit_rule
                """)
                for r in cur.fetchall():
                    self.rules[r["rule_id"]] = dict(r)
                    self.reward_units[r["rule_id"]] = (
                        r["reward_unit"]
                    )

                cur.execute("""
                    SELECT merchant_id, industry_code
                    FROM public.merchant
                """)
                for r in cur.fetchall():
                    self.merchants[r["merchant_id"]] = (
                        r["industry_code"]
                    )

                cur.execute("""
                    SELECT
                        rule_id, target_type,
                        target_code, apply_type
                    FROM public.benefit_industry
                """)
                for r in cur.fetchall():
                    self.targets[r["rule_id"]].append(
                        dict(r)
                    )

                cur.execute("""
                    SELECT
                        industry_code,
                        std_category,
                        valid_from,
                        valid_to
                    FROM public.benefit_category_map
                """)
                for r in cur.fetchall():
                    self.categories[
                        r["industry_code"]
                    ].append(dict(r))

        self.evaluate = lru_cache(maxsize=200000)(
            self._evaluate
        )

    def cache_info(self):
        return self.evaluate.cache_info()

    def _evaluate(
        self,
        *,
        rule_id,
        merchant_id,
        payment,
        as_of,
    ):
        day = (
            date.fromisoformat(as_of)
            if isinstance(as_of, str)
            else as_of
        )

        rule = self.rules.get(rule_id)

        def result(
            status,
            reason,
            target_status="NOT_EVALUATED",
            channel_status="NOT_EVALUATED",
            source_status=None,
            std_category=None,
        ):
            return EligibilityResult(
                rule_id=rule_id,
                merchant_id=merchant_id,
                status=status,
                reason=reason,
                target_status=target_status,
                channel_status=channel_status,
                source_status=source_status,
                std_category=std_category,
            )

        if rule is None:
            return result(
                "UNRESOLVED",
                "RULE_NOT_FOUND_OR_DUPLICATED",
            )

        source = rule["source_status"]
        start = rule["valid_from"]
        end = rule["valid_to"]

        if (
            (start is not None and day < start)
            or (end is not None and day > end)
        ):
            return result(
                "INELIGIBLE",
                "RULE_OUT_OF_VALIDITY",
                source_status=source,
            )

        industry = self.merchants.get(merchant_id)

        if merchant_id not in self.merchants:
            return result(
                "UNRESOLVED",
                "MERCHANT_NOT_FOUND_OR_DUPLICATED",
                source_status=source,
            )

        if not industry:
            return result(
                "UNRESOLVED",
                "MERCHANT_INDUSTRY_MISSING",
                source_status=source,
            )

        conditions = []
        channel_includes = []
        channel_excludes = []
        invalid = False

        for row in self.targets.get(rule_id, []):
            target_type = row["target_type"]
            apply_type = row["apply_type"]
            code = row["target_code"]

            if target_type == "CHANNEL":
                if apply_type == "INCLUDE":
                    channel_includes.append(code)
                elif apply_type == "EXCLUDE":
                    channel_excludes.append(code)
                else:
                    invalid = True

            elif target_type in ("CATEGORY", "MERCHANT"):
                conditions.append(
                    TargetCondition(
                        rule_id=rule_id,
                        target_type=target_type,
                        target_code=code,
                        apply_type=apply_type,
                    )
                )
            else:
                invalid = True

        if invalid:
            return result(
                "UNRESOLVED",
                "UNKNOWN_TARGET_CONDITION",
                source_status=source,
            )

        if not conditions:
            return result(
                "UNRESOLVED",
                "TARGET_RULES_MISSING",
                source_status=source,
            )

        category_map = {}
        std_category = None

        if any(
            c.target_type == "CATEGORY"
            for c in conditions
        ):
            matched = [
                (
                    industry,
                    row["std_category"],
                )
                for row in self.categories.get(
                    industry, []
                )
                if (
                    row["valid_from"] is None
                    or row["valid_from"] <= day
                )
                and (
                    row["valid_to"] is None
                    or row["valid_to"] >= day
                )
            ]

            std_category, error = choose_category(
                matched, industry
            )

            if error:
                return result(
                    "UNRESOLVED",
                    error,
                    source_status=source,
                )

            category_map[industry] = std_category

        target = evaluate_target(
            rule_id=rule_id,
            merchant=MerchantContext(
                merchant_id=merchant_id,
                industry_code=industry,
            ),
            conditions=conditions,
            category_map=category_map,
        )

        channel = evaluate_channel(
            payment=payment,
            payment_channel_required=rule[
                "payment_channel_required"
            ],
            channel_includes=channel_includes,
            channel_excludes=channel_excludes,
        )

        ts = status_value(target.status)
        cs = status_value(channel.status)

        if ts == "INELIGIBLE" or cs == "INELIGIBLE":
            status = "INELIGIBLE"
            reason = (
                target.reason
                if ts == "INELIGIBLE"
                else channel.reason
            )

        elif ts == "UNRESOLVED" or cs == "UNRESOLVED":
            status = "UNRESOLVED"
            reason = (
                target.reason
                if ts == "UNRESOLVED"
                else channel.reason
            )

        else:
            status = "ELIGIBLE"
            reason = "TARGET_AND_CHANNEL_MATCHED"

        return result(
            status,
            reason,
            target_status=ts,
            channel_status=cs,
            source_status=source,
            std_category=std_category,
        )


def make_fast_repositories():
    rules = FastRuleRepository()
    eligibility = FastEligibilityRepository()
    return rules, eligibility

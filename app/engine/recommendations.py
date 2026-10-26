"""Transparent recommendation generator distinguishing evidence from advice.

This module implements the decision-support engine required by Section 9 of the
TECH5 specification, providing inspectable recommendations with explicit
criteria, mathematical evidence, and policy-oriented advice.
"""

import dataclasses
from typing import Any

from app.domain import models


@dataclasses.dataclass
class RecommendationItem:
    """An individual decision recommendation.

    Attributes:
        priority_focus: The organizational objective prioritized (e.g.
            Student Satisfaction, Project Skill Delivery, Egalitarian Balance).
        recommended_solution_id: Identifier of the top solution for this focus.
        recommended_alternative_number: 1-based index of recommended solution.
        criteria_used: Explicit list of analytical metrics evaluated.
        evidence: Objective calculated facts supporting the recommendation.
        advice: Practical normative advice describing operational trade-offs.
        trade_offs: Explicit opportunity costs and trade-offs incurred
            relative to competing alternatives.
    """

    priority_focus: str
    recommended_solution_id: str
    recommended_alternative_number: int
    criteria_used: list[str]
    evidence: list[str]
    advice: str
    trade_offs: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializes recommendation item to a dictionary.

        Returns:
            Dictionary containing recommendation fields.
        """
        return {
            "priority_focus": self.priority_focus,
            "recommended_solution_id": self.recommended_solution_id,
            "recommended_alternative_number": (
                self.recommended_alternative_number
            ),
            "criteria_used": list(self.criteria_used),
            "evidence": list(self.evidence),
            "advice": self.advice,
            "trade_offs": list(self.trade_offs),
        }


def generate_recommendations(
    solutions: list[models.Solution],
) -> list[RecommendationItem]:
    """Generates policy-oriented recommendations from alternative solutions.

    In compliance with Section 9 of the TECH5 specification and Section 5 of
    the analytical note, recommendations strictly separate objective calculated
    evidence from normative administrative policy advice, while highlighting
    explicit Pareto trade-offs across three distinct governance priorities:
    1. Student Preference Maximization (Borda rank satisfaction)
    2. Project Skill Quality & Delivery Assurance (competence fit)
    3. Balanced & Egalitarian Compromise (Gini inequality minimization)

    Args:
        solutions: Feasible alternative solutions from an assignment run.

    Returns:
        List of structured RecommendationItem instances.
    """
    if not solutions:
        return []

    recommendations: list[RecommendationItem] = []

    # 1. Identify optimal solution for Priority 1 (Student Satisfaction)
    best_pref_sol = min(
        solutions,
        key=lambda s: (
            s.indicators.get("fairness", {}).get("unranked_count", 999),
            s.indicators.get("fairness", {}).get("mean_rank", 999.0),
            s.indicators.get("fairness", {}).get("worst_rank", 999),
        ),
    )
    pref_indicators = best_pref_sol.indicators
    pref_fairness = pref_indicators.get("fairness", {})
    pref_efficiency = pref_indicators.get("efficiency", {})

    # 2. Identify optimal solution for Priority 2 (Project Skill Fit)
    best_skill_sol = max(
        solutions,
        key=lambda s: (
            s.indicators.get("efficiency", {}).get("mean_skill_fit", -1.0),
            -s.indicators.get("efficiency", {}).get(
                "unmet_soft_requirements_count", 999
            ),
        ),
    )
    skill_indicators = best_skill_sol.indicators
    skill_efficiency = skill_indicators.get("efficiency", {})
    skill_fairness = skill_indicators.get("fairness", {})

    # 3. Identify optimal solution for Priority 3 (Egalitarian Fairness & Gini)
    best_balanced_sol = min(
        solutions,
        key=lambda s: (
            s.indicators.get("fairness", {}).get("rank_gini", 1.0),
            s.indicators.get("fairness", {}).get("rank_variance", 999.0),
            s.indicators.get("fairness", {}).get("mean_rank", 999.0),
        ),
    )
    bal_indicators = best_balanced_sol.indicators
    bal_fairness = bal_indicators.get("fairness", {})
    bal_efficiency = bal_indicators.get("efficiency", {})

    # Single-alternative edge case
    is_single_alt = len(solutions) == 1

    # Build Priority 1 Item
    pref_trade_offs: list[str] = []
    if not is_single_alt:
        skill_delta = (
            skill_efficiency.get("mean_skill_fit", 0.0)
            - pref_efficiency.get("mean_skill_fit", 0.0)
        )
        if skill_delta > 0.005:
            pref_trade_offs.append(
                f"Skill Fit Penalty: Mean skill-fit score is "
                f"{pref_efficiency.get('mean_skill_fit', 0.0):.1%} (a reduction of "
                f"{skill_delta * 100:.1f}% compared to Alternative "
                f"#{best_skill_sol.alternative_number})."
            )
        soft_unmet_diff = (
            pref_efficiency.get("unmet_soft_requirements_count", 0)
            - skill_efficiency.get("unmet_soft_requirements_count", 0)
        )
        if soft_unmet_diff > 0:
            pref_trade_offs.append(
                f"Technical Coverage: Leaves {soft_unmet_diff} additional soft "
                f"skill requirement(s) unmet across client projects."
            )
    else:
        pref_trade_offs.append(
            "Single feasible alternative produced; no Pareto trade-off variance exists."
        )

    recommendations.append(
        RecommendationItem(
            priority_focus="Student Preference Maximization",
            recommended_solution_id=best_pref_sol.id,
            recommended_alternative_number=best_pref_sol.alternative_number,
            criteria_used=[
                "Average student preference rank (lower is better)",
                "Count of students assigned outside stated preferences",
                "Worst individual student rank (regret minimization)",
            ],
            evidence=[
                f"Achieves average preference rank of "
                f"{pref_fairness.get('mean_rank', 'N/A')}.",
                f"Assigned {pref_fairness.get('unranked_count', 0)} student(s) "
                "outside stated preferences.",
                f"Worst individual student rank is "
                f"{pref_fairness.get('worst_rank', 'N/A')}.",
                f"Maintains average skill-fit score of "
                f"{pref_efficiency.get('mean_skill_fit', 0.0):.2f}.",
            ],
            advice=(
                f"Adopt Solution {best_pref_sol.alternative_number} if student "
                "satisfaction, cohort morale, and minimizing student grievance "
                "appeals are the primary administrative priorities."
            ),
            trade_offs=pref_trade_offs,
        )
    )

    # Build Priority 2 Item
    skill_trade_offs: list[str] = []
    if not is_single_alt:
        rank_delta = (
            skill_fairness.get("mean_rank", 0.0)
            - pref_fairness.get("mean_rank", 0.0)
        )
        if rank_delta > 0.05:
            skill_trade_offs.append(
                f"Student Satisfaction Cost: Average preference rank worsens by "
                f"{rank_delta:.2f} rank positions (mean rank "
                f"{skill_fairness.get('mean_rank', 'N/A')} vs "
                f"{pref_fairness.get('mean_rank', 'N/A')} in Alternative "
                f"#{best_pref_sol.alternative_number})."
            )
        unranked_diff = (
            skill_fairness.get("unranked_count", 0)
            - pref_fairness.get("unranked_count", 0)
        )
        if unranked_diff > 0:
            skill_trade_offs.append(
                f"Displaced Students: {unranked_diff} additional student(s) "
                "allocated outside submitted preference lists."
            )
        worst_rank_diff = (
            skill_fairness.get("worst_rank", 0)
            - pref_fairness.get("worst_rank", 0)
        )
        if worst_rank_diff > 0:
            skill_trade_offs.append(
                f"Worst-case Regret: Highest individual rank is "
                f"{skill_fairness.get('worst_rank', 'N/A')}, compared to "
                f"{pref_fairness.get('worst_rank', 'N/A')} under student focus."
            )
    else:
        skill_trade_offs.append(
            "Single feasible alternative produced; no Pareto trade-off variance exists."
        )

    recommendations.append(
        RecommendationItem(
            priority_focus="Project Skill Quality & Delivery Assurance",
            recommended_solution_id=best_skill_sol.id,
            recommended_alternative_number=best_skill_sol.alternative_number,
            criteria_used=[
                "Average student-project skill fit score (higher is better)",
                "Total unmet soft skill requirements (lower is better)",
                "Full mandatory skill compliance across all teams",
            ],
            evidence=[
                f"Highest average skill fit score of "
                f"{skill_efficiency.get('mean_skill_fit', 0.0):.2f}.",
                f"Unmet soft requirements count: "
                f"{skill_efficiency.get('unmet_soft_requirements_count', 0)}.",
                f"Average student preference rank is "
                f"{skill_fairness.get('mean_rank', 'N/A')}.",
            ],
            advice=(
                f"Adopt Solution {best_skill_sol.alternative_number} when "
                "external partner organizations or capstone research sponsors "
                "demand strict technical proficiencies and high deliverable quality."
            ),
            trade_offs=skill_trade_offs,
        )
    )

    # Build Priority 3 Item
    bal_trade_offs: list[str] = []
    if not is_single_alt:
        gini_val = bal_fairness.get("rank_gini", "N/A")
        bal_trade_offs.append(
            f"Egalitarian Equality: Achieves rank Gini coefficient of "
            f"{gini_val}, minimizing disparity between satisfied and dissatisfied students."
        )
        skill_gap = (
            skill_efficiency.get("mean_skill_fit", 0.0)
            - bal_efficiency.get("mean_skill_fit", 0.0)
        )
        rank_gap = (
            bal_fairness.get("mean_rank", 0.0)
            - pref_fairness.get("mean_rank", 0.0)
        )
        bal_trade_offs.append(
            f"Balanced Compromise: Concedes only {skill_gap * 100:.1f}% skill fit "
            f"relative to the skill-optimal solution while remaining within "
            f"{rank_gap:.2f} average rank of the preference-optimal solution."
        )
    else:
        bal_trade_offs.append(
            "Single feasible alternative produced; represents the unique Pareto allocation."
        )

    recommendations.append(
        RecommendationItem(
            priority_focus="Balanced & Egalitarian Allocation",
            recommended_solution_id=best_balanced_sol.id,
            recommended_alternative_number=best_balanced_sol.alternative_number,
            criteria_used=[
                "Rank Gini coefficient (equality of outcome distribution)",
                "Rank variance across student cohort",
                "Harmonized trade-off between preference satisfaction and skill fit",
            ],
            evidence=[
                f"Lowest rank disparity (Gini coefficient: "
                f"{bal_fairness.get('rank_gini', 'N/A')}).",
                f"Rank variance across cohort: "
                f"{bal_fairness.get('rank_variance', 'N/A')}.",
                f"Average skill fit score: "
                f"{bal_efficiency.get('mean_skill_fit', 0.0):.2f}.",
                f"Average student preference rank: "
                f"{bal_fairness.get('mean_rank', 'N/A')}.",
            ],
            advice=(
                f"Adopt Solution {best_balanced_sol.alternative_number} as the "
                "default consensus baseline when academic leadership seeks an "
                "equitable Pareto compromise that balances student happiness against "
                "project quality."
            ),
            trade_offs=bal_trade_offs,
        )
    )

    return recommendations

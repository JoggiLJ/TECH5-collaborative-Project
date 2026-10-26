"""Unit and integration tests for transparent decision recommendations.

This test module validates the decision-support engine implemented for Section 9
of the TECH5 specification, ensuring rigorous separation of calculated evidence
from normative advice, as well as accurate computation of Pareto trade-offs.
"""

import pathlib
from typing import Any

import pytest

from app import create_app
from app.domain import models
from app.engine import recommendations
from app.persistence import repositories


def _create_mock_solution(
    solution_id: str,
    alternative_number: int,
    mean_rank: float,
    unranked_count: int,
    worst_rank: int,
    mean_skill_fit: float,
    unmet_soft: int,
    rank_gini: float,
    rank_variance: float,
) -> models.Solution:
    """Helper creating a domain Solution with specific indicators."""
    return models.Solution(
        id=solution_id,
        run_id="test_run_123",
        alternative_number=alternative_number,
        strategy_name="PREFERENCE",
        objective_value=100.0,
        assignments=[],
        indicators={
            "efficiency": {
                "mean_skill_fit": mean_skill_fit,
                "unmet_soft_requirements_count": unmet_soft,
            },
            "fairness": {
                "mean_rank": mean_rank,
                "unranked_count": unranked_count,
                "worst_rank": worst_rank,
                "rank_gini": rank_gini,
                "rank_variance": rank_variance,
            },
        },
    )


def test_generate_recommendations_empty() -> None:
    """Verifies that empty solution list returns empty recommendations."""
    recs = recommendations.generate_recommendations([])
    assert recs == []


def test_generate_recommendations_single_solution() -> None:
    """Verifies recommendations with only a single feasible alternative."""
    sol = _create_mock_solution(
        solution_id="sol_only",
        alternative_number=1,
        mean_rank=1.5,
        unranked_count=0,
        worst_rank=2,
        mean_skill_fit=0.85,
        unmet_soft=0,
        rank_gini=0.1,
        rank_variance=0.2,
    )
    recs = recommendations.generate_recommendations([sol])
    assert len(recs) == 3

    for item in recs:
        assert item.recommended_solution_id == "sol_only"
        assert item.recommended_alternative_number == 1
        assert len(item.evidence) >= 1
        assert len(item.trade_offs) == 1
        assert "Single feasible alternative" in item.trade_offs[0]


def test_generate_recommendations_multi_priority_tradeoffs() -> None:
    """Verifies distinct Pareto recommendation winners and quantified trade-offs."""
    # Alternative 1: Optimal for Student Satisfaction
    sol_pref = _create_mock_solution(
        solution_id="sol_pref",
        alternative_number=1,
        mean_rank=1.2,
        unranked_count=0,
        worst_rank=2,
        mean_skill_fit=0.60,
        unmet_soft=3,
        rank_gini=0.25,
        rank_variance=0.8,
    )

    # Alternative 2: Optimal for Project Skill Fit
    sol_skill = _create_mock_solution(
        solution_id="sol_skill",
        alternative_number=2,
        mean_rank=3.5,
        unranked_count=2,
        worst_rank=6,
        mean_skill_fit=0.95,
        unmet_soft=0,
        rank_gini=0.30,
        rank_variance=1.2,
    )

    # Alternative 3: Optimal for Egalitarian Fairness & Balance
    sol_fair = _create_mock_solution(
        solution_id="sol_fair",
        alternative_number=3,
        mean_rank=2.0,
        unranked_count=0,
        worst_rank=3,
        mean_skill_fit=0.80,
        unmet_soft=1,
        rank_gini=0.05,
        rank_variance=0.15,
    )

    solutions = [sol_pref, sol_skill, sol_fair]
    recs = recommendations.generate_recommendations(solutions)
    assert len(recs) == 3

    # Priority 1 Check: Student Preference
    rec_pref = recs[0]
    assert rec_pref.priority_focus == "Student Preference Maximization"
    assert rec_pref.recommended_solution_id == "sol_pref"
    assert rec_pref.recommended_alternative_number == 1
    # Check Trade-offs incurred: skill fit penalty relative to sol_skill
    assert any("Skill Fit Penalty" in t for t in rec_pref.trade_offs)
    assert any("Technical Coverage" in t for t in rec_pref.trade_offs)

    # Priority 2 Check: Skill Fit
    rec_skill = recs[1]
    assert rec_skill.priority_focus == "Project Skill Quality & Delivery Assurance"
    assert rec_skill.recommended_solution_id == "sol_skill"
    assert rec_skill.recommended_alternative_number == 2
    # Check Trade-offs incurred: rank worsening, displaced students, worst rank
    assert any("Student Satisfaction Cost" in t for t in rec_skill.trade_offs)
    assert any("Displaced Students" in t for t in rec_skill.trade_offs)
    assert any("Worst-case Regret" in t for t in rec_skill.trade_offs)

    # Priority 3 Check: Balanced & Egalitarian
    rec_fair = recs[2]
    assert rec_fair.priority_focus == "Balanced & Egalitarian Allocation"
    assert rec_fair.recommended_solution_id == "sol_fair"
    assert rec_fair.recommended_alternative_number == 3
    # Check Trade-offs: Gini equality and balanced compromise
    assert any("Egalitarian Equality" in t for t in rec_fair.trade_offs)
    assert any("Balanced Compromise" in t for t in rec_fair.trade_offs)


def test_recommendation_item_serialization() -> None:
    """Verifies serialization of RecommendationItem to dictionary."""
    item = recommendations.RecommendationItem(
        priority_focus="Student Satisfaction",
        recommended_solution_id="s1",
        recommended_alternative_number=1,
        criteria_used=["Mean rank"],
        evidence=["Average rank is 1.2"],
        advice="Adopt Alternative 1.",
        trade_offs=["Lower skill fit."],
    )
    data = item.to_dict()
    assert data["priority_focus"] == "Student Satisfaction"
    assert data["recommended_solution_id"] == "s1"
    assert data["recommended_alternative_number"] == 1
    assert data["criteria_used"] == ["Mean rank"]
    assert data["evidence"] == ["Average rank is 1.2"]
    assert data["advice"] == "Adopt Alternative 1."
    assert data["trade_offs"] == ["Lower skill fit."]


def test_recommendations_web_route(tmp_path: pathlib.Path) -> None:
    """Verifies the GET /recommendations/<run_id> route rendering."""
    db_file = tmp_path / "test_recs.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})

    sol_a = _create_mock_solution(
        solution_id="sol_a",
        alternative_number=1,
        mean_rank=1.1,
        unranked_count=0,
        worst_rank=2,
        mean_skill_fit=0.7,
        unmet_soft=1,
        rank_gini=0.15,
        rank_variance=0.3,
    )
    sol_b = _create_mock_solution(
        solution_id="sol_b",
        alternative_number=2,
        mean_rank=2.5,
        unranked_count=1,
        worst_rank=4,
        mean_skill_fit=0.95,
        unmet_soft=0,
        rank_gini=0.20,
        rank_variance=0.5,
    )
    run = models.AssignmentRun(
        id="run_test_recs",
        created_at="2026-10-26T12:00:00Z",
        status="COMPLETED",
        configuration={"max_alternatives": 2},
        solutions=[sol_a, sol_b],
    )
    repositories.RunRepository().save_run(run)

    client = app.test_client()

    # 1. Existing run with solutions
    resp = client.get("/recommendations/run_test_recs")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Transparent Decision Recommendations" in html
    assert "Pareto Opportunity Costs &amp; Trade-offs" in html
    assert "Student Preference Maximization" in html
    assert "Project Skill Quality &amp; Delivery Assurance" in html
    assert "Balanced &amp; Egalitarian Allocation" in html

    # 2. Non-existent run redirects
    resp_missing = client.get("/recommendations/non_existent_run", follow_redirects=True)
    assert resp_missing.status_code == 200
    assert "not found" in resp_missing.get_data(as_text=True)

    # 3. Existing run with zero solutions
    run_empty = models.AssignmentRun(
        id="run_empty_sol",
        created_at="2026-10-26T12:00:00Z",
        status="INFEASIBLE",
        configuration={"max_alternatives": 2},
        solutions=[],
    )
    repositories.RunRepository().save_run(run_empty)
    resp_empty = client.get("/recommendations/run_empty_sol")
    assert resp_empty.status_code == 200
    assert "No recommendations available" in resp_empty.get_data(as_text=True)

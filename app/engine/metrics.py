"""Calculators for feasibility, efficiency, fairness, and trade-offs.

This module provides analytical functions to evaluate solutions according to
the requirements in Section 7 of the TECH5 specification.

Students (Team B) must implement these analytical functions to compute
student-project skill fit, Gini inequality, solution indicators, and
side-by-side trade-off comparisons.
"""

from typing import Any

from app.domain import models


def calculate_assignment_skill_fit(
    student: models.Student,
    project: models.Project,
) -> tuple[float, list[str]]:
    """Calculates skill fit score and unmet requirements for a student-project pair.

    In compliance with Section 7.2 of the TECH5 specification, skill fit
    evaluates how well the candidate student satisfies the required technical
    skills of the target project.

    Args:
        student: The student under evaluation.
        project: The project under evaluation.

    The score is sigma_{s,p} from Section 2.2 of the analytical note: the
    average over the project's requirements of min(1, level / required level).
    A project without requirements gives a neutral fit of 1.0.

    Args:
        student: The student under evaluation.
        project: The project under evaluation.

    Returns:
        A tuple of (skill_fit_score [0.0, 1.0], list_of_unmet_skill_ids).
    """
    if not project.requirements:
        return 1.0, []

    coverage: list[float] = []
    unmet: list[str] = []
    for req in project.requirements:
        level = student.get_skill_level(req.skill_id)
        if req.minimum_level <= 0:
            coverage.append(1.0)
            continue
        coverage.append(min(1.0, level / req.minimum_level))
        if level < req.minimum_level:
            unmet.append(req.skill_id)
    return sum(coverage) / len(coverage), unmet


def calculate_gini(values: list[float]) -> float:
    """Calculates the Gini coefficient of inequality for non-negative values.

    In compliance with Section 7.3 of the TECH5 specification, the Gini
    coefficient measures the inequality/fairness in student preference rank
    distribution (0.0 represents perfect equality, 1.0 represents extreme inequality).

    Args:
        values: Non-negative numerical series (e.g. assigned preference ranks).

    Uses G = sum_i sum_j |v_i - v_j| / (2 n sum_i v_i) from Section 3.3 of
    the analytical note.

    Args:
        values: Non-negative numerical series (e.g. assigned preference ranks).

    Returns:
        The Gini coefficient in [0.0, 1.0]. An empty or all-zero series
        returns 0.0.

    Raises:
        ValueError: If any value is negative.
    """
    if any(v < 0 for v in values):
        raise ValueError("Gini coefficient requires non-negative values.")
    total = sum(values)
    if not values or total == 0:
        return 0.0
    abs_diff_sum = sum(abs(a - b) for a in values for b in values)
    return abs_diff_sum / (2 * len(values) * total)


def compute_solution_indicators(
    students: list[models.Student],
    projects: list[models.Project],
    assignments: list[models.Assignment],
    fixed_assignments: list[models.FixedAssignment] | None = None,
) -> dict[str, Any]:
    """Computes comprehensive feasibility, efficiency, and fairness indicators.

    Evaluates a solution across the four dimensions defined in the specification:
    1. Feasibility: Exact student count, capacity bounds, fixed assignments.
    2. Efficiency: Mean skill-fit score, unmet soft requirements count.
    3. Fairness: Rank distribution, mean rank, worst rank, unranked count, Gini.
    4. Capacity: Total assigned, total capacity, overall utilization, per-project.

    Args:
        students: Complete cohort of students.
        projects: Catalog of semester projects.
        assignments: List of student-to-project allocations.
        fixed_assignments: Optional list of locked pre-allocations.

    Returns:
        Dictionary containing structured indicators and diagnostic metrics:
        {
            "feasibility": {"is_feasible": bool, "violations": list[str], ...},
            "efficiency": {"mean_skill_fit": float, ...},
            "fairness": {"mean_rank": float, "worst_rank": int, "rank_gini": float, ...},
            "capacity": {"overall_utilization_pct": float, "projects": dict, ...}
        }

    Unranked assignments count as rank |P| + 1 in all rank statistics
    (Section 2.2 of the analytical note).
    """
    projects_by_id = {p.id: p for p in projects}
    student_ids = {s.id for s in students}
    unranked_rank = len(projects) + 1

    # Feasibility (Section 3.1): re-verify every hard constraint.
    violations: list[str] = []
    assigned_ids = [a.student_id for a in assignments]
    for s_id in sorted(student_ids - set(assigned_ids)):
        violations.append(f"Student '{s_id}' has no project.")
    for s_id in sorted({i for i in assigned_ids if assigned_ids.count(i) > 1}):
        violations.append(f"Student '{s_id}' is assigned more than once.")
    for a in assignments:
        if a.project_id not in projects_by_id:
            violations.append(
                f"Student '{a.student_id}' is assigned to unknown project "
                f"'{a.project_id}'."
            )

    headcount = {p.id: 0 for p in projects}
    for a in assignments:
        if a.project_id in headcount:
            headcount[a.project_id] += 1
    for p in projects:
        n_p = headcount[p.id]
        if n_p > 0 and not p.min_capacity <= n_p <= p.max_capacity:
            violations.append(
                f"Project '{p.id}' has {n_p} students, outside its capacity "
                f"[{p.min_capacity}, {p.max_capacity}]."
            )

    assigned_project = {a.student_id: a.project_id for a in assignments}
    for fa in fixed_assignments or []:
        if assigned_project.get(fa.student_id) != fa.project_id:
            violations.append(
                f"Fixed assignment {fa.student_id} -> {fa.project_id} is not "
                "respected."
            )

    students_by_id = {s.id: s for s in students}
    mandatory_unmet_count = 0
    for p in projects:
        if headcount[p.id] == 0:
            continue
        members = [
            students_by_id[a.student_id]
            for a in assignments
            if a.project_id == p.id and a.student_id in students_by_id
        ]
        for req in p.requirements:
            if req.is_mandatory and not any(
                s.get_skill_level(req.skill_id) >= req.minimum_level
                for s in members
            ):
                mandatory_unmet_count += 1
                violations.append(
                    f"Project '{p.id}' has no student meeting mandatory skill "
                    f"'{req.skill_id}' (level {req.minimum_level})."
                )

    # Efficiency (Section 3.2).
    n = len(assignments)
    fit_sum = sum(a.skill_fit_score for a in assignments)
    unmet_soft = 0
    for a in assignments:
        project = projects_by_id.get(a.project_id)
        mandatory = (
            {r.skill_id for r in project.requirements if r.is_mandatory}
            if project
            else set()
        )
        unmet_soft += sum(
            1 for k in a.unmet_requirements if k not in mandatory
        )

    # Fairness (Section 3.3).
    ranks = [
        a.preference_rank if a.preference_rank is not None else unranked_rank
        for a in assignments
    ]
    unranked_count = sum(1 for a in assignments if a.preference_rank is None)
    rank_distribution: dict[str, int] = {}
    for r in sorted({a.preference_rank for a in assignments} - {None}):
        rank_distribution[f"rank_{r}"] = sum(
            1 for a in assignments if a.preference_rank == r
        )
    if unranked_count:
        rank_distribution["unranked"] = unranked_count
    mean_rank = sum(ranks) / n if n else 0.0
    rank_variance = (
        sum((r - mean_rank) ** 2 for r in ranks) / n if n else 0.0
    )

    # Capacity (Section 3.4).
    total_capacity = sum(p.max_capacity for p in projects)

    def utilization(count: int, capacity: int) -> float:
        return round(count / capacity * 100.0, 1) if capacity > 0 else 0.0

    return {
        "feasibility": {
            "is_feasible": not violations,
            "violations": violations,
            "assigned_count": n,
            "total_students": len(students),
            "mandatory_unmet_count": mandatory_unmet_count,
        },
        "efficiency": {
            "mean_skill_fit": round(fit_sum / n, 4) if n else 0.0,
            "unmet_soft_requirements_count": unmet_soft,
            "total_skill_fit_sum": round(fit_sum, 4),
        },
        "fairness": {
            "rank_distribution": rank_distribution,
            "unranked_count": unranked_count,
            "unranked_pct": (
                round(unranked_count / n * 100.0, 1) if n else 0.0
            ),
            "worst_rank": max(ranks) if ranks else 0,
            "mean_rank": round(mean_rank, 4),
            "rank_variance": round(rank_variance, 4),
            "rank_gini": round(calculate_gini([float(r) for r in ranks]), 4),
        },
        "capacity": {
            "total_assigned": n,
            "total_capacity": total_capacity,
            "capacity_slack": total_capacity - n,
            "overall_utilization_pct": utilization(n, total_capacity),
            "projects": {
                p.id: {
                    "assigned_count": headcount[p.id],
                    "min_capacity": p.min_capacity,
                    "max_capacity": p.max_capacity,
                    "is_active": headcount[p.id] > 0,
                    "utilization_pct": utilization(
                        headcount[p.id], p.max_capacity
                    ),
                }
                for p in projects
            },
        },
    }


def compare_two_solutions(
    solution_a: models.Solution,
    solution_b: models.Solution,
) -> dict[str, Any]:
    """Performs detailed trade-off comparison between two alternative solutions.

    In compliance with Section 7.4 of the specification, identifies:
    - Changed student allocations between solutions A and B.
    - Improved and worsened student preference ranks.
    - Deltas in mean skill-fit, mean rank, and Gini coefficient.
    - Human-readable trade-off summary statements.

    Args:
        solution_a: Baseline solution.
        solution_b: Alternative solution to compare against A.

    Returns:
        Dictionary documenting differences, changed assignments, and trade-offs:
        {
            "solution_a_id": str,
            "solution_b_id": str,
            "is_distinct": bool,
            "changed_students_count": int,
            "changed_assignments": list[dict[str, Any]],
            "delta_metrics": dict[str, Any],
            "trade_off_summary": list[str]
        }

    Deltas follow Section 4.1 of the analytical note (B minus A) and are read
    from each solution's indicators. A positive rank delta means a worse
    outcome for the student.
    """
    map_a = {a.student_id: a for a in solution_a.assignments}
    map_b = {b.student_id: b for b in solution_b.assignments}
    known_ranks = [
        a.preference_rank
        for a in solution_a.assignments + solution_b.assignments
        if a.preference_rank is not None
    ]
    # Unranked sorts below every stated preference.
    unranked_rank = max(known_ranks, default=0) + 1

    changed: list[dict[str, Any]] = []
    rank_improved = 0
    rank_worsened = 0
    for s_id, asg_a in map_a.items():
        asg_b = map_b.get(s_id)
        if asg_b is None or asg_a.project_id == asg_b.project_id:
            continue
        r_a = asg_a.preference_rank or unranked_rank
        r_b = asg_b.preference_rank or unranked_rank
        if r_b < r_a:
            rank_change = "IMPROVED"
            rank_improved += 1
        elif r_b > r_a:
            rank_change = "WORSENED"
            rank_worsened += 1
        else:
            rank_change = "SAME"
        changed.append(
            {
                "student_id": s_id,
                "student_name": s_id,
                "project_a": asg_a.project_id,
                "project_a_id": asg_a.project_id,
                "project_a_title": asg_a.project_id,
                "rank_a": asg_a.preference_rank,
                "skill_fit_a": asg_a.skill_fit_score,
                "project_b": asg_b.project_id,
                "project_b_id": asg_b.project_id,
                "project_b_title": asg_b.project_id,
                "rank_b": asg_b.preference_rank,
                "skill_fit_b": asg_b.skill_fit_score,
                "rank_delta": r_b - r_a,
                "rank_change": rank_change,
            }
        )

    eff_a = solution_a.indicators.get("efficiency", {})
    eff_b = solution_b.indicators.get("efficiency", {})
    fair_a = solution_a.indicators.get("fairness", {})
    fair_b = solution_b.indicators.get("fairness", {})

    def delta(a: dict[str, Any], b: dict[str, Any], key: str) -> float:
        return round(b.get(key, 0) - a.get(key, 0), 4)

    delta_metrics: dict[str, Any] = {
        "mean_skill_fit_delta": delta(eff_a, eff_b, "mean_skill_fit"),
        "mean_rank_delta": delta(fair_a, fair_b, "mean_rank"),
        "worst_rank_delta": delta(fair_a, fair_b, "worst_rank"),
        "gini_delta": delta(fair_a, fair_b, "rank_gini"),
        "unranked_count_delta": int(delta(fair_a, fair_b, "unranked_count")),
    }

    total = len(map_a)
    summary: list[str] = []
    if not changed:
        summary.append("Both solutions give every student the same project.")
    else:
        summary.append(
            f"{len(changed)} of {total} student(s) change project: "
            f"{rank_improved} get a better choice, {rank_worsened} a worse one."
        )
        fit_d = delta_metrics["mean_skill_fit_delta"]
        if fit_d:
            summary.append(
                f"Mean skill fit {'rises' if fit_d > 0 else 'falls'} by "
                f"{abs(fit_d):.4f}."
            )
        rank_d = delta_metrics["mean_rank_delta"]
        if rank_d:
            summary.append(
                f"Mean preference rank {'worsens' if rank_d > 0 else 'improves'}"
                f" by {abs(rank_d):.2f}."
            )
        worst_d = delta_metrics["worst_rank_delta"]
        if worst_d:
            summary.append(
                f"Worst assigned rank {'worsens' if worst_d > 0 else 'improves'}"
                f" by {abs(worst_d):g}."
            )

    return {
        "solution_a_id": solution_a.id,
        "solution_a_alt": solution_a.alternative_number,
        "solution_b_id": solution_b.id,
        "solution_b_alt": solution_b.alternative_number,
        "is_distinct": bool(changed),
        "changed_students_count": len(changed),
        "total_students": total,
        "changed_assignments": changed,
        "rank_improved_count": rank_improved,
        "rank_worsened_count": rank_worsened,
        "delta_metrics": delta_metrics,
        "delta_mean_skill_fit": delta_metrics["mean_skill_fit_delta"],
        "delta_mean_rank": delta_metrics["mean_rank_delta"],
        "delta_gini": delta_metrics["gini_delta"],
        "delta_unranked_count": delta_metrics["unranked_count_delta"],
        "trade_off_summary": summary,
    }

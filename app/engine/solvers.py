"""Mathematical optimization solvers and Strategy Pattern skeleton for TECH5.

In compliance with Section 5 and Section 8 of the TECH5 specification,
Team B is responsible for proposing and implementing an approved assignment
method (e.g. Integer Linear Programming, heuristic search, or stable matching).

This module defines the abstract strategy base class and the AssignmentEngine
that implements AssignmentEngineContract.
"""

import abc
import logging
from typing import Any
import uuid

import pulp

from app import config
from app.contract import contract
from app.domain import models
from app.domain import validation
from app.engine import metrics
from app.persistence import repositories


class AssignmentStrategy(abc.ABC):
    """Abstract Base Class for student-to-project allocation strategies.

    Team B should derive concrete strategy subclasses implementing specific
    objective functions (e.g. preference satisfaction, skill fit, balanced).
    """

    def __init__(
        self, name: str, description: str, min_difference: int = 1
    ) -> None:
        """Initializes the strategy with descriptive metadata.

        Args:
            name: Machine-readable identifier for the strategy.
            description: Human-readable explanation of the objective function.
            min_difference: Minimum number of students whose project must
                differ from every excluded solution (d in Section 2.2).
        """
        self.name = name
        self.description = description
        self.min_difference = min_difference
        # Tie-breaking constant, set per solve to 1 / (|S| + 1) (Section 2.2).
        self.epsilon = 0.0

    @abc.abstractmethod
    def calculate_cost_or_utility(
        self,
        student: models.Student,
        project: models.Project,
        max_preferences: int,
    ) -> float:
        """Computes objective utility or cost weight for assigning student to project.

        Args:
            student: The candidate student.
            project: The target semester project.
            max_preferences: Maximum number of preferences ranked in cohort.

        Returns:
            Numerical weight reflecting desirability in optimization objective.
        """

    def add_strategy_terms(
        self,
        model: pulp.LpProblem,
        x: dict[tuple[str, str], pulp.LpVariable],
        students: list[models.Student],
        projects: list[models.Project],
    ) -> pulp.LpAffineExpression:
        """Adds strategy-specific variables and constraints to the model.

        The default strategy adds nothing. Subclasses override this when their
        objective needs more than the per-pair coefficients, such as the
        worst-rank variable rho in Strategy 1.

        Args:
            model: The PuLP model under construction.
            x: Assignment variables keyed by (student_id, project_id).
            students: List of students in the cohort.
            projects: List of available semester projects.

        Returns:
            Extra terms to add to the objective function.
        """
        return pulp.LpAffineExpression()

    def solve(
        self,
        students: list[models.Student],
        projects: list[models.Project],
        fixed_assignments: list[models.FixedAssignment] | None = None,
        excluded_solutions: list[list[tuple[str, str]]] | None = None,
    ) -> tuple[str, list[models.Assignment], float | None, dict[str, Any]]:
        """Solves the assignment problem under this strategy's formulation.

        In accordance with Section 8 of the specification, must:
        - Assign students to projects respecting capacities [min_cap, max_cap].
        - Enforce each student receives exactly one project allocation.
        - Strictly preserve pre-allocated fixed assignments.
        - Support integer no-good cuts (excluded_solutions) to guarantee distinct
          Pareto alternatives.

        Args:
            students: List of students in the cohort.
            projects: List of available semester projects.
            fixed_assignments: Pre-assigned student-project pairs that must hold.
            excluded_solutions: Previous solution allocations to cut out.

        Returns:
            A tuple of (solver_status, assignments, objective_value, diagnostics).
            Assignments are empty unless solver_status is "Optimal".
        """
        fixed_pairs = {
            (fa.student_id, fa.project_id) for fa in (fixed_assignments or [])
        }
        student_ids = {s.id for s in students}
        project_ids = {p.id for p in projects}
        unknown_locks = [
            f"{s_id} -> {p_id}"
            for s_id, p_id in sorted(fixed_pairs)
            if s_id not in student_ids or p_id not in project_ids
        ]
        if unknown_locks:
            return (
                "Invalid",
                [],
                None,
                {
                    "solver_status": "Invalid",
                    "reasons": [
                        "Fixed assignment references unknown student or "
                        f"project: {lock}"
                        for lock in unknown_locks
                    ],
                },
            )

        # L: longest preference list in the cohort (Section 2.2).
        max_preferences = max(
            (pref.rank for s in students for pref in s.preferences), default=1
        )
        self.epsilon = 1.0 / (len(students) + 1)

        model = pulp.LpProblem(f"assignment_{self.name}", pulp.LpMaximize)
        x = {
            (s.id, p.id): pulp.LpVariable(f"x_{i}_{j}", cat=pulp.LpBinary)
            for i, s in enumerate(students)
            for j, p in enumerate(projects)
        }
        y = {
            p.id: pulp.LpVariable(f"y_{j}", cat=pulp.LpBinary)
            for j, p in enumerate(projects)
        }

        # Objective (Section 2.5): per-pair coefficients plus strategy terms.
        model.setObjective(
            pulp.lpSum(
                self.calculate_cost_or_utility(s, p, max_preferences)
                * x[s.id, p.id]
                for s in students
                for p in projects
            )
            + self.add_strategy_terms(model, x, students, projects)
        )

        # Constraint 1: every student receives exactly one project.
        for s in students:
            model += pulp.lpSum(x[s.id, p.id] for p in projects) == 1

        # Constraint 2: capacity bounds apply only to active projects.
        for p in projects:
            headcount = pulp.lpSum(x[s.id, p.id] for s in students)
            model += headcount >= p.min_capacity * y[p.id]
            model += headcount <= p.max_capacity * y[p.id]
            for s in students:
                model += x[s.id, p.id] <= y[p.id]

        # Constraint 3: administrative locks.
        for pair in fixed_pairs:
            model += x[pair] == 1

        # Constraint 4: an active project needs at least one qualified
        # student for each mandatory skill.
        for p in projects:
            for req in p.requirements:
                if req.is_mandatory:
                    qualified = [
                        s
                        for s in students
                        if s.get_skill_level(req.skill_id) >= req.minimum_level
                    ]
                    model += (
                        pulp.lpSum(x[s.id, p.id] for s in qualified)
                        >= y[p.id]
                    )

        # Constraint 5: no-good cuts against previously found allocations.
        for previous in excluded_solutions or []:
            model += (
                pulp.lpSum(x[pair] for pair in previous if pair in x)
                <= len(students) - self.min_difference
            )

        solver = pulp.PULP_CBC_CMD(
            msg=False, timeLimit=config.Config.PULP_TIME_LIMIT_SECONDS
        )
        model.solve(solver)
        status = pulp.LpStatus[model.status]
        diagnostics: dict[str, Any] = {
            "solver_status": status,
            "proven_optimal": model.sol_status == pulp.LpSolutionOptimal,
            "solve_time_seconds": round(model.solutionTime, 3),
            "num_variables": len(model.variables()),
            "num_constraints": len(model.constraints),
            "max_preferences": max_preferences,
            "epsilon": self.epsilon,
        }
        if model.status != pulp.LpStatusOptimal:
            return status, [], None, diagnostics

        assignments: list[models.Assignment] = []
        for s in students:
            for p in projects:
                if (x[s.id, p.id].value() or 0) > 0.5:
                    fit, unmet = metrics.calculate_assignment_skill_fit(s, p)
                    assignments.append(
                        models.Assignment(
                            student_id=s.id,
                            project_id=p.id,
                            is_fixed=(s.id, p.id) in fixed_pairs,
                            preference_rank=s.get_preference_rank(p.id),
                            skill_fit_score=fit,
                            unmet_requirements=unmet,
                        )
                    )
                    break
        diagnostics["active_projects"] = [
            p.id for p in projects if (y[p.id].value() or 0) > 0.5
        ]
        return status, assignments, pulp.value(model.objective), diagnostics


class AssignmentEngine(contract.AssignmentEngineContract):
    """Main Assignment Engine orchestrating validation, execution, and persistence.

    Implements the internal component contract (AssignmentEngineContract)
    connecting Component B to Component A.
    """

    def __init__(
        self, run_repo: repositories.RunRepository | None = None
    ) -> None:
        """Initializes the AssignmentEngine with persistence repositories.

        Args:
            run_repo: Optional repository for persisting runs and solutions.
        """
        self.run_repo = (
            run_repo if run_repo is not None else repositories.RunRepository()
        )
        self.strategies: dict[str, AssignmentStrategy] = {
            # Team B: Instantiate and register your custom strategies here
        }

    def validate_inputs(
        self, request: contract.RunRequest
    ) -> contract.ValidationOutcome:
        """Validates cohort and constraints before attempting optimization.

        Args:
            request: The run request containing students, projects, etc.

        Returns:
            ValidationOutcome with validity, feasibility, errors, and warnings.
        """
        val_result = validation.validate_cohort(
            students=request.students,
            projects=request.projects,
            skills=request.skills,
            fixed_assignments=request.fixed_assignments,
        )
        return contract.ValidationOutcome(
            is_valid=val_result.is_valid,
            is_feasible=val_result.is_feasible,
            errors=list(val_result.errors),
            warnings=list(val_result.warnings),
            infeasibility_reasons=list(val_result.infeasibility_reasons),
        )

    def execute_run(
        self, request: contract.RunRequest
    ) -> models.AssignmentRun:
        """Executes the assignment algorithm, calculates metrics, and persists run.

        In accordance with Section 8 of the specification, Team B must:
        1. Synchronize entities to maintain relational integrity.
        2. Validate cohort feasibility.
        3. Run assignment solver(s) to generate one or more distinct alternatives.
        4. Calculate indicators for each alternative using app.engine.metrics.
        5. Persist run and solutions via self.run_repo.
        6. Return populated models.AssignmentRun.

        Args:
            request: The run request containing students, projects, etc.

        Returns:
            The created AssignmentRun populated with alternative solutions.

        Raises:
            NotImplementedError: To be implemented by Team B.
        """
        raise NotImplementedError(
            "TODO (Team B): Implement execute_run in app/engine/solvers.py"
        )

    def run_assignment(
        self,
        students: list[models.Student],
        projects: list[models.Project],
        skills: list[models.Skill] | None = None,
        fixed_assignments: list[models.FixedAssignment] | None = None,
        strategy_name: str = "PREFERENCE",
        max_alternatives: int = 3,
        notes: str = "",
    ) -> models.AssignmentRun:
        """Convenience method delegating to execute_run via RunRequest.

        Args:
            students: Student profiles.
            projects: Project specifications.
            skills: Optional skills catalog.
            fixed_assignments: Optional pre-allocated locks.
            strategy_name: Strategy key name.
            max_alternatives: Max solutions to generate.
            notes: Administrative description or notes for the run.

        Returns:
            The created AssignmentRun.
        """
        req = contract.RunRequest(
            students=students,
            projects=projects,
            skills=skills or [],
            fixed_assignments=fixed_assignments or [],
            strategy_key=strategy_name,
            max_alternatives=max_alternatives,
            notes=notes,
        )
        return self.execute_run(req)

    def list_runs(self, limit: int = 20) -> list[models.AssignmentRun]:
        """Retrieves historical assignment runs from repository.

        Args:
            limit: Maximum number of runs to retrieve.

        Returns:
            List of historical AssignmentRun domain objects.
        """
        return self.run_repo.list_runs(limit=limit)

    def get_run(self, run_id: str) -> models.AssignmentRun | None:
        """Retrieves a specific run by identifier.

        Args:
            run_id: Unique run identifier.

        Returns:
            The AssignmentRun object, or None if not found.
        """
        return self.run_repo.get_run(run_id)

    def get_solution(self, solution_id: str) -> models.Solution | None:
        """Retrieves a specific solution and its student allocations.

        Args:
            solution_id: Unique solution identifier.

        Returns:
            The Solution object with assignments, or None if not found.
        """
        return self.run_repo.get_solution(solution_id)

    def compare_solutions(
        self, solution_a_id: str, solution_b_id: str
    ) -> models.RunComparison:
        """Compares two alternative solutions side-by-side using metrics module.

        Args:
            solution_a_id: Identifier of the baseline solution.
            solution_b_id: Identifier of the comparison solution.

        Returns:
            RunComparison containing delta metrics and changed assignments.

        Raises:
            KeyError: If either solution cannot be found.
        """
        sol_a = self.run_repo.get_solution(solution_a_id)
        sol_b = self.run_repo.get_solution(solution_b_id)
        if sol_a is None or sol_b is None:
            raise KeyError(
                f"Solutions not found: {solution_a_id}, {solution_b_id}"
            )
        comp_dict = metrics.compare_two_solutions(sol_a, sol_b)
        return models.RunComparison.from_dict(comp_dict)

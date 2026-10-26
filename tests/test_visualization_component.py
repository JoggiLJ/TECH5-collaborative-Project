"""Tests for Component A (Visualization & Recommendation) web workflows."""

import pathlib

import pytest

from app import create_app
from app.contract import contract
from app.contract import mocks
from app.domain import models
from app.engine import solvers
from app.persistence import repositories
from app.samples import demo_data


def test_dashboard_loads(tmp_path: pathlib.Path) -> None:
    """Verifies dashboard overview page rendering."""
    db_file = tmp_path / "test_ui_dash.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    dash_res = client.get("/")
    assert dash_res.status_code == 200
    assert b"TECH5" in dash_res.data


def test_role_switcher(tmp_path: pathlib.Path) -> None:
    """Verifies role switching in session."""
    db_file = tmp_path / "test_role.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    res = client.post(
        "/set-role", data={"role": "STUDENT"}, follow_redirects=True
    )
    assert res.status_code == 200
    assert b"Switched role to Student Viewer" in res.data


def test_student_and_fixed_assignment_workflow(
    tmp_path: pathlib.Path,
) -> None:
    """Verifies student and fixed-assignment creation workflows."""
    db_file = tmp_path / "test_stud_fixed.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    # Seed project P1 so student preference foreign key is valid
    repositories.ProjectRepository().save(
        models.Project(
            id="P1",
            title="FinTech Risk",
            min_capacity=1,
            max_capacity=2,
        )
    )

    # Create student
    res_stud = client.post(
        "/students/new",
        data={
            "id": "S1",
            "display_name": "Alice Chen",
            "preferences_text": "P1",
        },
        follow_redirects=True,
    )
    assert res_stud.status_code == 200
    assert b"Alice Chen" in res_stud.data

    # Create fixed assignment
    res_fixed = client.post(
        "/fixed-assignments/new",
        data={
            "student_id": "S1",
            "project_id": "P1",
            "status": "APPROVED",
            "reason": "Pre-matched",
        },
        follow_redirects=True,
    )
    assert res_fixed.status_code == 200
    assert b"Pre-matched" in res_fixed.data


def test_scenario_loading_and_optimization_trigger(
    tmp_path: pathlib.Path,
) -> None:
    """Verifies benchmark scenario loading, execution, and result views."""
    db_file = tmp_path / "test_scenario_run.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    # Load standard benchmark
    load_res = client.post("/load-scenario/standard", follow_redirects=True)
    assert load_res.status_code == 200
    assert b"Standard Cohort" in load_res.data

    # Trigger optimization run (falls back to mock engine if solver unimplemented)
    run_res = client.post(
        "/runs/trigger",
        data={
            "primary_strategy": "PREFERENCE",
            "max_alternatives": 3,
        },
        follow_redirects=True,
    )
    assert run_res.status_code == 200
    assert b"Optimization run completed" in run_res.data

    runs = repositories.RunRepository().list_runs(limit=1)
    assert len(runs) == 1
    run = runs[0]
    assert len(run.solutions) >= 1

    # View solution detail
    sol_id = run.solutions[0].id
    sol_res = client.get(f"/solutions/{sol_id}")
    assert sol_res.status_code == 200
    assert b"Student-to-Project Allocations" in sol_res.data

    # View recommendations
    recs_res = client.get(f"/recommendations/{run.id}")
    assert recs_res.status_code == 200
    assert b"Transparent Decision Recommendations" in recs_res.data
    assert b"Calculated Evidence" in recs_res.data
    assert b"Policy Advice" in recs_res.data


def test_create_student_preference_validation(
    tmp_path: pathlib.Path,
) -> None:
    """Verifies preference validation when creating a student."""
    db_file = tmp_path / "test_stud_pref_val.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    repositories.ProjectRepository().save(
        models.Project(
            id="P1",
            title="Project One",
            min_capacity=1,
            max_capacity=2,
        )
    )

    # 1. Invalid project preference should flash error and not crash
    res_invalid = client.post(
        "/students/new",
        data={
            "id": "S10",
            "display_name": "Test Student",
            "preferences_text": "P99, P100",
        },
        follow_redirects=True,
    )
    assert res_invalid.status_code == 200
    assert b"Invalid project ID(s) in preferences" in res_invalid.data

    # 2. Case-insensitive project preference should normalize and succeed
    res_valid = client.post(
        "/students/new",
        data={
            "id": "S10",
            "display_name": "Test Student",
            "preferences_text": "p1",
        },
        follow_redirects=True,
    )
    assert res_valid.status_code == 200
    assert b"created successfully" in res_valid.data

    saved = repositories.StudentRepository().get_by_id("S10")
    assert saved is not None
    assert len(saved.preferences) == 1
    assert saved.preferences[0].project_id == "P1"


def test_skills_crud_workflow(tmp_path: pathlib.Path) -> None:
    """Verifies skill addition workflow (Team A implementation)."""
    db_file = tmp_path / "test_skill.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    res = client.post(
        "/skills/new",
        data={
            "id": "py",
            "name": "Python",
            "description": "Python Programming",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    saved = repositories.SkillRepository().get_by_id("py")
    assert saved is not None
    assert saved.name == "Python"


def test_projects_crud_workflow(tmp_path: pathlib.Path) -> None:
    """Verifies project addition, edit, delete, and capacity validation."""
    db_file = tmp_path / "test_proj.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    # 1. Invalid capacity (min > max) should be rejected
    res_invalid = client.post(
        "/projects/new",
        data={
            "id": "P_INV",
            "title": "Invalid Capacity Project",
            "min_capacity": 5,
            "max_capacity": 2,
        },
        follow_redirects=True,
    )
    assert res_invalid.status_code == 200
    assert b"Minimum capacity cannot exceed maximum capacity" in res_invalid.data
    assert repositories.ProjectRepository().get_by_id("P_INV") is None

    # 2. Create project
    res = client.post(
        "/projects/new",
        data={
            "id": "P1",
            "title": "FinTech Risk",
            "description": "Risk analytics",
            "min_capacity": 1,
            "max_capacity": 2,
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"FinTech Risk" in res.data

    saved = repositories.ProjectRepository().get_by_id("P1")
    assert saved is not None
    assert saved.title == "FinTech Risk"
    assert saved.min_capacity == 1
    assert saved.max_capacity == 2

    # 3. Update project
    res_update = client.post(
        "/projects/P1/edit",
        data={
            "title": "FinTech Risk Advanced",
            "description": "Updated risk description",
            "min_capacity": 2,
            "max_capacity": 4,
        },
        follow_redirects=True,
    )
    assert res_update.status_code == 200
    assert b"FinTech Risk Advanced" in res_update.data

    updated = repositories.ProjectRepository().get_by_id("P1")
    assert updated is not None
    assert updated.title == "FinTech Risk Advanced"
    assert updated.min_capacity == 2
    assert updated.max_capacity == 4

    # 4. Delete project
    res_delete = client.post("/projects/P1/delete", follow_redirects=True)
    assert res_delete.status_code == 200
    assert b"removed" in res_delete.data
    assert repositories.ProjectRepository().get_by_id("P1") is None


def test_compare_solutions_view(tmp_path: pathlib.Path) -> None:
    """Verifies solution comparison controller and view."""
    db_file = tmp_path / "test_comp.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    # 1. Base view without query params renders with selection prompt
    empty_res = client.get("/compare")
    assert empty_res.status_code == 200
    assert b"Side-by-Side Solution Comparison" in empty_res.data
    assert b"Select two solutions above" in empty_res.data

    # 2. View with nonexistent IDs warns user gracefully
    missing_res = client.get(
        "/compare?sol1=NONEXISTENT_A&sol2=NONEXISTENT_B",
        follow_redirects=True,
    )
    assert missing_res.status_code == 200
    assert b"was not found" in missing_res.data

    # 3. View with two valid solutions displays comparative analysis (including Gini)
    scenario = demo_data.get_standard_scenario()
    mock_engine = mocks.MockAssignmentEngine()
    req = contract.RunRequest(
        students=scenario["students"],
        projects=scenario["projects"],
        skills=scenario["skills"],
        fixed_assignments=scenario["fixed_assignments"],
        max_alternatives=2,
    )
    run = mock_engine.execute_run(req)
    assert len(run.solutions) >= 2

    sol_a = run.solutions[0]
    sol_b = run.solutions[1]

    comp_res = client.get(
        f"/compare?sol1={sol_a.id}&sol2={sol_b.id}",
        follow_redirects=True,
    )
    assert comp_res.status_code == 200
    assert b"Side-by-Side Solution Comparison" in comp_res.data
    assert b"Changed Student Allocations" in comp_res.data
    assert b"Trade-off Findings" in comp_res.data
    assert b"Detailed Allocation Shifts" in comp_res.data
    assert b"Gini" in comp_res.data


def test_compare_solutions_with_real_engine(tmp_path: pathlib.Path) -> None:
    """Verifies side-by-side comparison with real AssignmentEngine from Team B."""
    db_file = tmp_path / "test_comp_real.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    scenario = demo_data.get_standard_scenario()
    engine = solvers.AssignmentEngine()
    req = contract.RunRequest(
        students=scenario["students"],
        projects=scenario["projects"],
        skills=scenario["skills"],
        fixed_assignments=scenario["fixed_assignments"],
        strategy_key="PREFERENCE",
        max_alternatives=2,
    )
    run = engine.execute_run(req)
    assert run.status == "COMPLETED"
    assert len(run.solutions) >= 2

    sol_a = run.solutions[0]
    sol_b = run.solutions[1]

    comp_res = client.get(
        f"/compare?sol1={sol_a.id}&sol2={sol_b.id}",
        follow_redirects=True,
    )
    assert comp_res.status_code == 200
    assert b"Side-by-Side Solution Comparison" in comp_res.data
    assert b"Changed Student Allocations" in comp_res.data
    assert b"Gini" in comp_res.data
    assert b"Average Skill Fit" in comp_res.data
    assert b"Average Preference Rank" in comp_res.data


def test_lock_and_rerun_workflow(tmp_path: pathlib.Path) -> None:
    """Verifies interactive student pinning and automatic solver rerun."""
    db_file = tmp_path / "test_lock_rerun.db"
    app = create_app({"TESTING": True, "DATABASE_PATH": db_file})
    client = app.test_client()

    # 1. Seed cohort data and run initial optimization (skills first, then projects, then students)
    scenario = demo_data.get_standard_scenario()
    stud_repo = repositories.StudentRepository()
    proj_repo = repositories.ProjectRepository()
    skill_repo = repositories.SkillRepository()

    for sk in scenario["skills"]:
        skill_repo.save(sk)
    for p in scenario["projects"]:
        proj_repo.save(p)
    for s in scenario["students"]:
        stud_repo.save(s)

    engine = solvers.AssignmentEngine()
    initial_req = contract.RunRequest(
        students=scenario["students"],
        projects=scenario["projects"],
        skills=scenario["skills"],
        strategy_key="PREFERENCE",
        max_alternatives=1,
    )
    initial_run = engine.execute_run(initial_req)
    assert len(initial_run.solutions) >= 1
    init_sol = initial_run.solutions[0]

    # Pick a student assignment from initial solution
    target_asg = init_sol.assignments[0]
    target_student = target_asg.student_id
    target_project = target_asg.project_id

    # 2. Trigger lock_and_rerun
    lock_res = client.post(
        f"/solutions/{init_sol.id}/lock-and-rerun",
        data={
            "student_id": target_student,
            "project_id": target_project,
        },
        follow_redirects=True,
    )
    assert lock_res.status_code == 200
    assert b"successfully locked" in lock_res.data

    # 3. Verify that fixed assignment was persisted
    fixed_repo = repositories.FixedAssignmentRepository()
    fixed_list = fixed_repo.list_all()
    locked_item = next(
        (f for f in fixed_list if f.student_id == target_student), None
    )
    assert locked_item is not None
    assert locked_item.project_id == target_project
    assert locked_item.status == "APPROVED"

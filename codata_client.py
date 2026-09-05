"""
Codata-backed data layer for the Hospital MockLine app.

Replaces the original SQLite (training.db) persistence with calls to the
Codata REST API, so data survives restarts/redeploys on any host (including
serverless platforms where local disk is ephemeral).

Every function here returns plain dicts / lists of dicts using the SAME
field names the original SQLite schema used (e.g. "employee_id", not
"employeeId"), so the rest of app.py and all templates work UNCHANGED.

Requires the CODATA_API_KEY environment variable to be set.
"""

import os
import time
import requests

WORKSPACE_ID = "6a9bee3505214bfab652a29b"
BASE_URL = f"https://api.codata.io/v0/workspace/{WORKSPACE_ID}/branch/main/api"
API_KEY = os.environ.get("CODATA_API_KEY", "")

_session = requests.Session()


def _headers():
    if not API_KEY:
        raise RuntimeError(
            "CODATA_API_KEY environment variable is not set. "
            "Create a key in the Codata dashboard and set it in your .env "
            "(local) or your host's environment variables (production)."
        )
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _request(method, path, params=None, json_body=None, retries=3):
    url = f"{BASE_URL}{path}"
    last_exc = None
    for attempt in range(retries):
        try:
            resp = _session.request(
                method, url, headers=_headers(), params=params, json=json_body, timeout=15
            )
            # The branch can be transiently "verifying" for ~30s right after a
            # spec change; treat 503 as retryable.
            if resp.status_code == 503 and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise CodataError(method, path, resp.status_code, resp.text)
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Codata request failed after {retries} attempts: {method} {path}") from last_exc


class CodataError(Exception):
    def __init__(self, method, path, status_code, body):
        self.method = method
        self.path = path
        self.status_code = status_code
        self.body = body
        super().__init__(f"{method} {path} -> {status_code}: {body}")


# ---------------------------------------------------------------------------
# Field-name mapping helpers (Codata uses camelCase; original app used
# snake_case). Converting here keeps every other file untouched.
# ---------------------------------------------------------------------------

def _manager_to_row(rec):
    if rec is None:
        return None
    return {
        "id": rec.get("id"),
        "manager_id": rec.get("managerId"),
        "username": rec.get("username"),
        "password": rec.get("password"),
        "location": rec.get("location"),
        "created_at": rec.get("createdAt"),
    }


def _manager_to_body(row):
    body = {}
    if "manager_id" in row:
        body["managerId"] = row["manager_id"]
    if "username" in row:
        body["username"] = row["username"]
    if "password" in row:
        body["password"] = row["password"]
    if "location" in row:
        body["location"] = row["location"]
    if "created_at" in row:
        body["createdAt"] = row["created_at"]
    return body


def _employee_to_row(rec):
    if rec is None:
        return None
    return {
        "id": rec.get("id"),
        "employee_id": rec.get("employeeId"),
        "name": rec.get("name"),
        "email": rec.get("email"),
        "department": rec.get("department"),
        "location": rec.get("location"),
        "password": rec.get("password"),
        "created_at": rec.get("createdAt"),
    }


def _employee_to_body(row):
    body = {}
    if "employee_id" in row:
        body["employeeId"] = row["employee_id"]
    if "name" in row:
        body["name"] = row["name"]
    if "email" in row:
        body["email"] = row.get("email") or "unset@example.com"
    if "department" in row:
        body["department"] = row["department"]
    if "location" in row:
        body["location"] = row["location"]
    if "password" in row:
        body["password"] = row["password"]
    if "created_at" in row:
        body["createdAt"] = row["created_at"]
    return body


def _scenario_to_row(rec):
    if rec is None:
        return None
    return {
        "id": rec.get("id"),
        "title": rec.get("title"),
        "description": rec.get("description"),
        "scenario_types": rec.get("scenarioTypes"),
        "communication_styles": rec.get("communicationStyles"),
        "language": rec.get("language"),
        "assigned_batch": rec.get("assignedBatch"),
        "assigned_employee_ids": rec.get("assignedEmployeeIds"),
        "randomize_order": rec.get("randomizeOrder"),
        "created_at": rec.get("createdAt"),
    }


def _scenario_to_body(row):
    body = {}
    mapping = {
        "title": "title",
        "description": "description",
        "scenario_types": "scenarioTypes",
        "communication_styles": "communicationStyles",
        "language": "language",
        "assigned_batch": "assignedBatch",
        "assigned_employee_ids": "assignedEmployeeIds",
        "randomize_order": "randomizeOrder",
        "created_at": "createdAt",
    }
    for src, dst in mapping.items():
        if src in row:
            body[dst] = row[src]
    return body


def _simulation_to_row(rec):
    if rec is None:
        return None
    return {
        "id": rec.get("id"),
        "employee_id": rec.get("employeeId"),
        "scenario_id": rec.get("scenarioId"),
        "batch_no": rec.get("batchNo"),
        "transcript": rec.get("transcript"),
        "soft_skills_score": rec.get("softSkillsScore"),
        "customer_critical_score": rec.get("customerCriticalScore"),
        "business_critical_score": rec.get("businessCriticalScore"),
        "overall_score": rec.get("overallScore"),
        "status": rec.get("status"),
        "completed_at": rec.get("completedAt"),
    }


def _simulation_to_body(row):
    body = {}
    mapping = {
        "employee_id": "employeeId",
        "scenario_id": "scenarioId",
        "batch_no": "batchNo",
        "transcript": "transcript",
        "soft_skills_score": "softSkillsScore",
        "customer_critical_score": "customerCriticalScore",
        "business_critical_score": "businessCriticalScore",
        "overall_score": "overallScore",
        "status": "status",
        "completed_at": "completedAt",
    }
    for src, dst in mapping.items():
        if src in row:
            body[dst] = row[src]
    return body


def _unwrap_list(payload):
    """Codata list endpoints may return either a bare array or {items:[...]} /
    {data:[...]}. Normalize to a plain list."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "records", "results"):
            if key in payload and isinstance(payload[key], list):
                return payload[key]
    return []


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

def list_managers():
    payload = _request("GET", "/managers", params={"limit": 500})
    return [_manager_to_row(r) for r in _unwrap_list(payload)]


def get_manager(manager_pk):
    rec = _request("GET", f"/managers/{manager_pk}")
    return _manager_to_row(rec)


def get_manager_by_username(username):
    for row in list_managers():
        if row["username"] == username:
            return row
    return None


def insert_manager(manager_id, username, password, location):
    body = _manager_to_body({
        "manager_id": manager_id,
        "username": username,
        "password": password,
        "location": location,
    })
    rec = _request("POST", "/managers", json_body=body)
    return _manager_to_row(rec)


def delete_manager(manager_pk):
    _request("DELETE", f"/managers/{manager_pk}")


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

def list_employees(location=None):
    payload = _request("GET", "/employees", params={"limit": 1000})
    rows = [_employee_to_row(r) for r in _unwrap_list(payload)]
    if location:
        rows = [r for r in rows if r["location"] == location]
    rows.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return rows


def get_employee(employee_pk):
    rec = _request("GET", f"/employees/{employee_pk}")
    return _employee_to_row(rec)


def get_employee_by_employee_id(employee_id):
    for row in list_employees():
        if row["employee_id"] == employee_id:
            return row
    return None


def insert_employee(employee_id, name, email, department, location, password):
    body = _employee_to_body({
        "employee_id": employee_id,
        "name": name,
        "email": email,
        "department": department,
        "location": location,
        "password": password,
    })
    rec = _request("POST", "/employees", json_body=body)
    return _employee_to_row(rec)


def update_employee_password(employee_pk, new_password):
    rec = _request("PUT", f"/employees/{employee_pk}", json_body={"password": new_password})
    return _employee_to_row(rec)


def delete_employee(employee_pk):
    _request("DELETE", f"/employees/{employee_pk}")


# ---------------------------------------------------------------------------
# Call scenarios
# ---------------------------------------------------------------------------

def list_scenarios(assigned_batch=None):
    payload = _request("GET", "/callScenarios", params={"limit": 1000})
    rows = [_scenario_to_row(r) for r in _unwrap_list(payload)]
    if assigned_batch:
        rows = [r for r in rows if r["assigned_batch"] == assigned_batch]
    rows.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return rows


def get_scenario(scenario_pk):
    rec = _request("GET", f"/callScenarios/{scenario_pk}")
    return _scenario_to_row(rec)


def insert_scenario(**fields):
    body = _scenario_to_body(fields)
    rec = _request("POST", "/callScenarios", json_body=body)
    return _scenario_to_row(rec)


# ---------------------------------------------------------------------------
# Call simulations
#
# NOTE: Codata is currently missing the collection-level GET /callSimulations
# (list) endpoint for this asset (platform bug, reported as ticket SUP-13).
# Individual create/get/update/delete all work. Until that's fixed,
# list_simulations() below returns an empty list rather than pretending to
# have data it can't fetch -- features relying on it (an employee's call
# history/average score, the manager results page, the admin submissions
# report) will show "no data yet" until Codata resolves SUP-13.
# ---------------------------------------------------------------------------

CALLSIMULATION_LIST_BROKEN = True  # flip to False once SUP-13 is fixed


def list_simulations(employee_id=None, scenario_id=None):
    if CALLSIMULATION_LIST_BROKEN:
        return []
    payload = _request("GET", "/callSimulations", params={"limit": 1000})
    rows = [_simulation_to_row(r) for r in _unwrap_list(payload)]
    if employee_id:
        rows = [r for r in rows if r["employee_id"] == employee_id]
    if scenario_id:
        rows = [r for r in rows if r["scenario_id"] == scenario_id]
    rows.sort(key=lambda r: r["completed_at"] or "", reverse=True)
    return rows


def get_simulation(simulation_pk):
    rec = _request("GET", f"/callSimulations/{simulation_pk}")
    return _simulation_to_row(rec)


def insert_simulation(**fields):
    body = _simulation_to_body(fields)
    rec = _request("POST", "/callSimulations", json_body=body)
    return _simulation_to_row(rec)


def average_score(employee_id):
    """Returns average overall_score for an employee, or None.
    Degrades gracefully while SUP-13 (missing list endpoint) is open."""
    rows = list_simulations(employee_id=employee_id)
    scores = [r["overall_score"] for r in rows if r["overall_score"] is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)

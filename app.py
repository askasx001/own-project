
import json

import os

from urllib.error import URLError

from urllib.request import Request, urlopen

from pathlib import Path

import openpyxl

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify

import codata_client as db

app = Flask(__name__)

app.secret_key = "admin-panel-secret-key-change-me"

ADMIN_USERNAME = "admin"

ADMIN_PASSWORD = "admin123"

# Indian States

INDIAN_STATES = [

    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",

    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",

    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",

    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",

    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",

    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir",

    "Ladakh", "Puducherry"

]

# Manager credentials - username -> (password, location)

MANAGERS = {

    "manager_delhi": ("manager_delhi123", "Delhi"),

    "manager_mumbai": ("manager_mumbai123", "Maharashtra"),

    "manager_bangalore": ("manager_bangalore123", "Karnataka"),

}

def get_general_scenario_options():

    default_options = [

        "Complaint",

        "Billing Issue",

        "Technical Support",

        "Account Query",

        "Service Recovery",

        "Retention Call",

    ]

    project_root = Path(__file__).resolve().parent

    workbook_candidates = [

        project_root / "templates" / "general scenarios.xlsx",

        project_root / "general scenarios.xlsx",

    ]

    workbook_path = next((path for path in workbook_candidates if path.exists()), None)

    if workbook_path is None:

        return default_options

    try:

        workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)

        sheet = workbook.active

        categories = []

        seen = set()

        skip_labels = {"category", "s no", "call scenarios", "solution"}

        for row in sheet.iter_rows(min_row=1, max_col=2, values_only=True):

            if len(row) < 2 or row[1] is None:

                continue

            category = str(row[1]).strip()

            if not category or category.lower() in skip_labels or category in seen:

                continue

            seen.add(category)

            categories.append(category)

        workbook.close()

        if categories:

            return categories

    except Exception:

        pass

    return default_options

@app.context_processor

def inject_states():

    return {

        'indian_states': INDIAN_STATES,

        'general_scenario_options': get_general_scenario_options(),

    }

@app.before_request

def require_login():

    # Public site protection - allow login/logout and static files without authentication

    allowed_unauthenticated = ["/", "/login", "/logout", "/manager/login", "/manager/logout", "/admin/login", "/admin/logout", "/static"]

   

    if not any(request.path.startswith(path) for path in allowed_unauthenticated):

        # Check if this is a manager route

        if request.path.startswith("/manager"):

            if not session.get("manager_logged_in"):

                return redirect(url_for("unified_login"))

        # Check if this is an admin route

        elif request.path.startswith("/admin"):

            if not session.get("admin_logged_in"):

                return redirect(url_for("unified_login"))

        # Check if this is a public route

        else:

            if not session.get("public_logged_in"):

                return redirect(url_for("unified_login"))

def get_manager_accounts():

    rows = db.list_managers()

    return {row["username"]: (row["password"], row["location"], row["manager_id"]) for row in rows}

def get_employee_account(employee_id):

    row = db.get_employee_by_employee_id(employee_id)

    if not row:

        return None

    return {"employee_id": row["employee_id"], "password": row["password"], "location": row["location"]}

def ensure_database():

    # Data now lives in Codata (see codata_client.py) instead of local SQLite,

    # so there is nothing to initialize on disk. Seed sample accounts once,

    # idempotently, so a brand-new Codata workspace behaves like a fresh install.

    if not db.list_managers():

        for username, (password, location) in MANAGERS.items():

            manager_id = f"MGR-{location[:3].upper()}-{username[-2:]}"

            db.insert_manager(manager_id, username, password, location)

    if not db.list_employees():

        sample_employees = [

            ("EMP-DEL-01", "Aarav Sharma", "aarav.sharma@example.com", "Support", "Delhi", "agent123"),

            ("EMP-MUM-01", "Priya Nair", "priya.nair@example.com", "Support", "Maharashtra", "agent123"),

            ("EMP-BLR-01", "Rohan Gupta", "rohan.gupta@example.com", "Support", "Karnataka", "agent123"),

        ]

        for employee_id, name, email, department, location, password in sample_employees:

            db.insert_employee(employee_id, name, email, department, location, password)

ensure_database()

# ---------- Unified Login Route ----------

@app.route("/", methods=["GET", "POST"])

def unified_login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()

        password = request.form.get("password", "")

        manager_accounts = get_manager_accounts()

        # Check if admin

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session.clear()

            session["admin_logged_in"] = True

            flash("Logged in as Admin.", "success")

            return redirect(url_for("admin_dashboard"))

        # Check if manager

        if username in manager_accounts and manager_accounts[username][0] == password:

            session.clear()

            session["manager_logged_in"] = True

            session["manager_username"] = username

            session["manager_location"] = manager_accounts[username][1]

            flash(f"Logged in as Manager - {manager_accounts[username][1]}.", "success")

            return redirect(url_for("manager_dashboard"))

        employee_account = get_employee_account(username)

        if employee_account and employee_account["password"] == password:

            session.clear()

            session["public_logged_in"] = True

            session["employee_id"] = employee_account["employee_id"]

            flash("Logged in to MockLine.", "success")

            return redirect(url_for("mockline_dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("unified_login.html")

# ---------- Public auth routes ----------

@app.route("/login", methods=["GET", "POST"])

def public_login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()

        password = request.form.get("password", "")

        employee_account = get_employee_account(username)

        if employee_account and employee_account["password"] == password:

            session.clear()

            session["public_logged_in"] = True

            session["employee_id"] = employee_account["employee_id"]

            flash("Logged in successfully.", "success")

            return redirect(url_for("mockline_dashboard"))

        flash("Invalid employee ID or password.", "error")

    return render_template("login.html", login_type="public")

@app.route("/logout")

def public_logout():

    session.pop("public_logged_in", None)

    flash("Logged out successfully.", "success")

    return redirect(url_for("unified_login"))

# ---------- Manager auth routes ----------

@app.route("/manager/login", methods=["GET", "POST"])

def manager_login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()

        password = request.form.get("password", "")

        manager_accounts = get_manager_accounts()

        if username in manager_accounts and manager_accounts[username][0] == password:

            session.clear()

            session["manager_logged_in"] = True

            session["manager_username"] = username

            session["manager_location"] = manager_accounts[username][1]

            flash("Logged in successfully.", "success")

            return redirect(url_for("manager_dashboard"))

        flash("Invalid manager username or password.", "error")

    return render_template("login.html", login_type="manager")

@app.route("/manager/logout")

def manager_logout():

    session.pop("manager_logged_in", None)

    session.pop("manager_username", None)

    session.pop("manager_location", None)

    flash("Logged out successfully.", "success")

    return redirect(url_for("unified_login"))

# ---------- Manager routes ----------

@app.route("/manager")

def manager_dashboard():

    if not session.get("manager_logged_in"):

        return redirect(url_for("manager_login"))

    manager_location = session.get("manager_location")

    employees = db.list_employees(location=manager_location)

    assignments = db.list_scenarios(assigned_batch=manager_location)

    return render_template("manager_dashboard.html", employees=employees, assignments=assignments, location=manager_location)

@app.route("/manager/mockline", methods=["GET", "POST"])

def manager_mockline():

    if not session.get("manager_logged_in"):

        return redirect(url_for("manager_login"))

    manager_location = session.get("manager_location")

    employees = db.list_employees(location=manager_location)

    if request.method == "POST":

        title = request.form.get("title", "Mock call").strip() or "Mock call"

        scenarios = request.form.getlist("scenario_types")

        communication_styles = request.form.getlist("communication_styles")

        assignment_scope = request.form.get("assignment_scope", "selected")

        assigned_employees = request.form.getlist("assigned_employees")

        randomize_order = request.form.get("randomize_order") == "on"

        batch_no = request.form.get("batch_no", manager_location).strip() or manager_location

        language = request.form.get("language", "English").strip() or "English"

        if not scenarios:

            flash("Please select at least one scenario type.", "error")

            return render_template("manager_mockline.html", employees=employees, location=manager_location, general_scenario_options=get_general_scenario_options())

        if not communication_styles:

            flash("Please select at least one communication tone.", "error")

            return render_template("manager_mockline.html", employees=employees, location=manager_location, general_scenario_options=get_general_scenario_options())

        if assignment_scope == "all":

            assigned_employees = [emp["employee_id"] for emp in employees]

        if not assigned_employees:

            flash("Please select at least one employee or choose everyone in this location.", "error")

            return render_template("manager_mockline.html", employees=employees, location=manager_location, general_scenario_options=get_general_scenario_options())

        display_title = f"{title} ({batch_no})" if batch_no and batch_no != manager_location else title

        assigned_employee_ids_json = json.dumps(assigned_employees) if assigned_employees else None

        # Each scenario/tone pair is one call for every selected employee.

        combination_count = 0

        for scenario in scenarios:

            for style in communication_styles:

                db.insert_scenario(

                    title=display_title,

                    description=f"Assigned by {session.get('manager_username', 'Manager')} | Batch: {batch_no}",

                    scenario_types=scenario,

                    communication_styles=style,

                    language=language,

                    assigned_batch=manager_location,

                    assigned_employee_ids=assigned_employee_ids_json,

                    randomize_order=randomize_order,

                )

                combination_count += 1

        total_calls = combination_count * len(assigned_employees)

        order_message = " in random order" if randomize_order else ""

        flash(f"Mock calls assigned successfully! {combination_count} scenario/tone combinations × {len(assigned_employees)} employees = {total_calls} total mock calls{order_message}.", "success")

        return redirect(url_for("manager_mockline"))

    assignments = db.list_scenarios(assigned_batch=manager_location)

    return render_template("manager_mockline.html", employees=employees, assignments=assignments, location=manager_location)

def _build_mock_report(answer_text, assigned_mock=None):

    response = (answer_text or "").strip()

    text = response.lower()

    has = lambda *markers: any(marker in text for marker in markers)

    customer_issue = (assigned_mock["scenario_types"] if assigned_mock else "the customer's issue") or "the customer's issue"

    rude = has("shut up", "be quiet", "go away", "whatever", "i don't care", "leave me alone")

    booking = has("book", "appointment", "slot", "availability", "alternate")

    probing = has("may i know", "could you", "can you tell", "when", "which", "what", "how long", "confirm")

    hold = has("hold", "one moment", "bear with me", "transfer")

    scores = []

    def quote(*markers):

        for sentence in response.replace("\n", " ").split("."):

            if any(marker in sentence.lower() for marker in markers):

                return sentence.strip()[:180]

        return response[:180]

    def add(category, name, weight, fatal, met, evidence, coaching, applicable=True, markers=()):

        score = "N/A" if not applicable else (100 if met else 0)

        if applicable and met and response:

            evidence = f'{evidence} Evidence: "{quote(*(markers or ())) }".'

        scores.append({"category": category, "name": name, "weight": weight, "fatal": fatal, "met": bool(met), "score": score, "applicable": applicable, "fatal_violation": bool(fatal and applicable and not met), "evidence": evidence, "coaching": coaching})

    business = "Critical to Business"

    add(business, "Intent to Convert", 5, True, booking, "Booking language found." if booking else "No appointment or alternate-slot offer found.", "Offer an appointment or a suitable alternate slot.")

    add(business, "Objection Handling Vs Offering Appropriate Rebuttals", 5, True, has("understand", "however", "alternative", "instead", "available"), "Reassurance or an alternative was offered." if has("understand", "however", "alternative", "instead", "available") else "No objection rebuttal found.", "Acknowledge the objection and offer a relevant alternative.")

    add(business, "Effective/Relevant Probing", 5, True, probing, "Questions or clarification language found." if probing else "No relevant probing question found.", "Ask focused questions about the customer's need.")

    add(business, "Showcase USPs/Benefits of the Product", 5, True, has("doctor", "specialist", "world-class", "benefit", "package", "expertise", "facility"), "A product, doctor, package, or benefit was mentioned." if has("doctor", "specialist", "world-class", "benefit", "package", "expertise", "facility") else "No product benefit or USP found.", "Explain a relevant product benefit or healthcare USP.")

    add(business, "Effective Call-back Scheduling", 5, True, has("call back", "callback", "preferred time", "preferred date"), "Callback scheduling language found." if has("call back", "callback", "preferred time", "preferred date") else "No callback scheduling found.", "Capture a preferred callback date and time when needed.")

    add(business, "Effective Upselling or Cross-selling", 5, True, has("also", "additional", "package", "health check", "consultation", "recommend"), "Additional service language found." if has("also", "additional", "package", "health check", "consultation", "recommend") else "No cross-sell or upsell found.", "Offer a relevant additional service without losing focus.")

    add(business, "Need Creation/Urgency Creation", 5, True, has("limited", "urgent", "today", "available now", "avoid delay", "don't miss"), "Urgency or availability language found." if has("limited", "urgent", "today", "available now", "avoid delay", "don't miss") else "No need or urgency creation found.", "Explain the benefit of acting now when appropriate.")

    add(business, "Appropriate Call Disposition & Description", 5, True, has("remarks", "disposition", "category", "request recorded", "noted"), "Disposition or case-note language found." if has("remarks", "disposition", "category", "request recorded", "noted") else "No disposition or remarks language found.", "Record clear remarks and select the correct disposition.")

    customer = "Critical to Customer"

    add(customer, "Answered all the Potential Queries raised by Customer", 7.5, False, has("answer", "explain", "certainly", "i can help", "confirm", "appointment"), "The response addresses or confirms the customer's request." if has("answer", "explain", "certainly", "i can help", "confirm", "appointment") else "The response does not clearly answer the customer's request.", "Answer every question clearly before closing.")

    soft = "Soft Skill"

    add(soft, "Personalization", 5, False, has("sir", "madam", "mr", "ms", "your name"), "A personal form of address was used." if has("sir", "madam", "mr", "ms", "your name") else "No personalization was detected.", "Use the caller's name when available.")

    add(soft, "Rapport Building/Two-way Communication", 5, False, probing and has("thank", "appreciate", "understand", "please"), "Questions and rapport language were detected." if probing and has("thank", "appreciate", "understand", "please") else "Limited evidence of two-way rapport.", "Ask, listen, acknowledge, and respond naturally.")

    add(soft, "Rate of Speech", 5, False, False, "Audio timing is not available in this text transcript.", "Maintain a moderate pace and concise sentences.", applicable=False)

    add(soft, "Pronunciation", 2.5, False, False, "Audio is not available to verify pronunciation.", "Pronounce names, specialties, and investigations clearly.", applicable=False)

    add(soft, "Tone of Voice/Voice Modulation", 5, False, has("please", "certainly", "of course", "understand", "happy"), "Polite or reassuring language suggests an appropriate tone." if has("please", "certainly", "of course", "understand", "happy") else "No positive tone markers found.", "Use a pleasant, scenario-appropriate tone.")

    add(soft, "Fumbling/Fillers/Dead-air/Too Many Pauses", 2.5, False, not has("um um", "uh uh", "...", "hmm hmm"), "No repeated filler pattern detected." if not has("um um", "uh uh", "...", "hmm hmm") else "Repeated fillers or pauses detected.", "Avoid fillers, dead air, and unnecessary pauses.")

    add(soft, "Acknowledgement/Active Listening/Comprehension", 5, False, has("understand", "i hear", "confirm", "let me make sure", "i see"), "Acknowledgement or confirmation language found." if has("understand", "i hear", "confirm", "let me make sure", "i see") else "No active-listening acknowledgement found.", "Acknowledge the concern and confirm understanding.")

    add(soft, "Hold/Call Transfer Procedure", 5, False, has("please hold", "thank you for holding", "welcome back", "refresh"), "Hold language includes a procedure." if has("please hold", "thank you for holding", "welcome back", "refresh") else "No hold or transfer was used in this call.", "Use hold permission, refresh the caller, and return promptly.", applicable=hold)

    add(soft, "Grammar", 5, False, bool(response) and not has("i is", "you was", "we is"), "No obvious grammar pattern was detected." if response and not has("i is", "you was", "we is") else "Incomplete or grammatically incorrect wording detected.", "Use complete, grammatically correct sentences.")

    compliance = "Compliance"

    add(compliance, "Brand Establishment & Introduction", 2.5, False, has("welcome", "speaking", "support", "hospital"), "Introduction or service identity was mentioned." if has("welcome", "speaking", "support", "hospital") else "No introduction or brand/service identity found.", "State your name and the service identity at the start.")

    add(compliance, "Reason for the Call", 2.5, False, has("calling", "regarding", "because", "appointment", "issue"), "A reason for contact was stated." if has("calling", "regarding", "because", "appointment", "issue") else "No reason for the call found.", "State the reason for the call clearly when applicable.")

    add(compliance, "Permission to Continue", 2.5, False, has("may i", "is it okay", "shall we", "can we continue"), "Permission language was found." if has("may i", "is it okay", "shall we", "can we continue") else "No permission-to-continue language found.", "Ask permission before continuing an outbound call.")

    add(compliance, "Summarisation/Further Assistance and Call Closing", 2.5, False, has("to summarize", "in summary", "anything else", "further assistance", "thank you for calling"), "Summary, further assistance, or closing language found." if has("to summarize", "in summary", "anything else", "further assistance", "thank you for calling") else "No summary or compliant closing found.", "Summarize the outcome, ask if anything else is needed, and close politely.")

    add(compliance, "Rude Behaviour/Call Disconnection/Sarcastic/Unprofessional Language", 2.5, True, not rude, "No rude or unprofessional language detected." if not rude else "Rude or unprofessional language was detected.", "Remain respectful and never disconnect or use sarcastic language.")

    category_scores = {}

    for category in {item["category"] for item in scores}:

        category_items = [item for item in scores if item["category"] == category and item["applicable"]]

        category_scores[category] = round(sum(item["score"] * item["weight"] for item in category_items) / sum(item["weight"] for item in category_items), 1) if category_items else "N/A"

    applicable_scores = [item for item in scores if item["applicable"]]

    applicable_weight = sum(item["weight"] for item in applicable_scores)

    weighted_score = round(sum(item["score"] * item["weight"] for item in applicable_scores) / applicable_weight, 1) if applicable_weight else 0

    fatal_violations = [item["name"] for item in scores if item["fatal_violation"]]

    fatal_flag = bool(fatal_violations)

    final_score = 0 if fatal_flag else weighted_score

    failed_items = [item for item in scores if item["applicable"] and not item["met"]]

    main_points = [item["coaching"] for item in failed_items[:4]] or ["Maintain the current standard across all evaluated parameters."]

    return {

        "soft_skills_score": category_scores[soft],

        "business_critical_score": category_scores[business],

        "customer_critical_score": category_scores[customer],

        "overall_score": final_score,

        "final_weighted_score": final_score,

        "category_scores": category_scores,

        "parameters": scores,

        "fatal_flag": fatal_flag,

        "fatal_violations": fatal_violations,

        "verdict": "Fail" if fatal_flag else ("Pass" if final_score >= 70 else "Fail"),

        "agent_behavior": "Professional and compliant" if not fatal_flag else "Fatal compliance issue detected",

        "manager_summary": f"Call summary: {response[:220] if response else 'No answer captured.'} Final weighted score: {final_score:.1f}%. " + (f"Fatal parameter failed: {', '.join(fatal_violations)}." if fatal_flag else "No fatal parameter was violated."),

        "main_points": main_points,

        "answer_preview": response[:220] if response else "No answer captured.",

    }

def _generate_ai_customer_reply(answer, issue, tone, conversation, language="English"):

    ollama_url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")

    ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")

    ollama_timeout = int(os.environ.get("OLLAMA_TIMEOUT", "120"))

    history_lines = []

    for item in conversation[-4:]:

        role = item.get("role", "")

        text = (item.get("text") or "").strip()

        if not text:

            continue

        speaker = "CUSTOMER" if role in {"customer", "caller"} else "EMPLOYEE"

        history_lines.append(f"{speaker}: {text[:320]}")

    history = "\n".join(history_lines)

    realism_guidance = """Speak like an ordinary person on a real phone call. Explain your own situation, answer the employee's questions, ask for clarification when needed, and react naturally to delays, misunderstandings, empathy, or rude language. Stay focused on your personal problem and do not sound scripted. Never take an action, process a request, check a system, arrange anything, or offer help to another person."""

    system_prompt = f"""You are the CUSTOMER in a hospital call-centre training exercise.

Your entire response must be Jagdish's spoken words. The other person is a hospital employee helping you. You are not staff and you do not work for the hospital.

Never speak for the employee. Never give the employee instructions, advice, scores, feedback, or a solution. Never claim to check, process, arrange, transfer, or complete anything. Only describe your own needs, answer questions about yourself, or ask a natural question as the caller.

Sound like a genuine caller in a live phone conversation. Do not introduce yourself by name or explain that you are a customer. Do not mention the simulation, these instructions, the prompt, or that the agent has answered.

Customer issue: {issue}

Customer personality/tone: {tone}

Reply in this language: {language}.

Behavior guidance: {realism_guidance}

"""

    user_prompt = f"""Write only the CUSTOMER'S next spoken reply. Never write the employee's words or describe what the employee should do.

The text after EMPLOYEE'S LATEST WORDS is the hospital employee's message. React to it as a customer; do not repeat it and do not answer as the employee.

Conversation so far:

{history or '(The call has just started.)'}

    EMPLOYEE'S LATEST WORDS:

{answer}

    Reply with only the customer's next spoken words, in 1-2 short natural sentences. Start directly with the customer's personal reaction. Do not act as staff, a receptionist, an assistant, a trainer, or an evaluator. Do not offer help, give instructions, process requests, check systems, or tell the employee what to do. If asked a question, answer only from the customer's point of view. If the employee is rude, react as a real customer would. Do not end the call automatically and do not mention these instructions."""

    payload = json.dumps({

        "model": ollama_model,

        "messages": [

            {"role": "system", "content": system_prompt},

            {"role": "user", "content": user_prompt},

        ],

        "stream": False,

        "keep_alive": "10m",

        "options": {

            "num_predict": 24,

            "num_ctx": 2048,

            "temperature": 0.35,

            "top_p": 0.85,

            "repeat_penalty": 1.1,

        },

    }).encode("utf-8")

    try:

        request_obj = Request(ollama_url, data=payload, headers={"Content-Type": "application/json"})

        with urlopen(request_obj, timeout=ollama_timeout) as response:

            result = json.loads(response.read().decode("utf-8"))

        reply = (result.get("message", {}).get("content") or result.get("response") or "").strip()

        normalized_reply = " ".join(reply.lower().split())

        normalized_answer = " ".join(answer.lower().split())

        role_script_markers = [

            "employee:", "customer:", "caller:", "agent:",

            "employee's latest words", "conversation so far", "assistant:",

            "thank you for your patience, sir", "i'll provide the area",

            "i will provide the area", "please hold while i",

        ]

        agent_markers = [

            "as the agent", "the agent should", "you should", "hospital representative:",

            "as a receptionist", "as an assistant", "as a trainer", "as an evaluator",

            "here is my advice", "my feedback", "your score", "i recommend that you",

            "how can i assist", "how may i assist", "how can i help you", "how may i help you",

            "what can i do for you", "thank you for contacting us", "i'm jagdish", "i am jagdish",

            "i am a customer", "the hospital agent has just answered", "the hospital agent",

            "as a customer", "in this simulation", "as a hospital employee", "as an employee",

            "the employee should", "the employee needs to", "please provide the following",

            "let me check", "let me verify", "let me book", "let me arrange", "let me transfer",

            "let's check", "let's verify", "please provide it", "for processing",

            "i will check the status", "i will process", "i will arrange", "i will transfer",

            "so we can proceed", "so we can process", "we can proceed", "we can process",

            "please wait while i check", "while i check the", "check the ambulance status",

            "i can't assist with that", "i cannot assist with that",

            "is there anything urgent that needs immediate attention",

        ]

        if (

            not reply

            or normalized_reply == normalized_answer

            or any(marker in normalized_reply for marker in role_script_markers)

            or any(marker in normalized_reply for marker in agent_markers)

        ):

            app.logger.warning("Ollama returned non-customer text; rejecting reply")

            return None

        return reply[:1000]

    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as error:

        app.logger.warning("Ollama customer reply failed: %s", error)

        return None

def _customer_opening(issue, tone, language):

    opening = _generate_ai_customer_reply(

        "Begin the call naturally by explaining why you called, in your own words.", issue, tone, [], language

    )

    if opening:

        return opening

    return f"I am calling because I need help with {issue.lower()}. Could you please tell me what I should do?"

def _customer_fallback(issue, tone, turn):

    if "angry" in tone or "frustrated" in tone or "impatient" in tone:

        replies = [

            f"I have been trying to get help with {issue.lower()} for a while, and I am getting frustrated.",

            "I understand, but I really need a clear answer because this is becoming urgent for me.",

            "Alright, I will wait, but please do not leave me without an update.",

        ]

    elif "confused" in tone or "uncertain" in tone:

        replies = [

            f"I am not sure I understand. I am calling about {issue.lower()}.",

            "Could you explain that once more in simple terms? I do not want to get anything wrong.",

            "Okay, I think I understand now. Is there anything else you need to know from me?",

        ]

    else:

        replies = [

            f"Yes, I am calling because I need help with {issue.lower()}.",

            "That makes sense. Could you tell me a little more about what I can expect?",

            "Thank you, that answers my question. I appreciate your help.",

        ]

    return replies[min(turn, len(replies) - 1)]

@app.route("/manager/results")

def manager_results():

    if not session.get("manager_logged_in"):

        return redirect(url_for("manager_login"))

    manager_location = session.get("manager_location")

    assigned_employees = db.list_employees(location=manager_location)

    employees_by_id = {emp["employee_id"]: emp for emp in assigned_employees}

    # NOTE: db.list_simulations() currently returns [] because Codata is

    # missing the collection-level list endpoint for CallSimulation

    # (platform bug, ticket SUP-13). This page will show "no data yet"

    # until Codata resolves that; scores/calls are still being recorded

    # correctly via db.insert_simulation(), just not listable yet.

    mock_reports = []

    for sim in db.list_simulations():

        emp = employees_by_id.get(sim["employee_id"])

        if not emp:

            continue

        row = dict(sim)

        row["employee_name"] = emp["name"]

        mock_reports.append(row)

    if not mock_reports:

        return render_template("manager_results.html", mock_reports=[], location=manager_location)

    formatted_mock_reports = []

    for row in mock_reports:

        try:

            transcript = json.loads(row.get("transcript") or "{}") if row.get("transcript") else {}

        except Exception:

            transcript = {}

        row["manager_summary"] = transcript.get("manager_summary") or "No summary recorded"

        row["main_points"] = transcript.get("main_points") or ["No summary recorded"]

        row["answer_preview"] = transcript.get("answer_preview") or "No answer captured"

        row["conversation"] = transcript.get("conversation") or []

        formatted_mock_reports.append(row)

    return render_template("manager_results.html", mock_reports=formatted_mock_reports, location=manager_location)

# ---------- Agent-facing routes ----------

@app.route("/employee")

def employee_dashboard():

    if not session.get("public_logged_in"):

        return redirect(url_for("public_login"))

    employee_id = session.get("employee_id")


    employee = db.get_employee_by_employee_id(employee_id)

    queued_calls = []

    previous_calls = []

    average_score = 0

    selected_scenario = request.args.get("scenario", "").strip()

    selected_date = request.args.get("date", "").strip()

    scenario_options = []

    date_options = []

    if employee:

        def _assigned_to_me(scn):

            try:

                ids = json.loads(scn["assigned_employee_ids"] or "[]")

            except Exception:

                ids = []

            return employee_id in ids

        all_scenarios = db.list_scenarios()

        my_scenarios = [s for s in all_scenarios if _assigned_to_me(s)]

        my_scenarios.sort(key=lambda s: (s["created_at"] or "", s["id"]))

        my_scenarios_by_id = {s["id"]: s for s in my_scenarios}

        # NOTE: db.list_simulations() is currently degraded to [] because

        # Codata is missing the CallSimulation list endpoint (ticket SUP-13).

        # New calls are still recorded correctly via db.insert_simulation();

        # queued/history/average below will simply show no history yet

        # until Codata resolves that ticket.

        my_sims = db.list_simulations(employee_id=employee_id)

        completed_scenario_ids = {sim["scenario_id"] for sim in my_sims}

        queued_calls = [s for s in my_scenarios if s["id"] not in completed_scenario_ids]

        def _matches_filters(sim):

            scn = my_scenarios_by_id.get(sim["scenario_id"])

            if selected_scenario:

                scn_type = (scn or {}).get("scenario_types") or ""

                if scn_type != selected_scenario:

                    return False

            if selected_date:

                completed = (sim.get("completed_at") or "")[:10]

                if completed != selected_date:

                    return False

            return True

        filtered_sims = [sim for sim in my_sims if _matches_filters(sim)]

        filtered_sims.sort(key=lambda s: (s["completed_at"] or "", s["id"]), reverse=True)

        previous_calls = []

        for sim in filtered_sims:

            row = dict(sim)

            scn = my_scenarios_by_id.get(sim["scenario_id"])

            row["title"] = (scn or {}).get("title")

            row["scenario_types"] = (scn or {}).get("scenario_types")

            previous_calls.append(row)

        scenario_options = sorted({

            (my_scenarios_by_id.get(sim["scenario_id"]) or {}).get("scenario_types")

            for sim in my_sims

            if (my_scenarios_by_id.get(sim["scenario_id"]) or {}).get("scenario_types")

        })

        date_options = sorted(

            {(sim.get("completed_at") or "")[:10] for sim in my_sims if sim.get("completed_at")},

            reverse=True,

        )

        scores = [sim["overall_score"] for sim in filtered_sims if sim.get("overall_score") is not None]

        average_score = (sum(scores) / len(scores)) if scores else 0

    return render_template(

        "employee_dashboard.html",

        employee=employee,

        queued_calls=queued_calls,

        previous_calls=previous_calls,

        average_score=average_score,

        scenario_options=scenario_options,

        date_options=date_options,

        selected_scenario=selected_scenario,

        selected_date=selected_date,

    )

@app.route("/mockline")

def mockline_dashboard():

    if not session.get("public_logged_in"):

        return redirect(url_for("public_login"))

    employee_id = session.get("employee_id")


    employee = db.get_employee_by_employee_id(employee_id)

    assigned_mocks = []

    if employee:

        def _assigned_to_me(scn):

            try:

                ids = json.loads(scn["assigned_employee_ids"] or "[]")

            except Exception:

                ids = []

            return employee_id in ids

        my_sims_ids = {sim["scenario_id"] for sim in db.list_simulations(employee_id=employee_id)}

        all_scenarios = db.list_scenarios()

        assigned_mocks = [

            s for s in all_scenarios

            if _assigned_to_me(s) and s["id"] not in my_sims_ids

        ]

        import random as _random

        randomized = [m for m in assigned_mocks if m.get("randomize_order")]

        ordered = [m for m in assigned_mocks if not m.get("randomize_order")]

        ordered.sort(key=lambda s: (s["created_at"] or "", s["id"]))

        _random.shuffle(randomized)

        assigned_mocks = randomized + ordered

    recent_score = 0

    previous_calls = []

    average_score = 0

    if employee:

        # NOTE: degraded to empty history until Codata ticket SUP-13

        # (missing CallSimulation list endpoint) is resolved.

        my_sims = db.list_simulations(employee_id=employee_id)

        my_sims.sort(key=lambda s: (s["completed_at"] or "", s["id"]), reverse=True)

        recent_score = my_sims[0]["overall_score"] if my_sims else 0

        scenarios_by_id = {s["id"]: s for s in db.list_scenarios()}

        previous_calls = []

        for sim in my_sims[:5]:

            row = dict(sim)

            row["title"] = (scenarios_by_id.get(sim["scenario_id"]) or {}).get("title")

            previous_calls.append(row)

        scores = [s["overall_score"] for s in my_sims if s.get("overall_score") is not None]

        average_score = (sum(scores) / len(scores)) if scores else 0

    return render_template(

        "mockline_dashboard.html",

        employee=employee,

        recent_score=recent_score,

        employee_name=(employee["name"] if employee else employee_id),

        employee_id_value=employee_id,

        batch_no=(assigned_mocks[0]["assigned_batch"] if assigned_mocks else employee["location"] if employee else "B-1043"),

        assigned_mocks=assigned_mocks,

        assigned_mock=(assigned_mocks[0] if assigned_mocks else None),

        previous_calls=previous_calls,

        average_score=average_score,

    )

@app.route("/mockline/submit", methods=["POST"])

def submit_mock_call():

    if not session.get("public_logged_in"):

        return jsonify({"error": "Login required"}), 401

    employee_id = session.get("employee_id")

    answer_text = request.form.get("answer", "").strip()

    scenario_id = request.form.get("scenario_id")

    try:

        conversation = json.loads(request.form.get("conversation_log", "[]"))

    except json.JSONDecodeError:

        conversation = []

    if not answer_text:

        return jsonify({"error": "No conversation response was provided."}), 400

    employee = db.get_employee_by_employee_id(employee_id)

    assigned_mock = None

    if employee:

        candidate = db.get_scenario(scenario_id)

        if candidate:

            try:

                ids = json.loads(candidate["assigned_employee_ids"] or "[]")

            except Exception:

                ids = []

            already_done = any(

                sim["scenario_id"] == scenario_id

                for sim in db.list_simulations(employee_id=employee_id)

            )

            if employee_id in ids and not already_done:

                assigned_mock = candidate

    if not assigned_mock:

        return jsonify({"error": "This mock call is no longer available."}), 404

    employee_dialogue = "\n".join(

        f"EMPLOYEE: {item.get('text', '')}"

        for item in conversation

        if item.get("role") == "employee" and item.get("text")

    )

    report = _build_mock_report(employee_dialogue or answer_text, assigned_mock)

    scenario_id = assigned_mock["id"] if assigned_mock else None

    batch_no = assigned_mock["assigned_batch"] if assigned_mock else (employee["location"] if employee else None)

    payload = {

        "employee_id": employee_id,

        "customer_question": assigned_mock["title"] if assigned_mock else "Mock call",

        "answer_text": answer_text,

        "analysis": report,

        "manager_summary": report["manager_summary"],

        "main_points": report["main_points"],

        "conversation": conversation,

    }

    created_sim = db.insert_simulation(

        employee_id=employee_id,

        scenario_id=scenario_id,

        batch_no=batch_no,

        transcript=json.dumps(payload),

        soft_skills_score=report["soft_skills_score"],

        customer_critical_score=report["customer_critical_score"],

        business_critical_score=report["business_critical_score"],

        overall_score=report["overall_score"],

        status="completed",

    )

    simulation_id = created_sim["id"]

    return render_template(

        "mockline_result.html",

        report=report,

        assigned_mock=assigned_mock,

        employee_name=employee["name"] if employee else employee_id,

        simulation_id=simulation_id,

        conversation=conversation,

    )

@app.route("/mockline/result/<simulation_id>")

def mockline_result(simulation_id):

    if not session.get("public_logged_in"):

        return redirect(url_for("public_login"))

    employee_id = session.get("employee_id")

    simulation = db.get_simulation(simulation_id)

    if simulation and simulation["employee_id"] != employee_id:

        simulation = None

    if simulation:

        scenario = db.get_scenario(simulation["scenario_id"]) if simulation["scenario_id"] else None

        if scenario:

            simulation = dict(simulation)

            simulation["title"] = scenario["title"]

            simulation["scenario_types"] = scenario["scenario_types"]

            simulation["communication_styles"] = scenario["communication_styles"]

    employee = db.get_employee_by_employee_id(employee_id)

    if not simulation:

        return redirect(url_for("employee_dashboard"))

    payload = json.loads(simulation["transcript"] or "{}")

    report = payload.get("analysis", {})

    conversation = payload.get("conversation", [])

    return render_template(

        "mockline_result.html",

        report=report,

        assigned_mock=simulation,

        employee_name=employee["name"] if employee else employee_id,

        simulation_id=simulation_id,

        conversation=conversation,

    )

@app.route("/mockline/respond", methods=["POST"])

def continue_mock_call():

    if not session.get("public_logged_in"):

        return jsonify({"error": "Login required"}), 401

    employee_id = session.get("employee_id")

    scenario_id = request.form.get("scenario_id")

    turn = request.form.get("turn", type=int) or 0

    answer = request.form.get("answer", "").strip()

    try:

        conversation = json.loads(request.form.get("conversation", "[]"))

    except json.JSONDecodeError:

        conversation = []

    if not answer:

        return jsonify({"error": "Please enter or speak an answer before submitting."}), 400

    employee = db.get_employee_by_employee_id(employee_id)

    assigned_mock = None

    if employee:

        candidate = db.get_scenario(scenario_id)

        if candidate:

            try:

                ids = json.loads(candidate["assigned_employee_ids"] or "[]")

            except Exception:

                ids = []

            if employee_id in ids:

                assigned_mock = candidate

    if not assigned_mock:

        return jsonify({"error": "This mock call is no longer available."}), 404

    issue = assigned_mock["scenario_types"] or "the service"

    tone = (assigned_mock["communication_styles"] or "calm").lower()

    language = assigned_mock["language"] or "English"

    next_turn = min(turn + 1, 3)

    caller_message = _generate_ai_customer_reply(answer, issue, tone, conversation, language)

    if not caller_message:

        caller_message = _customer_fallback(issue, tone, turn)

    return jsonify({

        "caller_message": caller_message,

        "turn": next_turn,

        "caller_tone": tone,

        "can_end": next_turn >= 3,

    })

@app.route("/mockline/start", methods=["POST"])

def start_mock_call():

    if not session.get("public_logged_in"):

        return jsonify({"error": "Login required"}), 401

    employee_id = session.get("employee_id")

    scenario_id = request.form.get("scenario_id")

    employee = db.get_employee_by_employee_id(employee_id)

    assigned_mock = None

    if employee:

        candidate = db.get_scenario(scenario_id)

        if candidate:

            try:

                ids = json.loads(candidate["assigned_employee_ids"] or "[]")

            except Exception:

                ids = []

            if employee_id in ids:

                assigned_mock = candidate

    if not assigned_mock:

        return jsonify({"error": "This mock call is no longer available."}), 404

    issue = assigned_mock["scenario_types"] or "the service"

    tone = (assigned_mock["communication_styles"] or "calm").lower()

    language = assigned_mock["language"] or "English"

    caller_message = _customer_opening(issue, tone, language)

    if not caller_message:

        return jsonify({"error": "AI customer bot is unavailable. Start Ollama and try again.", "ai_required": True}), 503

    return jsonify({"caller_message": caller_message, "turn": 0})

@app.route("/employee/reset-password", methods=["POST"])

def employee_reset_password():

    if not session.get("public_logged_in"):

        return redirect(url_for("public_login"))

    employee_id = session.get("employee_id")

    current_password = request.form.get("current_password", "").strip()

    new_password = request.form.get("new_password", "").strip()

    employee = db.get_employee_by_employee_id(employee_id)

    if not employee or employee["password"] != current_password:

        flash("Current password is incorrect.", "error")

        return redirect(url_for("employee_dashboard"))

    if not new_password:

        flash("New password cannot be empty.", "error")

        return redirect(url_for("employee_dashboard"))

    db.update_employee_password(employee["id"], new_password)

    flash("Password updated successfully.", "success")

    return redirect(url_for("employee_dashboard"))

# ---------- Admin auth routes ----------

@app.route("/admin/login", methods=["GET", "POST"])

def admin_login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()

        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session.clear()

            session["admin_logged_in"] = True

            flash("Logged in successfully.", "success")

            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin username or password.", "error")

    return render_template("login.html", login_type="admin")

@app.route("/admin/logout")

def admin_logout():

    session.pop("admin_logged_in", None)

    flash("Logged out successfully.", "success")

    return redirect(url_for("unified_login"))

# ---------- Manager Employee Management routes ----------

@app.route("/manager/employees")

def manager_employees():

    if not session.get("manager_logged_in"):

        return redirect(url_for("manager_login"))

    manager_location = session.get("manager_location")

    search_query = request.args.get("q", "").strip()

    employees = db.list_employees(location=manager_location)

    if search_query:

        employees = [e for e in employees if search_query.lower() in (e["employee_id"] or "").lower()]

    return render_template("manager_employees.html", employees=employees, location=manager_location, search_query=search_query)

@app.route("/manager/employees/new", methods=["GET", "POST"])

def manager_new_employee():

    if not session.get("manager_logged_in"):

        return redirect(url_for("manager_login"))

    if request.method == "POST":

        employee_id = request.form.get("employee_id", "").strip()

        name = request.form.get("name", "").strip()

        email = request.form.get("email", "").strip()

        department = request.form.get("department", "").strip()

        password = request.form.get("password", "").strip()

        manager_location = session.get("manager_location")

        if not employee_id or not name or not password:

            flash("Employee ID, Name, and Password are required.", "error")

            return render_template("manager_new_employee.html", location=manager_location)

        try:

            db.insert_employee(employee_id, name, email, department, manager_location, password)

            flash(f"Employee {employee_id} added successfully.", "success")

            return redirect(url_for("manager_employees"))

        except Exception:

            flash(f"Error: Employee ID already exists or invalid input.", "error")

    manager_location = session.get("manager_location")

    return render_template("manager_new_employee.html", location=manager_location)

@app.route("/manager/employees/delete/<employee_pk>", methods=["POST"])

def manager_delete_employee(employee_pk):

    if not session.get("manager_logged_in"):

        return redirect(url_for("manager_login"))

    manager_location = session.get("manager_location")

    # Only allow deletion if employee belongs to this manager's location

    employee = db.get_employee(employee_pk)

    if employee and employee["location"] == manager_location:

        db.delete_employee(employee_pk)

        flash("Employee deleted successfully.", "success")

    else:

        flash("Employee not found or you don't have permission to delete.", "error")

    return redirect(url_for("manager_employees"))

# ---------- Admin Manager Management routes ----------

@app.route("/admin/managers")

def manage_managers():

    if not session.get("admin_logged_in"):

        return redirect(url_for("admin_login"))

    managers = db.list_managers()

    managers.sort(key=lambda m: m["created_at"] or "", reverse=True)

    return render_template("manage_managers.html", managers=managers)

@app.route("/admin/managers/new", methods=["GET", "POST"])

def new_manager():

    if not session.get("admin_logged_in"):

        return redirect(url_for("admin_login"))

    if request.method == "POST":

        manager_id = request.form.get("manager_id", "").strip()

        username = request.form.get("username", "").strip()

        password = request.form.get("password", "").strip()

        location = request.form.get("location", "").strip()

        if not manager_id or not username or not password or not location:

            flash("Manager ID, username, password, and location are required.", "error")

            return render_template("new_manager.html")

        try:

            db.insert_manager(manager_id, username, password, location)

            flash(f"Manager {manager_id} added successfully.", "success")

            return redirect(url_for("manage_managers"))

        except Exception:

            flash("Error: Manager ID or username already exists.", "error")

    return render_template("new_manager.html")

@app.route("/admin/managers/delete/<manager_pk>", methods=["POST"])

def delete_manager(manager_pk):

    if not session.get("admin_logged_in"):

        return redirect(url_for("admin_login"))

    db.delete_manager(manager_pk)

    flash("Manager deleted successfully.", "success")

    return redirect(url_for("manage_managers"))

# ---------- Admin Employee Management routes ----------

@app.route("/admin/employees")

def manage_employees():

    if not session.get("admin_logged_in"):

        return redirect(url_for("admin_login"))

    employees = db.list_employees()

    return render_template("manage_employees.html", employees=employees)

@app.route("/admin/employees/new", methods=["GET", "POST"])

def new_employee():

    if not session.get("admin_logged_in"):

        return redirect(url_for("admin_login"))

    if request.method == "POST":

        employee_id = request.form.get("employee_id", "").strip()

        name = request.form.get("name", "").strip()

        email = request.form.get("email", "").strip()

        department = request.form.get("department", "").strip()

        location = request.form.get("location", "").strip()

        password = request.form.get("password", "").strip()

        if not employee_id or not name or not password:

            flash("Employee ID, Name, and Password are required.", "error")

            return render_template("new_employee.html")

        try:

            db.insert_employee(employee_id, name, email, department, location, password)

            flash(f"Employee {employee_id} added successfully.", "success")

            return redirect(url_for("manage_employees"))

        except Exception:

            flash(f"Error: Employee ID already exists or invalid input.", "error")

    return render_template("new_employee.html")

@app.route("/admin/employees/delete/<employee_pk>", methods=["POST"])

def delete_employee(employee_pk):

    if not session.get("admin_logged_in"):

        return redirect(url_for("admin_login"))

    db.delete_employee(employee_pk)

    flash("Employee deleted successfully.", "success")

    return redirect(url_for("manage_employees"))

# ---------- Admin routes ----------

@app.route("/admin")

def admin_dashboard():

    if not session.get("admin_logged_in"):

        return redirect(url_for("admin_login"))

    employees = db.list_employees()

    managers = db.list_managers()

    managers.sort(key=lambda m: m["created_at"] or "", reverse=True)

    # NOTE: db.list_simulations() is currently degraded to [] because Codata

    # is missing the CallSimulation list endpoint (ticket SUP-13). This

    # widget will show no recent calls until that's resolved.

    employees_by_id = {e["employee_id"]: e for e in employees}

    mock_reports = []

    for sim in db.list_simulations():

        emp = employees_by_id.get(sim["employee_id"])

        if not emp:

            continue

        row = dict(sim)

        row["employee_name"] = emp["name"]

        mock_reports.append(row)

    mock_reports.sort(key=lambda r: r["completed_at"] or "", reverse=True)

    mock_reports = mock_reports[:50]

    return render_template("admin.html", employees=employees, managers=managers, mock_reports=mock_reports)

@app.route("/admin/submissions")

def admin_submissions():

    if not session.get("admin_logged_in"):

        return redirect(url_for("admin_login"))

    managers = db.list_managers()

    managers.sort(key=lambda m: m["created_at"] or "")

    # NOTE: per-employee scores below depend on db.list_simulations(), which

    # is currently degraded to [] because Codata is missing the

    # CallSimulation list endpoint (ticket SUP-13). Averages/pass-rates will

    # show 0 until that's resolved; employee counts are unaffected.

    all_sims = db.list_simulations()

    scores_by_employee = {}

    for sim in all_sims:

        scores_by_employee.setdefault(sim["employee_id"], []).append(sim["overall_score"] or 0)

    summary = []

    for manager in managers:

        location = manager["location"]

        employees = [e for e in db.list_employees(location=location)]

        employees.sort(key=lambda e: e["name"] or "")

        employee_ids = [emp["employee_id"] for emp in employees]

        values = []

        for eid in employee_ids:

            values.extend(scores_by_employee.get(eid, []))

        if values:

            average = round(sum(values) / len(values), 2)

            pass_rate = round((sum(1 for v in values if v >= 6) / len(values)) * 100, 2)

        else:

            average = 0

            pass_rate = 0

        summary.append({

            "manager_name": manager["username"],

            "location": location,

            "employee_count": len(employees),

            "average_percentage": average,

            "pass_rate": pass_rate,

        })

    return render_template("admin_submissions.html", manager_summary=summary)

if __name__ == "__main__":

    app.run(debug=True)


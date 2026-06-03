"""
Creates a sample SQLite database with a mortgage / home-loan schema.

Schema highlights
-----------------
- ``branches``           — physical lending branches (lookup).
- ``loan_officers``      — bank employees originating loans, FK to branch.
- ``customers``          — borrowers with PII (name, address, gender, DOB,
                          age, income, employer, credit score, etc.).
- ``applications``       — loan applications submitted by customers (with
                          requested amount + decision).
- ``loans``              — booked mortgages: amount, rate, term, status,
                          monthly payment, outstanding balance.
- ``collaterals``        — properties pledged against each loan.
- ``payments``           — monthly amortisation payments per loan.
- ``credit_history``     — periodic credit bureau snapshots per customer.

Each table carries a ``report_date`` column tagging the snapshot. Natural-key
uniqueness is enforced as ``UNIQUE(<key>, report_date)`` so the same logical
entity (e.g. customer email) can appear in multiple snapshots while staying
unique within a snapshot.

Numeric fields (loan_amount, interest_rate, monthly_payment, appraised_value,
income, credit_score, …) are generated with ``random.uniform`` /
``random.randint`` so different snapshots show genuine variation. The PRNG
is seeded from the snapshot date, so re-running the same snapshot is stable
while different snapshots produce different numbers.
"""

import random
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.utils.db_registry import (
    clear_snapshot_artifacts,
    list_snapshot_dates,
    register_database,
    register_snapshot,
)

_DB_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,62}$")
_SNAPSHOT_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_db_name(db_name: str) -> str:
    if not isinstance(db_name, str) or not _DB_NAME_PATTERN.match(db_name):
        raise ValueError(
            f"Invalid db_name '{db_name}': must start with a letter and contain only "
            "letters, digits, underscores, or hyphens (max 63 chars)."
        )
    return db_name


def _validate_snapshot_date(snapshot_date: str) -> str:
    if not isinstance(snapshot_date, str) or not _SNAPSHOT_DATE_PATTERN.match(snapshot_date):
        raise ValueError(
            f"Invalid snapshot_date '{snapshot_date}': must be ISO format YYYY-MM-DD "
            "(e.g. '2025-01-01')."
        )
    try:
        datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid snapshot_date '{snapshot_date}': {e}")
    return snapshot_date


def _resolve_db_path(db_name: str) -> Path:
    return Path(settings.database_dir) / f"{db_name}.db"


SCHEMA_SQL = """
-- Branches (physical lending offices)
CREATE TABLE IF NOT EXISTS branches (
    branch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_code TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    address TEXT,
    city TEXT NOT NULL,
    state TEXT,
    country TEXT NOT NULL DEFAULT 'US',
    manager_name TEXT,
    phone TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_date TEXT NOT NULL,
    UNIQUE (branch_code, report_date)
);

-- Loan officers (bank employees originating mortgages)
CREATE TABLE IF NOT EXISTS loan_officers (
    officer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    branch_id INTEGER NOT NULL,
    hire_date TEXT NOT NULL,
    job_title TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    report_date TEXT NOT NULL,
    UNIQUE (email, report_date),
    FOREIGN KEY (branch_id) REFERENCES branches(branch_id)
);

-- Customers (borrowers / applicants)
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    date_of_birth TEXT,
    age INTEGER CHECK(age IS NULL OR (age >= 18 AND age <= 100)),
    gender TEXT CHECK(gender IN ('M', 'F', 'Other', NULL)),
    marital_status TEXT CHECK(marital_status IN ('Single', 'Married', 'Divorced', 'Widowed', NULL)),
    address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    country TEXT NOT NULL DEFAULT 'US',
    employment_status TEXT CHECK(employment_status IN ('Employed', 'Self-Employed', 'Unemployed', 'Retired', 'Student', NULL)),
    employer_name TEXT,
    annual_income REAL CHECK(annual_income IS NULL OR annual_income >= 0),
    credit_score INTEGER CHECK(credit_score IS NULL OR (credit_score >= 300 AND credit_score <= 850)),
    registration_date TEXT NOT NULL DEFAULT (datetime('now')),
    is_active INTEGER NOT NULL DEFAULT 1,
    report_date TEXT NOT NULL,
    UNIQUE (email, report_date)
);

-- Loan applications (submitted, possibly not yet approved)
CREATE TABLE IF NOT EXISTS applications (
    application_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    officer_id INTEGER,
    branch_id INTEGER,
    application_date TEXT NOT NULL,
    requested_amount REAL NOT NULL CHECK(requested_amount > 0),
    requested_term_months INTEGER NOT NULL CHECK(requested_term_months > 0),
    purpose TEXT CHECK(purpose IN ('Purchase', 'Refinance', 'Cash-Out Refinance', 'Construction', 'Home Improvement', NULL)),
    decision TEXT CHECK(decision IN ('Pending', 'Approved', 'Rejected', 'Withdrawn')),
    decision_date TEXT,
    decision_reason TEXT,
    report_date TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (officer_id) REFERENCES loan_officers(officer_id),
    FOREIGN KEY (branch_id) REFERENCES branches(branch_id)
);

-- Booked loans (originated mortgages)
CREATE TABLE IF NOT EXISTS loans (
    loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_number TEXT NOT NULL,
    customer_id INTEGER NOT NULL,
    officer_id INTEGER,
    branch_id INTEGER,
    application_id INTEGER,
    loan_type TEXT NOT NULL CHECK(loan_type IN ('Fixed', 'Variable', 'FHA', 'VA', 'Jumbo', 'Interest-Only')),
    loan_amount REAL NOT NULL CHECK(loan_amount > 0),
    interest_rate REAL NOT NULL CHECK(interest_rate >= 0 AND interest_rate <= 30),
    term_months INTEGER NOT NULL CHECK(term_months > 0),
    origination_date TEXT NOT NULL,
    maturity_date TEXT NOT NULL,
    monthly_payment REAL NOT NULL CHECK(monthly_payment >= 0),
    outstanding_balance REAL NOT NULL CHECK(outstanding_balance >= 0),
    loan_status TEXT NOT NULL CHECK(loan_status IN ('Active', 'Paid Off', 'Delinquent', 'In Foreclosure', 'Defaulted', 'Closed')),
    purpose TEXT,
    report_date TEXT NOT NULL,
    UNIQUE (loan_number, report_date),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (officer_id) REFERENCES loan_officers(officer_id),
    FOREIGN KEY (branch_id) REFERENCES branches(branch_id),
    FOREIGN KEY (application_id) REFERENCES applications(application_id)
);

-- Collateral (properties pledged against loans)
CREATE TABLE IF NOT EXISTS collaterals (
    collateral_id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL,
    collateral_type TEXT NOT NULL CHECK(collateral_type IN ('Single Family', 'Condo', 'Townhouse', 'Multi-Family', 'Land', 'Commercial')),
    property_address TEXT NOT NULL,
    property_city TEXT NOT NULL,
    property_state TEXT,
    property_postal_code TEXT,
    property_country TEXT NOT NULL DEFAULT 'US',
    year_built INTEGER CHECK(year_built IS NULL OR (year_built >= 1800 AND year_built <= 2030)),
    appraised_value REAL NOT NULL CHECK(appraised_value > 0),
    appraisal_date TEXT,
    ltv_ratio REAL CHECK(ltv_ratio IS NULL OR (ltv_ratio >= 0 AND ltv_ratio <= 1.5)),
    insurance_provider TEXT,
    report_date TEXT NOT NULL,
    FOREIGN KEY (loan_id) REFERENCES loans(loan_id)
);

-- Payments (monthly amortisation activity)
CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL,
    payment_date TEXT NOT NULL,
    scheduled_amount REAL NOT NULL CHECK(scheduled_amount >= 0),
    paid_amount REAL NOT NULL CHECK(paid_amount >= 0),
    principal_paid REAL NOT NULL CHECK(principal_paid >= 0),
    interest_paid REAL NOT NULL CHECK(interest_paid >= 0),
    escrow_paid REAL DEFAULT 0 CHECK(escrow_paid >= 0),
    payment_method TEXT CHECK(payment_method IN ('ACH', 'Check', 'Wire', 'Card', 'Cash', NULL)),
    status TEXT NOT NULL CHECK(status IN ('On-Time', 'Late', 'Missed', 'Partial', 'Reversed')),
    days_late INTEGER DEFAULT 0 CHECK(days_late >= 0),
    transaction_ref TEXT,
    report_date TEXT NOT NULL,
    UNIQUE (transaction_ref, report_date),
    FOREIGN KEY (loan_id) REFERENCES loans(loan_id)
);

-- Credit history (periodic bureau snapshots per customer)
CREATE TABLE IF NOT EXISTS credit_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    bureau TEXT NOT NULL CHECK(bureau IN ('Equifax', 'Experian', 'TransUnion')),
    pulled_date TEXT NOT NULL,
    score INTEGER NOT NULL CHECK(score >= 300 AND score <= 850),
    open_accounts INTEGER NOT NULL CHECK(open_accounts >= 0),
    total_debt REAL NOT NULL CHECK(total_debt >= 0),
    delinquencies_30d INTEGER DEFAULT 0 CHECK(delinquencies_30d >= 0),
    delinquencies_90d INTEGER DEFAULT 0 CHECK(delinquencies_90d >= 0),
    bankruptcies INTEGER DEFAULT 0 CHECK(bankruptcies >= 0),
    report_date TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_datetime(start_year: int, end_year: int) -> str:
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    return (start + timedelta(days=random.randint(0, delta.days))).strftime("%Y-%m-%d %H:%M:%S")


def _random_date(start_year: int, end_year: int) -> str:
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    return (start + timedelta(days=random.randint(0, delta.days))).strftime("%Y-%m-%d")


def _amortised_monthly_payment(principal: float, annual_rate_pct: float, term_months: int) -> float:
    """Standard fixed-rate amortisation formula."""
    if term_months <= 0 or principal <= 0:
        return 0.0
    r = (annual_rate_pct / 100.0) / 12.0
    if r == 0:
        return round(principal / term_months, 2)
    pmt = principal * (r * (1 + r) ** term_months) / ((1 + r) ** term_months - 1)
    return round(pmt, 2)


# ---------------------------------------------------------------------------
# Insertions (one snapshot at a time)
# ---------------------------------------------------------------------------

_BRANCH_DATA = [
    ("BR-NYC-01", "Manhattan Main", "200 Park Ave", "New York", "NY", "Alice Reynolds", "+1-212-555-1001"),
    ("BR-LAX-01", "Los Angeles Downtown", "500 S Grand Ave", "Los Angeles", "CA", "Carlos Mendoza", "+1-213-555-1002"),
    ("BR-CHI-01", "Chicago Loop", "100 N Wacker Dr", "Chicago", "IL", "Hannah Becker", "+1-312-555-1003"),
    ("BR-HOU-01", "Houston Galleria", "5085 Westheimer Rd", "Houston", "TX", "Marcus Lee", "+1-713-555-1004"),
    ("BR-PHX-01", "Phoenix Camelback", "2425 E Camelback Rd", "Phoenix", "AZ", "Priya Patel", "+1-602-555-1005"),
    ("BR-SEA-01", "Seattle Bellevue", "10500 NE 8th St", "Bellevue", "WA", "Diana Park", "+1-425-555-1006"),
    ("BR-MIA-01", "Miami Brickell", "1450 Brickell Ave", "Miami", "FL", "Roberto Silva", "+1-305-555-1007"),
]


def _insert_branches(conn: sqlite3.Connection, snapshot_date: str) -> list[int]:
    ids: list[int] = []
    for code, name, addr, city, state, manager, phone in _BRANCH_DATA:
        cur = conn.execute(
            "INSERT INTO branches (branch_code, branch_name, address, city, state, country, manager_name, phone, report_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (code, name, addr, city, state, "US", manager, phone, snapshot_date),
        )
        ids.append(cur.lastrowid)
    return ids


_OFFICER_FIRST = ["Olivia", "Liam", "Noah", "Emma", "Ava", "Ethan", "Mia", "Lucas",
                  "Amelia", "Mason", "Sophia", "Logan", "Isabella", "James", "Charlotte"]
_OFFICER_LAST = ["Anderson", "Thompson", "Walker", "Hall", "Allen", "Young", "King",
                 "Wright", "Scott", "Green", "Baker", "Adams", "Nelson", "Carter", "Mitchell"]


def _insert_loan_officers(
    conn: sqlite3.Connection, snapshot_date: str, branch_ids: list[int], drift: float
) -> list[int]:
    null_phone_rate = min(0.4, 0.10 + drift * 0.20)
    ids: list[int] = []
    # 3 officers per branch + a few extras for variation
    n_officers = 3 * len(branch_ids) + random.randint(2, 5)
    for i in range(n_officers):
        first = random.choice(_OFFICER_FIRST)
        last = random.choice(_OFFICER_LAST)
        email = f"{first.lower()}.{last.lower()}{i}@bank.example.com"
        phone = f"+1-555-{random.randint(2000, 8999)}" if random.random() > null_phone_rate else None
        branch_id = random.choice(branch_ids)
        hire = _random_date(2010, 2024)
        title = random.choices(
            ["Loan Officer", "Senior Loan Officer", "Mortgage Specialist", "Branch Manager"],
            weights=[0.55, 0.25, 0.15, 0.05],
            k=1,
        )[0]
        is_active = 0 if random.random() < min(0.15, 0.03 + drift * 0.10) else 1
        cur = conn.execute(
            "INSERT INTO loan_officers (first_name, last_name, email, phone, branch_id, hire_date, job_title, is_active, report_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (first, last, email, phone, branch_id, hire, title, is_active, snapshot_date),
        )
        ids.append(cur.lastrowid)
    return ids


_CUST_FIRST = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
               "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph",
               "Jessica", "Thomas", "Sarah", "Christopher", "Karen", "Daniel", "Lisa",
               "Matthew", "Nancy", "Anthony", "Betty", "Mark", "Margaret", "Donald", "Sandra",
               "Aisha", "Wei", "Yuki", "Carlos", "Fatima", "Dmitri", "Priya", "Hiroshi"]
_CUST_LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
              "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
              "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
              "Khan", "Chen", "Tanaka", "Okafor", "Singh", "Petrov"]
_CUST_CITIES = [
    ("New York", "NY"), ("Los Angeles", "CA"), ("Chicago", "IL"), ("Houston", "TX"),
    ("Phoenix", "AZ"), ("Philadelphia", "PA"), ("San Antonio", "TX"), ("San Diego", "CA"),
    ("Dallas", "TX"), ("San Jose", "CA"), ("Austin", "TX"), ("Jacksonville", "FL"),
    ("Charlotte", "NC"), ("Seattle", "WA"), ("Denver", "CO"), ("Boston", "MA"),
    ("Miami", "FL"), ("Atlanta", "GA"), ("Portland", "OR"), ("Minneapolis", "MN"),
]
_EMPLOYERS = ["Acme Corp", "Globex", "Initech", "Soylent", "Umbrella Inc", "Stark Industries",
              "Wayne Enterprises", "Hooli", "Pied Piper", "Cyberdyne", "Wonka Industries",
              "Tyrell Corp", "Massive Dynamic", "Self-Employed", None]


def _insert_customers(
    conn: sqlite3.Connection, snapshot_date: str, drift: float, n: int = 250
) -> list[int]:
    """Insert customers with realistic noise and intentional DQ issues."""
    null_phone_rate = min(0.5, 0.12 + drift * 0.20)
    null_dob_rate = min(0.3, 0.08 + drift * 0.12)
    null_postal_rate = min(0.25, 0.06 + drift * 0.10)
    null_income_rate = min(0.2, 0.05 + drift * 0.10)
    null_credit_rate = min(0.18, 0.05 + drift * 0.08)
    inactive_rate = min(0.20, 0.05 + drift * 0.10)
    # Intentional age/DOB inconsistency rate (DQ issue)
    age_dob_mismatch_rate = min(0.08, 0.02 + drift * 0.05)

    snap_year = int(snapshot_date[:4])
    ids: list[int] = []
    for i in range(n):
        fn = random.choice(_CUST_FIRST)
        ln = random.choice(_CUST_LAST)
        city, state = random.choice(_CUST_CITIES)
        email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
        phone = f"+1-555-{random.randint(1000, 9999)}" if random.random() > null_phone_rate else None

        # DOB and derived age, with noisy variation
        dob_year = random.randint(1945, snap_year - 21)
        dob = f"{dob_year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
        age = snap_year - dob_year
        if random.random() < age_dob_mismatch_rate:
            # Intentional inconsistency: age does not match dob
            age = max(18, age + random.choice([-7, -5, 5, 7]))
        if random.random() < null_dob_rate:
            dob = None

        gender = random.choices(["M", "F", "Other", None], weights=[0.46, 0.46, 0.04, 0.04], k=1)[0]
        marital = random.choices(
            ["Single", "Married", "Divorced", "Widowed", None],
            weights=[0.30, 0.50, 0.10, 0.05, 0.05],
            k=1,
        )[0]
        postal = f"{random.randint(10000, 99999)}" if random.random() > null_postal_rate else None
        emp_status = random.choices(
            ["Employed", "Self-Employed", "Unemployed", "Retired", "Student"],
            weights=[0.65, 0.15, 0.05, 0.10, 0.05],
            k=1,
        )[0]
        employer = random.choice(_EMPLOYERS) if emp_status in ("Employed", "Self-Employed") else None

        # Income: log-normal-ish noise, scaled by employment status
        base_income = random.uniform(28_000, 220_000)
        # add multiplicative jitter so different snapshots see drift
        income = base_income * random.uniform(0.85, 1.15)
        if emp_status == "Unemployed":
            income = random.uniform(0, 18_000)
        elif emp_status == "Student":
            income = random.uniform(0, 25_000)
        elif emp_status == "Retired":
            income = random.uniform(15_000, 80_000)
        income = round(income, 2)
        if random.random() < null_income_rate:
            income = None

        # Credit score with realistic-ish distribution + noise
        cs_band = random.choices(
            [(580, 639), (640, 699), (700, 749), (750, 799), (800, 850), (300, 579)],
            weights=[0.15, 0.25, 0.25, 0.20, 0.10, 0.05],
            k=1,
        )[0]
        credit_score = random.randint(*cs_band) + random.choice([-3, -2, -1, 0, 1, 2, 3])
        credit_score = max(300, min(850, credit_score))
        if random.random() < null_credit_rate:
            credit_score = None

        cur = conn.execute(
            "INSERT INTO customers (first_name, last_name, email, phone, date_of_birth, age, gender, "
            "marital_status, address, city, state, postal_code, country, employment_status, employer_name, "
            "annual_income, credit_score, registration_date, is_active, report_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fn, ln, email, phone, dob, age, gender, marital,
                f"{random.randint(1, 9999)} {random.choice(['Maple','Oak','Elm','Pine','Cedar'])} St",
                city, state, postal, "US", emp_status, employer,
                income, credit_score, _random_datetime(2018, snap_year),
                0 if random.random() < inactive_rate else 1, snapshot_date,
            ),
        )
        ids.append(cur.lastrowid)

    # Intentional duplicate-name customer (uniqueness/dedup test fixture)
    cur = conn.execute(
        "INSERT INTO customers (first_name, last_name, email, phone, date_of_birth, age, gender, "
        "marital_status, address, city, state, postal_code, country, employment_status, employer_name, "
        "annual_income, credit_score, registration_date, is_active, report_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("James", "Smith", "james.smith.dup@example.com", "+1-555-0000", "1985-04-12", 40, "M",
         "Married", "123 Main St", "New York", "NY", "10001", "US", "Employed", "Acme Corp",
         95000.00, 720, "2022-06-15 09:00:00", 1, snapshot_date),
    )
    ids.append(cur.lastrowid)
    return ids


def _insert_applications(
    conn: sqlite3.Connection,
    snapshot_date: str,
    customer_ids: list[int],
    officer_ids: list[int],
    branch_ids: list[int],
    drift: float,
    n: int = 400,
) -> list[int]:
    decisions = ["Approved", "Rejected", "Pending", "Withdrawn"]
    decision_weights = [0.55, 0.25, 0.15, 0.05]
    purposes = ["Purchase", "Refinance", "Cash-Out Refinance", "Construction", "Home Improvement"]
    purpose_weights = [0.55, 0.20, 0.10, 0.05, 0.10]
    null_purpose_rate = min(0.10, 0.02 + drift * 0.05)

    snap_year = int(snapshot_date[:4])
    ids: list[int] = []
    for _ in range(n):
        cust_id = random.choice(customer_ids)
        officer_id = random.choice(officer_ids) if random.random() > 0.05 else None
        branch_id = random.choice(branch_ids) if random.random() > 0.05 else None
        app_date = _random_date(snap_year - 3, snap_year)
        # Requested amount: noisy log-uniform-ish distribution
        amount = round(random.uniform(60_000, 1_500_000) * random.uniform(0.9, 1.1), 2)
        term = random.choice([120, 180, 240, 300, 360])
        purpose = None if random.random() < null_purpose_rate else random.choices(purposes, weights=purpose_weights, k=1)[0]
        decision = random.choices(decisions, weights=decision_weights, k=1)[0]
        decision_date = None
        decision_reason = None
        if decision != "Pending":
            app_dt = datetime.strptime(app_date, "%Y-%m-%d")
            decision_date = (app_dt + timedelta(days=random.randint(3, 45))).strftime("%Y-%m-%d")
            if decision == "Rejected":
                decision_reason = random.choice([
                    "Insufficient income",
                    "Low credit score",
                    "High debt-to-income ratio",
                    "Insufficient down payment",
                    "Property appraisal below offer",
                ])
            elif decision == "Withdrawn":
                decision_reason = "Applicant withdrew"

        cur = conn.execute(
            "INSERT INTO applications (customer_id, officer_id, branch_id, application_date, "
            "requested_amount, requested_term_months, purpose, decision, decision_date, decision_reason, report_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cust_id, officer_id, branch_id, app_date, amount, term, purpose,
             decision, decision_date, decision_reason, snapshot_date),
        )
        ids.append(cur.lastrowid)
    return ids


def _insert_loans(
    conn: sqlite3.Connection,
    snapshot_date: str,
    customer_ids: list[int],
    officer_ids: list[int],
    branch_ids: list[int],
    application_ids: list[int],
    drift: float,
) -> list[int]:
    """Materialise approved applications into booked loans, with extra noise."""
    loan_types = ["Fixed", "Variable", "FHA", "VA", "Jumbo", "Interest-Only"]
    loan_type_weights = [0.50, 0.18, 0.12, 0.08, 0.08, 0.04]
    statuses = ["Active", "Paid Off", "Delinquent", "In Foreclosure", "Defaulted", "Closed"]
    status_weights = [0.65, 0.10, 0.12, 0.04, 0.02, 0.07]
    # Drift makes statuses worsen over time
    delinq_drift = min(0.10, drift * 0.10)
    status_weights = [
        max(0.40, 0.65 - delinq_drift),  # Active
        0.10,
        0.12 + delinq_drift,             # Delinquent
        0.04 + delinq_drift / 2,         # In Foreclosure
        0.02 + delinq_drift / 4,         # Defaulted
        0.07,
    ]
    snap_year = int(snapshot_date[:4])

    ids: list[int] = []
    # ~70-80% of approved applications materialise into booked loans
    booked_count = max(1, int(len(application_ids) * 0.65))
    for i, app_id in enumerate(random.sample(application_ids, booked_count)):
        cust_id = random.choice(customer_ids)
        officer_id = random.choice(officer_ids) if random.random() > 0.04 else None
        branch_id = random.choice(branch_ids) if random.random() > 0.04 else None
        ltype = random.choices(loan_types, weights=loan_type_weights, k=1)[0]

        # Loan amount: noisy across snapshots
        base_amt = random.uniform(80_000, 1_200_000)
        amount = round(base_amt * random.uniform(0.92, 1.08), 2)

        # Rate: vary by snapshot year + jitter
        # Add a snapshot-dependent rate floor so different snapshots show rate drift
        snap_rate_anchor = 3.5 + (snap_year - 2020) * 0.4 + drift * 0.5
        rate = round(max(2.0, snap_rate_anchor + random.uniform(-0.75, 1.5) + random.uniform(-0.3, 0.3)), 3)

        term = random.choice([120, 180, 240, 300, 360])
        orig_date_str = _random_date(snap_year - 5, snap_year)
        orig_dt = datetime.strptime(orig_date_str, "%Y-%m-%d")
        maturity_dt = orig_dt + timedelta(days=int(term * 30.5))

        monthly = _amortised_monthly_payment(amount, rate, term)
        # Pay-down: roughly proportional to time elapsed since origination
        months_elapsed = max(0, (datetime.strptime(snapshot_date, "%Y-%m-%d") - orig_dt).days // 30)
        amortised_fraction = min(0.95, months_elapsed / max(1, term))
        outstanding = round(max(0.0, amount * (1 - amortised_fraction) * random.uniform(0.95, 1.05)), 2)

        status = random.choices(statuses, weights=status_weights, k=1)[0]
        if status == "Paid Off":
            outstanding = 0.0
        elif status == "Closed":
            outstanding = 0.0

        loan_number = f"L-{snap_year}-{i:06d}-{random.randint(100, 999)}"

        cur = conn.execute(
            "INSERT INTO loans (loan_number, customer_id, officer_id, branch_id, application_id, loan_type, "
            "loan_amount, interest_rate, term_months, origination_date, maturity_date, monthly_payment, "
            "outstanding_balance, loan_status, purpose, report_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                loan_number, cust_id, officer_id, branch_id, app_id, ltype,
                amount, rate, term, orig_date_str,
                maturity_dt.strftime("%Y-%m-%d"),
                monthly, outstanding, status,
                random.choice(["Purchase", "Refinance", "Cash-Out Refinance", "Construction", "Home Improvement"]),
                snapshot_date,
            ),
        )
        ids.append(cur.lastrowid)
    return ids


_PROPERTY_CITIES = [
    ("Brooklyn", "NY", "11201"), ("Queens", "NY", "11375"), ("Beverly Hills", "CA", "90210"),
    ("Pasadena", "CA", "91101"), ("Naperville", "IL", "60540"), ("Sugar Land", "TX", "77479"),
    ("Scottsdale", "AZ", "85251"), ("Bellevue", "WA", "98004"), ("Boulder", "CO", "80301"),
    ("Cambridge", "MA", "02139"), ("Coral Gables", "FL", "33134"), ("Sandy Springs", "GA", "30328"),
]


def _insert_collaterals(
    conn: sqlite3.Connection, snapshot_date: str, loan_ids: list[int],
    loan_amounts: dict[int, float], drift: float,
) -> None:
    coll_types = ["Single Family", "Condo", "Townhouse", "Multi-Family", "Land", "Commercial"]
    coll_weights = [0.55, 0.20, 0.12, 0.06, 0.04, 0.03]
    null_appraisal_rate = min(0.15, 0.03 + drift * 0.08)

    for loan_id in loan_ids:
        ctype = random.choices(coll_types, weights=coll_weights, k=1)[0]
        city, state, postal = random.choice(_PROPERTY_CITIES)
        addr = f"{random.randint(1, 9999)} {random.choice(['Lakeview','Hillside','Sunset','Riverside','Garden'])} Dr"
        year_built = random.randint(1920, 2024) if random.random() > 0.05 else None
        loan_amt = loan_amounts.get(loan_id, 250_000)
        # Appraisal value: typically loan/0.8 with noise; sometimes underwater
        ltv_target = random.choices([0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
                                    weights=[0.10, 0.20, 0.40, 0.20, 0.07, 0.03], k=1)[0]
        appraised = round((loan_amt / ltv_target) * random.uniform(0.92, 1.10), 2)
        appraised = max(50_000.0, appraised)
        appraisal_date = _random_date(int(snapshot_date[:4]) - 3, int(snapshot_date[:4])) \
            if random.random() > null_appraisal_rate else None
        ltv = round(loan_amt / appraised, 4) if appraised > 0 else None
        if ltv is not None:
            ltv = max(0.0, min(1.5, ltv))
        insurer = random.choice(["State Farm", "Allstate", "Liberty Mutual", "GEICO", "Travelers", None])

        conn.execute(
            "INSERT INTO collaterals (loan_id, collateral_type, property_address, property_city, property_state, "
            "property_postal_code, property_country, year_built, appraised_value, appraisal_date, ltv_ratio, "
            "insurance_provider, report_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (loan_id, ctype, addr, city, state, postal, "US", year_built,
             appraised, appraisal_date, ltv, insurer, snapshot_date),
        )


def _insert_payments(
    conn: sqlite3.Connection, snapshot_date: str, loan_ids: list[int],
    loan_meta: dict[int, dict[str, Any]], drift: float,
) -> None:
    null_method_rate = min(0.10, 0.02 + drift * 0.06)
    null_txn_rate = min(0.12, 0.03 + drift * 0.06)
    late_rate = min(0.20, 0.06 + drift * 0.10)
    missed_rate = min(0.08, 0.02 + drift * 0.05)

    snap_dt = datetime.strptime(snapshot_date, "%Y-%m-%d")
    for loan_id in loan_ids:
        meta = loan_meta[loan_id]
        orig_dt = datetime.strptime(meta["origination_date"], "%Y-%m-%d")
        scheduled = float(meta["monthly_payment"])
        rate = float(meta["interest_rate"])
        months_elapsed = max(0, min(meta["term_months"], (snap_dt - orig_dt).days // 30))
        # Cap to keep dataset small
        months_to_emit = min(months_elapsed, 24)
        principal_remaining = float(meta["loan_amount"])
        for m in range(months_to_emit):
            pay_dt = orig_dt + timedelta(days=int(30.5 * (m + 1)))
            interest_part = round(principal_remaining * (rate / 100.0) / 12.0, 2)

            r = random.random()
            if r < missed_rate:
                status = "Missed"
                paid = 0.0
                principal_paid = 0.0
                interest_paid = 0.0
                days_late = random.randint(31, 90)
            elif r < missed_rate + late_rate:
                status = "Late"
                # Late payment with possible partial amount
                if random.random() < 0.3:
                    status = "Partial"
                    paid = round(scheduled * random.uniform(0.3, 0.85), 2)
                else:
                    paid = round(scheduled * random.uniform(0.95, 1.05), 2)
                principal_paid = max(0.0, round(paid - interest_part, 2)) if paid > interest_part else 0.0
                interest_paid = min(paid, interest_part)
                days_late = random.randint(5, 30)
            else:
                status = "On-Time"
                paid = round(scheduled * random.uniform(0.99, 1.02), 2)
                principal_paid = max(0.0, round(paid - interest_part, 2))
                interest_paid = interest_part
                days_late = 0

            principal_remaining = max(0.0, principal_remaining - principal_paid)
            method = None if random.random() < null_method_rate else random.choices(
                ["ACH", "Check", "Wire", "Card", "Cash"], weights=[0.65, 0.15, 0.05, 0.10, 0.05], k=1
            )[0]
            txn_ref = (
                f"PMT-{loan_id:06d}-{m:03d}-{random.randint(1000, 9999)}"
                if random.random() > null_txn_rate else None
            )
            escrow = round(scheduled * random.uniform(0.0, 0.20), 2) if random.random() > 0.4 else 0.0

            conn.execute(
                "INSERT INTO payments (loan_id, payment_date, scheduled_amount, paid_amount, principal_paid, "
                "interest_paid, escrow_paid, payment_method, status, days_late, transaction_ref, report_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (loan_id, pay_dt.strftime("%Y-%m-%d"), scheduled, paid, principal_paid,
                 interest_paid, escrow, method, status, days_late, txn_ref, snapshot_date),
            )


def _insert_credit_history(
    conn: sqlite3.Connection, snapshot_date: str, customer_ids: list[int], drift: float
) -> None:
    bureaus = ["Equifax", "Experian", "TransUnion"]
    snap_year = int(snapshot_date[:4])
    # Most customers get 1-3 bureau pulls
    for cust_id in customer_ids:
        n_pulls = random.choices([0, 1, 2, 3], weights=[0.05, 0.40, 0.40, 0.15], k=1)[0]
        for _ in range(n_pulls):
            bureau = random.choice(bureaus)
            pulled = _random_date(snap_year - 2, snap_year)
            score = random.randint(540, 830) + random.choice([-3, -2, -1, 0, 1, 2, 3])
            score = max(300, min(850, score))
            open_acc = random.randint(1, 18)
            total_debt = round(random.uniform(0, 350_000) * random.uniform(0.9, 1.1), 2)
            d30 = random.choices([0, 0, 0, 1, 2, 3], weights=[0.5, 0.2, 0.1, 0.1, 0.05, 0.05], k=1)[0]
            d90 = random.choices([0, 0, 0, 0, 1, 2], weights=[0.6, 0.15, 0.1, 0.05, 0.05, 0.05], k=1)[0]
            bk = 0 if random.random() > min(0.06, 0.01 + drift * 0.04) else random.choice([1, 1, 2])

            conn.execute(
                "INSERT INTO credit_history (customer_id, bureau, pulled_date, score, open_accounts, "
                "total_debt, delinquencies_30d, delinquencies_90d, bankruptcies, report_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cust_id, bureau, pulled, score, open_acc, total_debt, d30, d90, bk, snapshot_date),
            )


# ---------------------------------------------------------------------------
# Snapshot orchestration
# ---------------------------------------------------------------------------

def _populate_snapshot(conn: sqlite3.Connection, snapshot_date: str, drift: float) -> None:
    branch_ids = _insert_branches(conn, snapshot_date)
    officer_ids = _insert_loan_officers(conn, snapshot_date, branch_ids, drift)
    customer_ids = _insert_customers(conn, snapshot_date, drift)
    application_ids = _insert_applications(conn, snapshot_date, customer_ids, officer_ids, branch_ids, drift)
    loan_ids = _insert_loans(conn, snapshot_date, customer_ids, officer_ids, branch_ids, application_ids, drift)

    # Pull back loan rows we just inserted so payments + collaterals stay consistent
    loan_meta: dict[int, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT loan_id, loan_amount, interest_rate, term_months, origination_date, monthly_payment "
        "FROM loans WHERE report_date = ?",
        (snapshot_date,),
    ):
        loan_meta[row[0]] = {
            "loan_amount": row[1],
            "interest_rate": row[2],
            "term_months": row[3],
            "origination_date": row[4],
            "monthly_payment": row[5],
        }
    loan_amounts = {lid: m["loan_amount"] for lid, m in loan_meta.items()}

    _insert_collaterals(conn, snapshot_date, loan_ids, loan_amounts, drift)
    _insert_payments(conn, snapshot_date, loan_ids, loan_meta, drift)
    _insert_credit_history(conn, snapshot_date, customer_ids, drift)


# Ordered child-first so DELETE never trips foreign-key constraints.
_SNAPSHOT_TABLES_DELETE_ORDER = (
    "credit_history",
    "payments",
    "collaterals",
    "loans",
    "applications",
    "customers",
    "loan_officers",
    "branches",
)


def _delete_snapshot_rows(conn: sqlite3.Connection, snapshot_date: str) -> None:
    for table in _SNAPSHOT_TABLES_DELETE_ORDER:
        conn.execute(f"DELETE FROM {table} WHERE report_date = ?", (snapshot_date,))


def create_mortgage_database(
    db_name: str | None = None,
    snapshot_date: str | None = None,
    description: str | None = None,
    properties: dict[str, Any] | None = None,
) -> str:
    """Create or extend a sample mortgage SQLite database with one data snapshot.

    Behavior mirrors :func:`app.database.setup_sample_db.create_sample_database`:

    * New ``(db_name, snapshot_date)`` → append snapshot rows; previous snapshots
      are preserved.
    * Existing ``(db_name, snapshot_date)`` → only that snapshot's rows and its
      dq_admin artifacts are replaced. Other snapshots are untouched.
    * First call for a ``db_name`` → file + schema are created automatically.

    Args:
        db_name: Unique database name (file will be ``<db_name>.db``).
        snapshot_date: REQUIRED. ISO ``YYYY-MM-DD`` calendar date tagging every
            row inserted by this call.
        description: Optional description stored in ``dq_admin_databases``.
        properties: Optional metadata dict (serialized as JSON).

    Returns:
        Absolute path to the created/updated database file.
    """
    if not snapshot_date:
        raise ValueError("snapshot_date is required (e.g. '2025-01-01').")
    snap = _validate_snapshot_date(snapshot_date)

    name = _validate_db_name(db_name or "mortgage_sample")
    db_path = _resolve_db_path(name)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    existing = list_snapshot_dates(name) if db_path.exists() else []
    is_replace = snap in existing
    others = [s for s in existing if s != snap]
    drift = min(len(others) / 4.0, 1.0)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA_SQL)
        if is_replace:
            conn.execute("PRAGMA foreign_keys = OFF")
            _delete_snapshot_rows(conn, snap)
            conn.execute("PRAGMA foreign_keys = ON")
        # Per-snapshot deterministic seeding: replays are stable, but different
        # snapshots produce genuinely different numeric values (loan amounts,
        # rates, balances, credit scores, etc.).
        random.seed(hash(snap) & 0xFFFFFFFF)
        _populate_snapshot(conn, snap, drift=drift)
        conn.commit()
    finally:
        conn.close()

    register_database(
        db_name=name,
        db_path=str(db_path),
        description=description or "Sample mortgage / home-loan dataset",
        properties=properties,
    )
    register_snapshot(name, snap)
    if is_replace:
        clear_snapshot_artifacts(name, snap)

    return str(db_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create / extend the mortgage sample database.")
    parser.add_argument("--db-name", default="mortgage_sample", help="Database name (default: mortgage_sample)")
    parser.add_argument("--snapshot-date", required=True, help="Snapshot date in YYYY-MM-DD")
    parser.add_argument("--description", default=None)
    args = parser.parse_args()

    path = create_mortgage_database(
        db_name=args.db_name,
        snapshot_date=args.snapshot_date,
        description=args.description,
    )
    print(f"Mortgage sample database ready at: {path}")

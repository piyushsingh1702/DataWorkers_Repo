"""
Creates a sample SQLite database with an e-commerce schema.
Includes realistic data with intentional quality issues for DQ testing.
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
    """Validate that ``snapshot_date`` is a real ISO ``YYYY-MM-DD`` calendar date."""
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

# NOTE: Single-column UNIQUE constraints on natural keys (email, sku, etc.) are
# replaced with composite UNIQUE(value, report_date) so the same logical row
# (e.g. customer 'james.smith0@example.com') can appear in multiple snapshots
# while still being unique within a snapshot.
SCHEMA_SQL = """
-- Categories
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL,
    description TEXT,
    parent_category_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_date TEXT NOT NULL,
    UNIQUE (category_name, report_date),
    FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
);

-- Suppliers
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    contact_name TEXT,
    contact_email TEXT,
    phone TEXT,
    address TEXT,
    city TEXT,
    country TEXT NOT NULL,
    rating REAL CHECK(rating >= 1.0 AND rating <= 5.0),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_date TEXT NOT NULL,
    UNIQUE (contact_email, report_date)
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    sku TEXT NOT NULL,
    description TEXT,
    category_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    unit_price REAL NOT NULL CHECK(unit_price > 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER DEFAULT 10,
    is_discontinued INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_date TEXT NOT NULL,
    UNIQUE (sku, report_date),
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);

-- Customers
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    date_of_birth TEXT,
    gender TEXT CHECK(gender IN ('M', 'F', 'Other', NULL)),
    address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    country TEXT NOT NULL DEFAULT 'US',
    registration_date TEXT NOT NULL DEFAULT (datetime('now')),
    is_active INTEGER NOT NULL DEFAULT 1,
    loyalty_tier TEXT CHECK(loyalty_tier IN ('Bronze', 'Silver', 'Gold', 'Platinum', NULL)),
    report_date TEXT NOT NULL,
    UNIQUE (email, report_date)
);

-- Employees
CREATE TABLE IF NOT EXISTS employees (
    employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    hire_date TEXT NOT NULL,
    department TEXT NOT NULL,
    job_title TEXT NOT NULL,
    salary REAL NOT NULL CHECK(salary > 0),
    manager_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    report_date TEXT NOT NULL,
    UNIQUE (email, report_date),
    FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    employee_id INTEGER,
    order_date TEXT NOT NULL,
    required_date TEXT,
    shipped_date TEXT,
    status TEXT NOT NULL CHECK(status IN ('Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled', 'Returned')),
    shipping_address TEXT,
    shipping_city TEXT,
    shipping_country TEXT,
    total_amount REAL NOT NULL CHECK(total_amount >= 0),
    report_date TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- Order Items
CREATE TABLE IF NOT EXISTS order_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price REAL NOT NULL CHECK(unit_price > 0),
    discount REAL DEFAULT 0.0 CHECK(discount >= 0 AND discount <= 1),
    report_date TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- Payments
CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    payment_date TEXT NOT NULL,
    amount REAL NOT NULL CHECK(amount > 0),
    payment_method TEXT NOT NULL CHECK(payment_method IN ('Credit Card', 'Debit Card', 'PayPal', 'Bank Transfer', 'Cash')),
    transaction_ref TEXT,
    status TEXT NOT NULL CHECK(status IN ('Pending', 'Completed', 'Failed', 'Refunded')),
    report_date TEXT NOT NULL,
    UNIQUE (transaction_ref, report_date),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- Shipping
CREATE TABLE IF NOT EXISTS shipping (
    shipping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    carrier TEXT NOT NULL,
    tracking_number TEXT,
    ship_date TEXT,
    estimated_delivery TEXT,
    actual_delivery TEXT,
    shipping_cost REAL NOT NULL CHECK(shipping_cost >= 0),
    status TEXT NOT NULL CHECK(status IN ('Preparing', 'In Transit', 'Delivered', 'Returned')),
    report_date TEXT NOT NULL,
    UNIQUE (tracking_number, report_date),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- Reviews
CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
    review_text TEXT,
    review_date TEXT NOT NULL,
    is_verified_purchase INTEGER NOT NULL DEFAULT 0,
    helpful_votes INTEGER DEFAULT 0,
    report_date TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
"""


def _random_date(start_year=2022, end_year=2025):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime("%Y-%m-%d %H:%M:%S")


def _random_date_only(start_year=1960, end_year=2005):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime("%Y-%m-%d")


def _insert_categories(conn, snapshot_date: str) -> dict[str, int]:
    """Insert categories for one snapshot. Returns mapping of name -> new category_id."""
    parents = [
        ("Electronics", "Electronic devices and accessories"),
        ("Clothing", "Apparel and fashion items"),
        ("Home & Kitchen", "Home appliances and kitchenware"),
        ("Books", "Physical and digital books"),
        ("Sports & Outdoors", "Sports equipment and outdoor gear"),
    ]
    name_to_id: dict[str, int] = {}
    for name, desc in parents:
        cur = conn.execute(
            "INSERT INTO categories (category_name, description, parent_category_id, report_date) VALUES (?, ?, NULL, ?)",
            (name, desc, snapshot_date),
        )
        name_to_id[name] = cur.lastrowid

    children = [
        ("Smartphones", "Mobile phones and accessories", "Electronics"),
        ("Laptops", "Portable computers", "Electronics"),
        ("Men's Clothing", "Men's fashion", "Clothing"),
        ("Women's Clothing", "Women's fashion", "Clothing"),
        ("Cookware", "Pots, pans, and cooking tools", "Home & Kitchen"),
    ]
    for name, desc, parent_name in children:
        cur = conn.execute(
            "INSERT INTO categories (category_name, description, parent_category_id, report_date) VALUES (?, ?, ?, ?)",
            (name, desc, name_to_id[parent_name], snapshot_date),
        )
        name_to_id[name] = cur.lastrowid
    return name_to_id


def _insert_suppliers(conn, snapshot_date: str) -> list[int]:
    """Insert suppliers for one snapshot. Returns list of new supplier_ids."""
    suppliers = [
        ("TechCorp Inc.", "John Smith", "john@techcorp.com", "+1-555-0101", "123 Tech Blvd", "San Jose", "US", 4.5),
        ("Fashion Forward Ltd.", "Emma Wilson", "emma@fashionforward.co.uk", "+44-20-7946-0958", "45 Oxford St", "London", "UK", 4.2),
        ("HomeGoods Global", "Li Wei", "li.wei@homegoods.cn", "+86-10-6552-1234", "88 Nanjing Rd", "Shanghai", "CN", 3.8),
        ("BookWorld Publishers", "Maria Garcia", "maria@bookworld.com", "+1-555-0202", "500 Fifth Ave", "New York", "US", 4.7),
        ("SportElite", "Hans Mueller", "hans@sportelite.de", "+49-89-1234-5678", "10 Olympia Str", "Munich", "DE", 4.0),
        ("MegaSupply Co.", "Sarah Johnson", None, "+1-555-0303", "789 Industrial Pkwy", "Chicago", "US", 3.5),
        ("Pacific Traders", "Yuki Tanaka", "yuki@pacifictraders.jp", None, "2-1 Shibuya", "Tokyo", "JP", 4.3),
        ("Global Electronics", "Ahmed Hassan", "ahmed@globalelec.ae", "+971-4-123-4567", "Dubai Trade Center", "Dubai", "AE", 3.9),
    ]
    ids: list[int] = []
    for s in suppliers:
        cur = conn.execute(
            "INSERT INTO suppliers (company_name, contact_name, contact_email, phone, address, city, country, rating, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*s, snapshot_date),
        )
        ids.append(cur.lastrowid)
    return ids


def _insert_products(
    conn, snapshot_date: str, cat_ids: dict[str, int], sup_ids: list[int]
) -> list[int]:
    """Insert products for one snapshot. Returns list of new product_ids."""
    # (name, sku, description, category_name, supplier_index, price, stock, reorder)
    product_templates = [
        ("iPhone 15 Pro", "SKU-ELEC-001", "Latest Apple smartphone", "Smartphones", 0, 999.99, 150, 20),
        ("Samsung Galaxy S24", "SKU-ELEC-002", "Samsung flagship phone", "Smartphones", 7, 849.99, 200, 25),
        ("MacBook Pro 16\"", "SKU-ELEC-003", "Apple laptop for professionals", "Laptops", 0, 2499.99, 50, 10),
        ("Dell XPS 15", "SKU-ELEC-004", "Premium Windows laptop", "Laptops", 7, 1799.99, 75, 15),
        ("Sony WH-1000XM5", "SKU-ELEC-005", "Noise cancelling headphones", "Electronics", 7, 349.99, 300, 30),
        ("Men's Classic Shirt", "SKU-CLO-001", "Cotton formal shirt", "Men's Clothing", 1, 49.99, 500, 50),
        ("Women's Summer Dress", "SKU-CLO-002", "Lightweight summer dress", "Women's Clothing", 1, 79.99, 350, 40),
        ("Running Shoes Pro", "SKU-CLO-003", "Professional running shoes", "Sports & Outdoors", 4, 129.99, 200, 25),
        ("Winter Jacket", "SKU-CLO-004", "Warm winter jacket", "Men's Clothing", 1, 199.99, 100, 15),
        ("Yoga Pants", "SKU-CLO-005", None, "Women's Clothing", 1, 39.99, 600, 60),
        ("Stainless Steel Cookware Set", "SKU-HOM-001", "10-piece cookware set", "Cookware", 2, 299.99, 80, 10),
        ("Coffee Machine Deluxe", "SKU-HOM-002", "Automatic espresso machine", "Home & Kitchen", 2, 599.99, 45, 8),
        ("Robot Vacuum", "SKU-HOM-003", "AI-powered robot vacuum", "Home & Kitchen", 0, 449.99, 120, 15),
        ("Air Purifier", "SKU-HOM-004", "HEPA air purifier", "Home & Kitchen", 2, 249.99, 90, 12),
        ("Smart Thermostat", "SKU-HOM-005", "WiFi-enabled thermostat", "Home & Kitchen", 0, 179.99, 200, 20),
        ("Python Programming", "SKU-BOK-001", "Learn Python in 30 days", "Books", 3, 34.99, 1000, 100),
        ("Data Science Handbook", "SKU-BOK-002", "Comprehensive data science guide", "Books", 3, 44.99, 500, 50),
        ("Fiction: The Last Code", "SKU-BOK-003", "Bestselling tech thriller", "Books", 3, 14.99, 2000, 200),
        ("Mountain Bike Pro", "SKU-SPT-001", "Professional mountain bike", "Sports & Outdoors", 4, 1299.99, 30, 5),
        ("Tennis Racket Elite", "SKU-SPT-002", "Professional tennis racket", "Sports & Outdoors", 4, 249.99, 150, 20),
        ("Camping Tent 4P", "SKU-SPT-003", "4-person camping tent", "Sports & Outdoors", 4, 189.99, 70, 10),
        ("Fitness Tracker", "SKU-SPT-004", "Advanced fitness tracking watch", "Sports & Outdoors", 0, 199.99, 400, 40),
        ("Protein Powder", "SKU-SPT-005", "Premium whey protein 2kg", "Sports & Outdoors", 5, 54.99, 800, 80),
        ("Wireless Charger", "SKU-ELEC-006", "Fast wireless charging pad", "Electronics", 7, 29.99, 1000, 100),
        ("USB-C Hub", "SKU-ELEC-007", "7-in-1 USB-C hub", "Electronics", 0, 59.99, 500, 50),
    ]
    ids: list[int] = []
    for name, sku, desc, cat_name, sup_idx, price, stock, reorder in product_templates:
        cur = conn.execute(
            "INSERT INTO products (product_name, sku, description, category_id, supplier_id, unit_price, stock_quantity, reorder_level, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, sku, desc, cat_ids[cat_name], sup_ids[sup_idx], price, stock, reorder, snapshot_date),
        )
        ids.append(cur.lastrowid)
    return ids


def _insert_customers(conn, snapshot_date: str, drift: float = 0.0) -> list[int]:
    """Insert customers. ``drift`` (0.0-1.0) increases the rate of intentional DQ issues."""
    first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
                   "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
                   "Thomas", "Sarah", "Christopher", "Karen", "Daniel", "Lisa", "Matthew", "Nancy",
                   "Anthony", "Betty", "Mark", "Margaret", "Donald", "Sandra"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
                  "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
                  "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
                  "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson"]
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
              "San Antonio", "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville",
              "Fort Worth", "Columbus", "Charlotte", "Indianapolis", "San Francisco", "Seattle"]
    states = ["NY", "CA", "IL", "TX", "AZ", "PA", "TX", "CA", "TX", "CA", "TX", "FL",
              "TX", "OH", "NC", "IN", "CA", "WA"]
    tiers = ["Bronze", "Silver", "Gold", "Platinum", None]
    genders = ["M", "F", "Other", None]

    null_phone_rate = min(0.5, 0.15 + drift * 0.2)
    null_dob_rate = min(0.4, 0.10 + drift * 0.15)
    null_postal_rate = min(0.3, 0.08 + drift * 0.10)
    inactive_rate = min(0.25, 0.05 + drift * 0.10)

    ids: list[int] = []
    for i in range(200):
        fn = random.choice(first_names)
        ln = random.choice(last_names)
        city_idx = random.randint(0, len(cities) - 1)
        email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
        phone = f"+1-555-{random.randint(1000, 9999)}" if random.random() > null_phone_rate else None
        dob = _random_date_only(1960, 2005) if random.random() > null_dob_rate else None
        gender = random.choice(genders)
        postal = f"{random.randint(10000, 99999)}" if random.random() > null_postal_rate else None
        tier = random.choice(tiers)

        cur = conn.execute(
            "INSERT INTO customers (first_name, last_name, email, phone, date_of_birth, gender, address, city, state, postal_code, country, registration_date, is_active, loyalty_tier, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fn, ln, email, phone, dob, gender,
                f"{random.randint(1, 999)} Main St",
                cities[city_idx], states[city_idx], postal, "US",
                _random_date(2020, 2024), 0 if random.random() < inactive_rate else 1, tier,
                snapshot_date,
            ),
        )
        ids.append(cur.lastrowid)

    # Intentional duplicate-name customer for uniqueness testing
    cur = conn.execute(
        "INSERT INTO customers (first_name, last_name, email, phone, date_of_birth, gender, address, city, state, postal_code, country, registration_date, is_active, loyalty_tier, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("James", "Smith", "james.smith.dup@example.com", "+1-555-0000", "1990-01-01", "M",
         "123 Main St", "New York", "NY", "10001", "US", "2023-01-01 00:00:00", 1, "Gold", snapshot_date),
    )
    ids.append(cur.lastrowid)
    return ids


def _insert_employees(conn, snapshot_date: str) -> list[int]:
    """Insert employees and stitch up manager_id references within this snapshot."""
    # (first, last, email, phone, hire_date, dept, title, salary, manager_index_in_list_or_None)
    rows = [
        ("Alice", "Manager", "alice.manager@company.com", "+1-555-1001", "2018-03-15", "Sales", "Sales Director", 120000, None),
        ("Bob", "Tech", "bob.tech@company.com", "+1-555-1002", "2019-06-01", "IT", "IT Manager", 110000, None),
        ("Carol", "Support", "carol.support@company.com", "+1-555-1003", "2020-01-10", "Support", "Support Lead", 85000, None),
        ("Dave", "Sales", "dave.sales@company.com", "+1-555-1004", "2021-04-20", "Sales", "Sales Rep", 65000, 0),
        ("Eve", "Sales", "eve.sales@company.com", "+1-555-1005", "2021-07-15", "Sales", "Sales Rep", 63000, 0),
        ("Frank", "Dev", "frank.dev@company.com", "+1-555-1006", "2020-09-01", "IT", "Software Engineer", 95000, 1),
        ("Grace", "Support", "grace.support@company.com", "+1-555-1007", "2022-02-01", "Support", "Support Agent", 55000, 2),
        ("Henry", "Warehouse", "henry.warehouse@company.com", "+1-555-1008", "2019-11-10", "Operations", "Warehouse Manager", 72000, None),
        ("Ivy", "Marketing", "ivy.marketing@company.com", "+1-555-1009", "2023-01-05", "Marketing", "Marketing Specialist", 68000, None),
        ("Jack", "Finance", "jack.finance@company.com", "+1-555-1010", "2020-05-20", "Finance", "Accountant", 78000, None),
    ]
    ids: list[int] = []
    for first, last, email, phone, hire, dept, title, salary, mgr_idx in rows:
        manager_id = ids[mgr_idx] if mgr_idx is not None and mgr_idx < len(ids) else None
        cur = conn.execute(
            "INSERT INTO employees (first_name, last_name, email, phone, hire_date, department, job_title, salary, manager_id, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (first, last, email, phone, hire, dept, title, salary, manager_id, snapshot_date),
        )
        ids.append(cur.lastrowid)
    return ids


def _insert_orders(
    conn,
    snapshot_date: str,
    customer_ids: list[int],
    employee_ids: list[int],
    drift: float = 0.0,
) -> list[int]:
    statuses = ["Pending", "Processing", "Shipped", "Delivered", "Cancelled", "Returned"]
    status_weights = [0.05, 0.1, 0.15, 0.55, 0.1, 0.05]
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Seattle"]

    null_addr_rate = min(0.25, 0.05 + drift * 0.10)
    sales_employee_pool = [employee_ids[0], employee_ids[3], employee_ids[4], None] if len(employee_ids) > 4 else [None]

    ids: list[int] = []
    for _ in range(500):
        customer_id = random.choice(customer_ids)
        employee_id = random.choice(sales_employee_pool)
        order_date = _random_date(2022, 2025)
        order_dt = datetime.strptime(order_date, "%Y-%m-%d %H:%M:%S")
        required_date = (order_dt + timedelta(days=random.randint(3, 14))).strftime("%Y-%m-%d %H:%M:%S")
        status = random.choices(statuses, weights=status_weights, k=1)[0]

        shipped_date = None
        if status in ("Shipped", "Delivered", "Returned"):
            shipped_date = (order_dt + timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d %H:%M:%S")

        ship_addr = f"{random.randint(1, 999)} Delivery St" if random.random() > null_addr_rate else None
        ship_city = random.choice(cities) if ship_addr else None
        total = round(random.uniform(15.0, 2500.0), 2)

        cur = conn.execute(
            "INSERT INTO orders (customer_id, employee_id, order_date, required_date, shipped_date, status, shipping_address, shipping_city, shipping_country, total_amount, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (customer_id, employee_id, order_date, required_date, shipped_date,
             status, ship_addr, ship_city, "US", total, snapshot_date),
        )
        ids.append(cur.lastrowid)

    # Intentional stale "Pending" orders (timeliness issue)
    for _ in range(10):
        old_date = _random_date(2022, 2022)
        cur = conn.execute(
            "INSERT INTO orders (customer_id, employee_id, order_date, required_date, shipped_date, status, shipping_address, shipping_city, shipping_country, total_amount, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (random.choice(customer_ids), None, old_date, old_date, None,
             "Pending", "123 Old St", "Chicago", "US", round(random.uniform(50, 500), 2), snapshot_date),
        )
        ids.append(cur.lastrowid)
    return ids


def _insert_order_items(conn, snapshot_date: str, order_ids: list[int], product_ids: list[int]) -> None:
    for order_id in order_ids:
        num_items = random.randint(1, 5)
        for _ in range(num_items):
            product_id = random.choice(product_ids)
            quantity = random.randint(1, 10)
            unit_price = round(random.uniform(10.0, 999.99), 2)
            discount = round(random.choice([0, 0, 0, 0.05, 0.1, 0.15, 0.2]), 2)
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount, report_date) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, product_id, quantity, unit_price, discount, snapshot_date),
            )


def _insert_payments(conn, snapshot_date: str, order_ids: list[int], drift: float = 0.0) -> None:
    methods = ["Credit Card", "Debit Card", "PayPal", "Bank Transfer", "Cash"]
    method_weights = [0.4, 0.2, 0.25, 0.1, 0.05]
    payment_statuses = ["Completed", "Completed", "Completed", "Pending", "Failed", "Refunded"]
    null_txn_rate = min(0.15, 0.03 + drift * 0.08)

    for order_id in order_ids:
        pay_date = _random_date(2022, 2025)
        amount = round(random.uniform(15.0, 2500.0), 2)
        method = random.choices(methods, weights=method_weights, k=1)[0]
        txn_ref = f"TXN-{order_id:06d}-{random.randint(1000, 9999)}" if random.random() > null_txn_rate else None
        status = random.choice(payment_statuses)
        conn.execute(
            "INSERT INTO payments (order_id, payment_date, amount, payment_method, transaction_ref, status, report_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (order_id, pay_date, amount, method, txn_ref, status, snapshot_date),
        )


def _insert_shipping(conn, snapshot_date: str, order_ids: list[int], drift: float = 0.0) -> None:
    carriers = ["FedEx", "UPS", "USPS", "DHL", "Amazon Logistics"]
    ship_statuses = ["Preparing", "In Transit", "Delivered", "Returned"]
    null_track_rate = min(0.2, 0.05 + drift * 0.08)
    null_actual_rate = min(0.4, 0.20 + drift * 0.10)

    # Not all orders ship; pick ~89% of the snapshot's orders.
    sample_size = int(len(order_ids) * 0.89)
    for order_id in random.sample(order_ids, sample_size):
        carrier = random.choice(carriers)
        tracking = f"{carrier[:3].upper()}-{random.randint(100000000, 999999999)}" if random.random() > null_track_rate else None
        ship_date = _random_date(2022, 2025)
        ship_dt = datetime.strptime(ship_date, "%Y-%m-%d %H:%M:%S")
        est_delivery = (ship_dt + timedelta(days=random.randint(2, 7))).strftime("%Y-%m-%d %H:%M:%S")
        actual_delivery = (ship_dt + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d %H:%M:%S") if random.random() > null_actual_rate else None
        cost = round(random.uniform(5.0, 50.0), 2)
        status = random.choice(ship_statuses)
        conn.execute(
            "INSERT INTO shipping (order_id, carrier, tracking_number, ship_date, estimated_delivery, actual_delivery, shipping_cost, status, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, carrier, tracking, ship_date, est_delivery, actual_delivery, cost, status, snapshot_date),
        )


def _insert_reviews(conn, snapshot_date: str, product_ids: list[int], customer_ids: list[int]) -> None:
    review_texts = [
        "Great product, highly recommend!", "Decent quality for the price.",
        "Not what I expected.", "Amazing! Will buy again.",
        "Terrible quality, returning it.", "Good value for money.",
        "Perfect gift!", "Arrived damaged but seller replaced quickly.",
        "Exactly as described.", "Could be better.",
        None, None, None,
    ]

    for _ in range(300):
        product_id = random.choice(product_ids)
        customer_id = random.choice(customer_ids)
        rating = random.choices([1, 2, 3, 4, 5], weights=[0.05, 0.1, 0.2, 0.35, 0.3], k=1)[0]
        text = random.choice(review_texts)
        review_date = _random_date(2022, 2025)
        verified = 1 if random.random() > 0.3 else 0
        helpful = random.randint(0, 50)
        conn.execute(
            "INSERT INTO reviews (product_id, customer_id, rating, review_text, review_date, is_verified_purchase, helpful_votes, report_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (product_id, customer_id, rating, text, review_date, verified, helpful, snapshot_date),
        )


def _populate_snapshot(conn: sqlite3.Connection, snapshot_date: str, drift: float) -> None:
    """Insert one full snapshot of the e-commerce dataset.

    Foreign-key references stay intra-snapshot: every order/payment/shipping/review
    references customer/product/employee IDs that were also created for this
    ``snapshot_date``. ``drift`` (0.0-1.0) gradually worsens DQ issue rates so
    later snapshots have visibly different DQ scores.
    """
    cat_ids = _insert_categories(conn, snapshot_date)
    sup_ids = _insert_suppliers(conn, snapshot_date)
    prod_ids = _insert_products(conn, snapshot_date, cat_ids, sup_ids)
    cust_ids = _insert_customers(conn, snapshot_date, drift=drift)
    emp_ids = _insert_employees(conn, snapshot_date)
    order_ids = _insert_orders(conn, snapshot_date, cust_ids, emp_ids, drift=drift)
    _insert_order_items(conn, snapshot_date, order_ids, prod_ids)
    _insert_payments(conn, snapshot_date, order_ids, drift=drift)
    _insert_shipping(conn, snapshot_date, order_ids, drift=drift)
    _insert_reviews(conn, snapshot_date, prod_ids, cust_ids)


# Tables that carry a ``report_date`` column. Order matters for deletion: child
# tables (FK referencers) come BEFORE their parents so we can safely DELETE
# this snapshot's rows without violating foreign-key constraints. Add a new
# table to this list whenever the schema gains another snapshot-scoped table.
_SNAPSHOT_TABLES_DELETE_ORDER = (
    "reviews",
    "shipping",
    "payments",
    "order_items",
    "orders",
    "products",
    "employees",
    "customers",
    "suppliers",
    "categories",
)


def _delete_snapshot_rows(conn: sqlite3.Connection, snapshot_date: str) -> None:
    """Remove every row tagged with ``snapshot_date`` across all data tables."""
    for table in _SNAPSHOT_TABLES_DELETE_ORDER:
        conn.execute(
            f"DELETE FROM {table} WHERE report_date = ?",
            (snapshot_date,),
        )


def create_sample_database(
    db_name: str | None = None,
    snapshot_date: str | None = None,
    description: str | None = None,
    properties: dict[str, Any] | None = None,
) -> str:
    """Create or extend a sample SQLite database with one data snapshot.

    Behavior is implicit:

    * If ``(db_name, snapshot_date)`` does not yet exist, a new snapshot is
      appended to the existing database (or the file is created on first use).
    * If ``(db_name, snapshot_date)`` already exists, only that snapshot's
      rows are deleted and re-inserted with the same ``snapshot_date``. Other
      snapshots in the same database are preserved. Stale dq_admin artifacts
      (technical catalogue, glossary, classification, DQ rules, DQ scores,
      DQ markdown report) for that snapshot are also cleared so re-running the
      pipeline does not return outdated metadata.

    Args:
        db_name: Unique database name (file will be ``<db_name>.db``).
        snapshot_date: REQUIRED. ISO ``YYYY-MM-DD`` calendar date that tags
            every row inserted by this call.
        description: Optional human-readable description stored in
            ``dq_admin_databases``.
        properties: Optional dict of extra metadata (serialized as JSON).

    Returns:
        The absolute path to the database file.
    """
    if not snapshot_date:
        raise ValueError("snapshot_date is required (e.g. '2025-01-01').")
    snap = _validate_snapshot_date(snapshot_date)

    name = _validate_db_name(db_name or settings.default_db_name)
    db_path = _resolve_db_path(name)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Drift increases with the count of *other* snapshots already loaded.
    # When this same snapshot is being replaced we exclude it so the drift
    # value is stable across replays of the same date.
    existing = list_snapshot_dates(name) if db_path.exists() else []
    is_replace = snap in existing
    others = [s for s in existing if s != snap]
    drift = min(len(others) / 4.0, 1.0)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        conn.executescript(SCHEMA_SQL)
        if is_replace:
            # Drop FK enforcement during the cleanup so we can DELETE rows
            # in a single transaction without ordering surprises if the
            # schema evolves. Re-enabled immediately after.
            conn.execute("PRAGMA foreign_keys = OFF")
            _delete_snapshot_rows(conn, snap)
            conn.execute("PRAGMA foreign_keys = ON")
        # Reseed deterministically per snapshot so repeat runs are stable.
        random.seed(hash(snap) & 0xFFFFFFFF)
        _populate_snapshot(conn, snap, drift=drift)
        conn.commit()
    finally:
        conn.close()

    register_database(
        db_name=name,
        db_path=str(db_path),
        description=description,
        properties=properties,
    )
    register_snapshot(name, snap)
    if is_replace:
        # Wipe downstream artifacts so they get regenerated against the
        # freshly loaded rows on the next pipeline / agent run.
        clear_snapshot_artifacts(name, snap)

    return str(db_path)

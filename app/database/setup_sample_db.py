"""
Creates a sample SQLite database with an e-commerce schema.
Includes realistic data with intentional quality issues for DQ testing.
"""

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app.config.settings import settings

SCHEMA_SQL = """
-- Categories
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE,
    description TEXT,
    parent_category_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
);

-- Suppliers
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    contact_name TEXT,
    contact_email TEXT UNIQUE,
    phone TEXT,
    address TEXT,
    city TEXT,
    country TEXT NOT NULL,
    rating REAL CHECK(rating >= 1.0 AND rating <= 5.0),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    sku TEXT UNIQUE NOT NULL,
    description TEXT,
    category_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    unit_price REAL NOT NULL CHECK(unit_price > 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER DEFAULT 10,
    is_discontinued INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);

-- Customers
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
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
    loyalty_tier TEXT CHECK(loyalty_tier IN ('Bronze', 'Silver', 'Gold', 'Platinum', NULL))
);

-- Employees
CREATE TABLE IF NOT EXISTS employees (
    employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    hire_date TEXT NOT NULL,
    department TEXT NOT NULL,
    job_title TEXT NOT NULL,
    salary REAL NOT NULL CHECK(salary > 0),
    manager_id INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
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
    transaction_ref TEXT UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('Pending', 'Completed', 'Failed', 'Refunded')),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- Shipping
CREATE TABLE IF NOT EXISTS shipping (
    shipping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    carrier TEXT NOT NULL,
    tracking_number TEXT UNIQUE,
    ship_date TEXT,
    estimated_delivery TEXT,
    actual_delivery TEXT,
    shipping_cost REAL NOT NULL CHECK(shipping_cost >= 0),
    status TEXT NOT NULL CHECK(status IN ('Preparing', 'In Transit', 'Delivered', 'Returned')),
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


def _insert_categories(conn):
    categories = [
        ("Electronics", "Electronic devices and accessories", None),
        ("Clothing", "Apparel and fashion items", None),
        ("Home & Kitchen", "Home appliances and kitchenware", None),
        ("Books", "Physical and digital books", None),
        ("Sports & Outdoors", "Sports equipment and outdoor gear", None),
        ("Smartphones", "Mobile phones and accessories", 1),
        ("Laptops", "Portable computers", 1),
        ("Men's Clothing", "Men's fashion", 2),
        ("Women's Clothing", "Women's fashion", 2),
        ("Cookware", "Pots, pans, and cooking tools", 3),
    ]
    conn.executemany(
        "INSERT INTO categories (category_name, description, parent_category_id) VALUES (?, ?, ?)",
        categories,
    )


def _insert_suppliers(conn):
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
    conn.executemany(
        "INSERT INTO suppliers (company_name, contact_name, contact_email, phone, address, city, country, rating) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        suppliers,
    )


def _insert_products(conn):
    products = []
    product_templates = [
        ("iPhone 15 Pro", "SKU-ELEC-001", "Latest Apple smartphone", 6, 1, 999.99, 150, 20),
        ("Samsung Galaxy S24", "SKU-ELEC-002", "Samsung flagship phone", 6, 8, 849.99, 200, 25),
        ("MacBook Pro 16\"", "SKU-ELEC-003", "Apple laptop for professionals", 7, 1, 2499.99, 50, 10),
        ("Dell XPS 15", "SKU-ELEC-004", "Premium Windows laptop", 7, 8, 1799.99, 75, 15),
        ("Sony WH-1000XM5", "SKU-ELEC-005", "Noise cancelling headphones", 1, 8, 349.99, 300, 30),
        ("Men's Classic Shirt", "SKU-CLO-001", "Cotton formal shirt", 8, 2, 49.99, 500, 50),
        ("Women's Summer Dress", "SKU-CLO-002", "Lightweight summer dress", 9, 2, 79.99, 350, 40),
        ("Running Shoes Pro", "SKU-CLO-003", "Professional running shoes", 5, 5, 129.99, 200, 25),
        ("Winter Jacket", "SKU-CLO-004", "Warm winter jacket", 8, 2, 199.99, 100, 15),
        ("Yoga Pants", "SKU-CLO-005", None, 9, 2, 39.99, 600, 60),
        ("Stainless Steel Cookware Set", "SKU-HOM-001", "10-piece cookware set", 10, 3, 299.99, 80, 10),
        ("Coffee Machine Deluxe", "SKU-HOM-002", "Automatic espresso machine", 3, 3, 599.99, 45, 8),
        ("Robot Vacuum", "SKU-HOM-003", "AI-powered robot vacuum", 3, 1, 449.99, 120, 15),
        ("Air Purifier", "SKU-HOM-004", "HEPA air purifier", 3, 3, 249.99, 90, 12),
        ("Smart Thermostat", "SKU-HOM-005", "WiFi-enabled thermostat", 3, 1, 179.99, 200, 20),
        ("Python Programming", "SKU-BOK-001", "Learn Python in 30 days", 4, 4, 34.99, 1000, 100),
        ("Data Science Handbook", "SKU-BOK-002", "Comprehensive data science guide", 4, 4, 44.99, 500, 50),
        ("Fiction: The Last Code", "SKU-BOK-003", "Bestselling tech thriller", 4, 4, 14.99, 2000, 200),
        ("Mountain Bike Pro", "SKU-SPT-001", "Professional mountain bike", 5, 5, 1299.99, 30, 5),
        ("Tennis Racket Elite", "SKU-SPT-002", "Professional tennis racket", 5, 5, 249.99, 150, 20),
        ("Camping Tent 4P", "SKU-SPT-003", "4-person camping tent", 5, 5, 189.99, 70, 10),
        ("Fitness Tracker", "SKU-SPT-004", "Advanced fitness tracking watch", 5, 1, 199.99, 400, 40),
        ("Protein Powder", "SKU-SPT-005", "Premium whey protein 2kg", 5, 6, 54.99, 800, 80),
        ("Wireless Charger", "SKU-ELEC-006", "Fast wireless charging pad", 1, 8, 29.99, 1000, 100),
        ("USB-C Hub", "SKU-ELEC-007", "7-in-1 USB-C hub", 1, 1, 59.99, 500, 50),
    ]
    for p in product_templates:
        products.append(p)
    conn.executemany(
        "INSERT INTO products (product_name, sku, description, category_id, supplier_id, unit_price, stock_quantity, reorder_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        products,
    )


def _insert_customers(conn):
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

    customers = []
    for i in range(200):
        fn = random.choice(first_names)
        ln = random.choice(last_names)
        city_idx = random.randint(0, len(cities) - 1)
        email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
        # Intentional quality issues: some missing phones, invalid formats
        phone = f"+1-555-{random.randint(1000, 9999)}" if random.random() > 0.15 else None
        dob = _random_date_only(1960, 2005) if random.random() > 0.1 else None
        gender = random.choice(genders)
        postal = f"{random.randint(10000, 99999)}" if random.random() > 0.08 else None
        tier = random.choice(tiers)

        customers.append((
            fn, ln, email, phone, dob, gender,
            f"{random.randint(1, 999)} Main St",
            cities[city_idx], states[city_idx], postal, "US",
            _random_date(2020, 2024), 1 if random.random() > 0.05 else 0, tier
        ))

    # Add some intentional duplicates (same name, different email) for uniqueness testing
    customers.append(("James", "Smith", "james.smith.dup@example.com", "+1-555-0000", "1990-01-01", "M",
                      "123 Main St", "New York", "NY", "10001", "US", "2023-01-01 00:00:00", 1, "Gold"))

    conn.executemany(
        "INSERT INTO customers (first_name, last_name, email, phone, date_of_birth, gender, address, city, state, postal_code, country, registration_date, is_active, loyalty_tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        customers,
    )


def _insert_employees(conn):
    employees = [
        ("Alice", "Manager", "alice.manager@company.com", "+1-555-1001", "2018-03-15", "Sales", "Sales Director", 120000, None),
        ("Bob", "Tech", "bob.tech@company.com", "+1-555-1002", "2019-06-01", "IT", "IT Manager", 110000, None),
        ("Carol", "Support", "carol.support@company.com", "+1-555-1003", "2020-01-10", "Support", "Support Lead", 85000, None),
        ("Dave", "Sales", "dave.sales@company.com", "+1-555-1004", "2021-04-20", "Sales", "Sales Rep", 65000, 1),
        ("Eve", "Sales", "eve.sales@company.com", "+1-555-1005", "2021-07-15", "Sales", "Sales Rep", 63000, 1),
        ("Frank", "Dev", "frank.dev@company.com", "+1-555-1006", "2020-09-01", "IT", "Software Engineer", 95000, 2),
        ("Grace", "Support", "grace.support@company.com", "+1-555-1007", "2022-02-01", "Support", "Support Agent", 55000, 3),
        ("Henry", "Warehouse", "henry.warehouse@company.com", "+1-555-1008", "2019-11-10", "Operations", "Warehouse Manager", 72000, None),
        ("Ivy", "Marketing", "ivy.marketing@company.com", "+1-555-1009", "2023-01-05", "Marketing", "Marketing Specialist", 68000, None),
        ("Jack", "Finance", "jack.finance@company.com", "+1-555-1010", "2020-05-20", "Finance", "Accountant", 78000, None),
    ]
    conn.executemany(
        "INSERT INTO employees (first_name, last_name, email, phone, hire_date, department, job_title, salary, manager_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        employees,
    )


def _insert_orders(conn):
    statuses = ["Pending", "Processing", "Shipped", "Delivered", "Cancelled", "Returned"]
    status_weights = [0.05, 0.1, 0.15, 0.55, 0.1, 0.05]
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Seattle"]

    orders = []
    for i in range(500):
        customer_id = random.randint(1, 200)
        employee_id = random.choice([1, 4, 5, None])
        order_date = _random_date(2022, 2025)
        order_dt = datetime.strptime(order_date, "%Y-%m-%d %H:%M:%S")
        required_date = (order_dt + timedelta(days=random.randint(3, 14))).strftime("%Y-%m-%d %H:%M:%S")
        status = random.choices(statuses, weights=status_weights, k=1)[0]

        shipped_date = None
        if status in ("Shipped", "Delivered", "Returned"):
            shipped_date = (order_dt + timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%d %H:%M:%S")

        # Intentional: some orders missing shipping address
        ship_addr = f"{random.randint(1, 999)} Delivery St" if random.random() > 0.05 else None
        ship_city = random.choice(cities) if ship_addr else None
        total = round(random.uniform(15.0, 2500.0), 2)

        orders.append((
            customer_id, employee_id, order_date, required_date, shipped_date,
            status, ship_addr, ship_city, "US", total
        ))

    # Intentional: some old stale orders still in "Pending" (timeliness issue)
    for _ in range(10):
        old_date = _random_date(2022, 2022)
        orders.append((
            random.randint(1, 200), None, old_date, old_date, None,
            "Pending", "123 Old St", "Chicago", "US", round(random.uniform(50, 500), 2)
        ))

    conn.executemany(
        "INSERT INTO orders (customer_id, employee_id, order_date, required_date, shipped_date, status, shipping_address, shipping_city, shipping_country, total_amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        orders,
    )


def _insert_order_items(conn):
    items = []
    for order_id in range(1, 511):
        num_items = random.randint(1, 5)
        for _ in range(num_items):
            product_id = random.randint(1, 25)
            quantity = random.randint(1, 10)
            unit_price = round(random.uniform(10.0, 999.99), 2)
            discount = round(random.choice([0, 0, 0, 0.05, 0.1, 0.15, 0.2]), 2)
            items.append((order_id, product_id, quantity, unit_price, discount))
    conn.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount) VALUES (?, ?, ?, ?, ?)",
        items,
    )


def _insert_payments(conn):
    methods = ["Credit Card", "Debit Card", "PayPal", "Bank Transfer", "Cash"]
    method_weights = [0.4, 0.2, 0.25, 0.1, 0.05]
    payment_statuses = ["Completed", "Completed", "Completed", "Pending", "Failed", "Refunded"]

    payments = []
    for order_id in range(1, 511):
        pay_date = _random_date(2022, 2025)
        amount = round(random.uniform(15.0, 2500.0), 2)
        method = random.choices(methods, weights=method_weights, k=1)[0]
        txn_ref = f"TXN-{order_id:06d}-{random.randint(1000, 9999)}" if random.random() > 0.03 else None
        status = random.choice(payment_statuses)
        payments.append((order_id, pay_date, amount, method, txn_ref, status))

    conn.executemany(
        "INSERT INTO payments (order_id, payment_date, amount, payment_method, transaction_ref, status) VALUES (?, ?, ?, ?, ?, ?)",
        payments,
    )


def _insert_shipping(conn):
    carriers = ["FedEx", "UPS", "USPS", "DHL", "Amazon Logistics"]
    ship_statuses = ["Preparing", "In Transit", "Delivered", "Returned"]

    shipments = []
    for order_id in range(1, 450):  # Not all orders have shipping
        carrier = random.choice(carriers)
        tracking = f"{carrier[:3].upper()}-{random.randint(100000000, 999999999)}" if random.random() > 0.05 else None
        ship_date = _random_date(2022, 2025)
        ship_dt = datetime.strptime(ship_date, "%Y-%m-%d %H:%M:%S")
        est_delivery = (ship_dt + timedelta(days=random.randint(2, 7))).strftime("%Y-%m-%d %H:%M:%S")
        # Intentional: some delivered late
        actual_delivery = (ship_dt + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d %H:%M:%S") if random.random() > 0.2 else None
        cost = round(random.uniform(5.0, 50.0), 2)
        status = random.choice(ship_statuses)
        shipments.append((order_id, carrier, tracking, ship_date, est_delivery, actual_delivery, cost, status))

    conn.executemany(
        "INSERT INTO shipping (order_id, carrier, tracking_number, ship_date, estimated_delivery, actual_delivery, shipping_cost, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        shipments,
    )


def _insert_reviews(conn):
    review_texts = [
        "Great product, highly recommend!", "Decent quality for the price.",
        "Not what I expected.", "Amazing! Will buy again.",
        "Terrible quality, returning it.", "Good value for money.",
        "Perfect gift!", "Arrived damaged but seller replaced quickly.",
        "Exactly as described.", "Could be better.",
        None, None, None,  # Some reviews without text
    ]

    reviews = []
    for _ in range(300):
        product_id = random.randint(1, 25)
        customer_id = random.randint(1, 200)
        rating = random.choices([1, 2, 3, 4, 5], weights=[0.05, 0.1, 0.2, 0.35, 0.3], k=1)[0]
        text = random.choice(review_texts)
        review_date = _random_date(2022, 2025)
        verified = 1 if random.random() > 0.3 else 0
        helpful = random.randint(0, 50)
        reviews.append((product_id, customer_id, rating, text, review_date, verified, helpful))

    conn.executemany(
        "INSERT INTO reviews (product_id, customer_id, rating, review_text, review_date, is_verified_purchase, helpful_votes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        reviews,
    )


def create_sample_database() -> str:
    """Create the sample SQLite database. Returns the database path."""
    random.seed(42)  # Reproducible data

    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing DB to start fresh
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        conn.executescript(SCHEMA_SQL)
        _insert_categories(conn)
        _insert_suppliers(conn)
        _insert_products(conn)
        _insert_customers(conn)
        _insert_employees(conn)
        _insert_orders(conn)
        _insert_order_items(conn)
        _insert_payments(conn)
        _insert_shipping(conn)
        _insert_reviews(conn)
        conn.commit()
    finally:
        conn.close()

    return str(db_path)

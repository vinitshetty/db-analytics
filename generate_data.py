#!/usr/bin/env python3
"""
Generate synthetic data warehouse for testing and reporting.
"""

import sqlite3
import random
from datetime import datetime, timedelta
import math

DB_PATH = "warehouse.db"

# Reference data
CUSTOMERS_DATA = [
    ("Alice Johnson", "alice@example.com", "USA", "North America", "Premium"),
    ("Bob Smith", "bob@example.com", "Canada", "North America", "Standard"),
    ("Charlie Brown", "charlie@example.com", "USA", "North America", "Premium"),
    ("Diana Prince", "diana@example.com", "UK", "Europe", "Standard"),
    ("Eve Martinez", "eve@example.com", "Spain", "Europe", "Growth"),
    ("Frank Wilson", "frank@example.com", "Germany", "Europe", "Premium"),
    ("Grace Lee", "grace@example.com", "Australia", "Asia Pacific", "Standard"),
    ("Henry Wang", "henry@example.com", "China", "Asia Pacific", "Premium"),
    ("Isabel Garcia", "isabel@example.com", "Mexico", "Latin America", "Growth"),
    ("Jack Davis", "jack@example.com", "Brazil", "Latin America", "Standard"),
]

PRODUCTS_DATA = [
    ("Laptop Pro", "Electronics", "Computers", "TechBrand", 1200.00, 600.00, 1),
    ("Wireless Mouse", "Electronics", "Peripherals", "TechBrand", 29.99, 10.00, 1),
    ("USB-C Cable", "Electronics", "Cables", "TechBrand", 14.99, 3.00, 1),
    ("Monitor 4K", "Electronics", "Displays", "VisuBrand", 399.99, 150.00, 2),
    ("Mechanical Keyboard", "Electronics", "Peripherals", "KeyMaster", 149.99, 50.00, 3),
    ("Office Chair", "Furniture", "Seating", "ComfortCorp", 299.99, 120.00, 4),
    ("Standing Desk", "Furniture", "Desks", "ComfortCorp", 499.99, 200.00, 4),
    ("Desk Lamp LED", "Furniture", "Lighting", "BrightLight", 79.99, 20.00, 5),
    ("Notebook Set", "Stationery", "Paper", "PaperCo", 9.99, 2.00, 6),
    ("Pen Pack", "Stationery", "Writing", "PenCorp", 4.99, 0.80, 6),
]

REGIONS_DATA = [
    ("North America", "USA", "America", "John Smith"),
    ("Europe", "Germany", "Europe", "Maria Schmidt"),
    ("Asia Pacific", "Australia", "Asia", "David Chen"),
    ("Latin America", "Brazil", "America", "Carlos Rodriguez"),
    ("Africa", "South Africa", "Africa", "Nelson Mkhize"),
]

STATUSES = ["Completed", "Pending", "Shipped", "Cancelled", "Returned"]

def create_connection():
    """Create and return database connection."""
    conn = sqlite3.connect(DB_PATH)
    return conn

def generate_date_dimension(conn, start_date, end_date):
    """Generate date dimension table."""
    cursor = conn.cursor()
    current_date = start_date
    date_id = 1

    while current_date <= end_date:
        cursor.execute(
            """INSERT INTO dim_date
            (date_id, full_date, year, month, quarter, day_of_month,
             day_of_week, week_of_year, month_name, is_weekend)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                date_id,
                current_date.date(),
                current_date.year,
                current_date.month,
                (current_date.month - 1) // 3 + 1,
                current_date.day,
                current_date.weekday(),
                current_date.isocalendar()[1],
                current_date.strftime("%B"),
                current_date.weekday() >= 5
            )
        )
        date_id += 1
        current_date += timedelta(days=1)

    conn.commit()
    print(f"✓ Generated {date_id-1} dates")

def generate_dimensions(conn):
    """Generate dimension tables."""
    cursor = conn.cursor()

    # Customers
    for i, (name, email, country, region, segment) in enumerate(CUSTOMERS_DATA, 1):
        created = datetime(2022, random.randint(1, 12), random.randint(1, 28))
        cursor.execute(
            """INSERT INTO dim_customer
            (customer_id, customer_name, email, country, region, segment, created_date, lifecycle_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (i, name, email, country, region, segment, created.date(),
             random.choice(["Active", "Inactive", "At Risk"]))
        )
    conn.commit()
    print(f"✓ Generated {len(CUSTOMERS_DATA)} customers")

    # Products
    for i, (name, cat, subcat, brand, price, cost, supplier) in enumerate(PRODUCTS_DATA, 1):
        cursor.execute(
            """INSERT INTO dim_product
            (product_id, product_name, category, subcategory, brand, unit_price, cost, supplier_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (i, name, cat, subcat, brand, price, cost, supplier)
        )
    conn.commit()
    print(f"✓ Generated {len(PRODUCTS_DATA)} products")

    # Regions
    for i, (name, country, continent, manager) in enumerate(REGIONS_DATA, 1):
        cursor.execute(
            """INSERT INTO dim_region
            (region_id, region_name, country, continent, sales_manager)
            VALUES (?, ?, ?, ?, ?)""",
            (i, name, country, continent, manager)
        )
    conn.commit()
    print(f"✓ Generated {len(REGIONS_DATA)} regions")

def generate_orders(conn, num_orders=5000):
    """Generate fact orders."""
    cursor = conn.cursor()

    # Get date range
    cursor.execute("SELECT MIN(date_id), MAX(date_id) FROM dim_date")
    min_date_id, max_date_id = cursor.fetchone()

    for order_id in range(1, num_orders + 1):
        customer_id = random.randint(1, len(CUSTOMERS_DATA))
        product_id = random.randint(1, len(PRODUCTS_DATA))
        region_id = random.randint(1, len(REGIONS_DATA))
        order_date_id = random.randint(min_date_id, max_date_id)
        delivery_date_id = random.randint(order_date_id, min(order_date_id + 30, max_date_id))

        quantity = random.randint(1, 10)
        unit_price = PRODUCTS_DATA[product_id - 1][4]
        cost = PRODUCTS_DATA[product_id - 1][5]
        discount_percent = random.choice([0, 5, 10, 15, 20]) if random.random() > 0.7 else 0

        base_revenue = quantity * unit_price
        revenue = base_revenue * (1 - discount_percent / 100)
        tax_amount = revenue * 0.1
        total_cost = quantity * cost
        profit = revenue - total_cost

        status = random.choice(STATUSES)

        cursor.execute(
            """INSERT INTO fact_order
            (order_id, order_date_id, delivery_date_id, customer_id, product_id, region_id,
             quantity, unit_price, discount_percent, tax_amount, revenue, cost, profit, order_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, order_date_id, delivery_date_id, customer_id, product_id, region_id,
             quantity, unit_price, discount_percent, tax_amount, revenue, cost, profit, status)
        )

        if order_id % 1000 == 0:
            conn.commit()
            print(f"  Generated {order_id}/{num_orders} orders...")

    conn.commit()
    print(f"✓ Generated {num_orders} orders")

def main():
    """Main execution."""
    print("🏗️  Building Data Warehouse...\n")

    # Create connection and load schema
    conn = create_connection()
    with open("schema.sql") as f:
        conn.executescript(f.read())
    print("✓ Schema created\n")

    # Generate data
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2024, 12, 31)

    print("Generating dimensions...")
    generate_date_dimension(conn, start_date, end_date)
    generate_dimensions(conn)

    print("\nGenerating facts...")
    generate_orders(conn, num_orders=5000)

    conn.close()
    print("\n✅ Data warehouse ready! Database: warehouse.db")

if __name__ == "__main__":
    main()

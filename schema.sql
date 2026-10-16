-- Data Warehouse Schema (Star Schema)

-- Dimension: Date
CREATE TABLE dim_date (
    date_id INTEGER PRIMARY KEY,
    full_date DATE UNIQUE,
    year INTEGER,
    month INTEGER,
    quarter INTEGER,
    day_of_month INTEGER,
    day_of_week INTEGER,
    week_of_year INTEGER,
    month_name TEXT,
    is_weekend BOOLEAN
);

-- Dimension: Customer
CREATE TABLE dim_customer (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT,
    country TEXT NOT NULL,
    region TEXT NOT NULL,
    segment TEXT,
    created_date DATE,
    lifecycle_status TEXT
);

-- Dimension: Product
CREATE TABLE dim_product (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    brand TEXT,
    unit_price DECIMAL(10, 2),
    cost DECIMAL(10, 2),
    supplier_id INTEGER
);

-- Dimension: Region
CREATE TABLE dim_region (
    region_id INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL UNIQUE,
    country TEXT,
    continent TEXT,
    sales_manager TEXT
);

-- Fact Table: Orders
CREATE TABLE fact_order (
    order_id INTEGER PRIMARY KEY,
    order_date_id INTEGER NOT NULL,
    delivery_date_id INTEGER,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    region_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2),
    discount_percent DECIMAL(5, 2),
    tax_amount DECIMAL(10, 2),
    revenue DECIMAL(12, 2),
    cost DECIMAL(10, 2),
    profit DECIMAL(12, 2),
    order_status TEXT,
    FOREIGN KEY (order_date_id) REFERENCES dim_date(date_id),
    FOREIGN KEY (delivery_date_id) REFERENCES dim_date(date_id),
    FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id),
    FOREIGN KEY (region_id) REFERENCES dim_region(region_id)
);

-- Indexes for performance
CREATE INDEX idx_fact_order_date ON fact_order(order_date_id);
CREATE INDEX idx_fact_order_customer ON fact_order(customer_id);
CREATE INDEX idx_fact_order_product ON fact_order(product_id);
CREATE INDEX idx_fact_order_region ON fact_order(region_id);
CREATE INDEX idx_dim_date_full_date ON dim_date(full_date);

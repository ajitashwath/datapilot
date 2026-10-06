from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent
rng = np.random.default_rng(42)

REGIONS = {"North America": 0.38, "Europe": 0.27, "Asia Pacific": 0.2, "Latin America": 0.1, "Middle East & Africa": 0.05}
COUNTRIES = {
    "North America": ["United States", "Canada"],
    "Europe": ["Germany", "France", "United Kingdom", "Spain"],
    "Asia Pacific": ["Japan", "Australia", "India", "Singapore"],
    "Latin America": ["Brazil", "Mexico", "Chile"],
    "Middle East & Africa": ["UAE", "South Africa", "Kenya"],
}
FIRST = ["Ava", "Liam", "Noah", "Emma", "Mia", "Lucas", "Sofia", "Ethan", "Yuki", "Arjun", "Chloe", "Omar", "Elena", "Mateo", "Priya", "Hans"]
LAST = ["Smith", "Garcia", "Chen", "Patel", "Müller", "Rossi", "Tanaka", "Silva", "Khan", "Dubois", "Nguyen", "Brown", "Ivanov", "Lopez"]

CATEGORIES = {
    "Laptops": [("ProBook 14", 780, 1199), ("ProBook 16", 940, 1499), ("AirLite 13", 610, 999), ("StudioBook", 1250, 1999), ("Student Laptop S1", 280, 449)],
    "Phones": [("Nova X", 420, 799), ("Nova Mini", 300, 549), ("Nova Pro", 610, 1099), ("Basic Phone B2", 80, 149)],
    "Accessories": [("USB-C Hub", 18, 45), ("Wireless Mouse", 12, 29), ("Mechanical Keyboard", 38, 99), ("Laptop Sleeve", 9, 25), ("Webcam HD", 22, 59), ("Charging Dock", 31, 79)],
    "Monitors": [("View 24", 110, 199), ("View 27 4K", 260, 449), ("UltraWide 34", 420, 749)],
    "Audio": [("Buds Air", 38, 99), ("Buds Pro", 70, 179), ("Studio Headphones", 120, 299), ("Smart Speaker", 28, 79)],
    "Software": [("Office Suite", 40, 129), ("Security Pro", 22, 59), ("Cloud Backup 1TB", 30, 99)],
}
POPULARITY = {"Laptops": 2.0, "Phones": 2.4, "Accessories": 3.0, "Monitors": 1.2, "Audio": 1.4, "Software": 0.35}
UNDERPERFORMERS = {"Student Laptop S1", "Basic Phone B2", "Smart Speaker", "Cloud Backup 1TB"}


def make_customers(n: int = 600) -> pd.DataFrame:
    regions = rng.choice(list(REGIONS), size=n, p=list(REGIONS.values()))
    countries = [rng.choice(COUNTRIES[r]) for r in regions]
    names = [f"{rng.choice(FIRST)} {rng.choice(LAST)}" for _ in range(n)]
    signup = pd.to_datetime("2022-01-01") + pd.to_timedelta(rng.integers(0, 900, size=n), unit="D")
    segments = rng.choice(["Consumer", "Small Business", "Enterprise"], size=n, p=[0.6, 0.3, 0.1])
    return pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "customer_name": names,
        "segment": segments,
        "country": countries,
        "region": regions,
        "signup_date": signup.strftime("%Y-%m-%d"),
    })


def make_products() -> pd.DataFrame:
    rows = []
    for category, items in CATEGORIES.items():
        for name, cost, price in items:
            rows.append({"product_id": len(rows) + 1, "product_name": name, "category": category, "unit_cost": cost, "list_price": price})
    return pd.DataFrame(rows)


def make_orders(customers: pd.DataFrame, products: pd.DataFrame, n: int = 7000) -> pd.DataFrame:
    days = pd.date_range("2023-01-01", "2024-12-31")
    month_weight = np.array([0.85, 0.8, 0.9, 0.95, 1.0, 0.95, 0.9, 0.95, 1.05, 1.1, 1.35, 1.6])
    growth = 1 + (days - days[0]).days.to_numpy() / 730 * 0.5
    weights = month_weight[days.month - 1] * growth
    order_days = rng.choice(days, size=n, p=weights / weights.sum())

    customer_weights = np.where(customers["region"] == "North America", 1.5, 1.0) * rng.gamma(2.0, 1.0, size=len(customers))
    customer_idx = rng.choice(len(customers), size=n, p=customer_weights / customer_weights.sum())
    chosen_customers = customers.iloc[customer_idx].reset_index(drop=True)

    product_weights = np.array([
        POPULARITY[row.category] * (0.12 if row.product_name in UNDERPERFORMERS else 1.0) for row in products.itertuples()
    ])
    product_idx = rng.choice(len(products), size=n, p=product_weights / product_weights.sum())
    chosen_products = products.iloc[product_idx].reset_index(drop=True)

    quantity = np.where(chosen_products["category"].isin(["Accessories", "Software"]), rng.integers(1, 6, size=n), rng.integers(1, 3, size=n))
    quantity = np.where(chosen_customers["segment"] == "Enterprise", quantity * rng.integers(2, 6, size=n), quantity)
    discount = np.round(rng.choice([0, 0, 0, 0.05, 0.1, 0.15], size=n), 2)
    unit_price = np.round(chosen_products["list_price"].to_numpy() * rng.normal(1.0, 0.03, size=n), 2)
    revenue = np.round(quantity * unit_price * (1 - discount), 2)

    orders = pd.DataFrame({
        "order_id": np.arange(100001, 100001 + n),
        "order_date": pd.to_datetime(order_days).strftime("%Y-%m-%d"),
        "customer_id": chosen_customers["customer_id"],
        "product_id": chosen_products["product_id"],
        "region": chosen_customers["region"],
        "channel": rng.choice(["Online", "Retail", "Partner"], size=n, p=[0.55, 0.3, 0.15]),
        "quantity": quantity,
        "unit_price": unit_price,
        "discount": discount,
        "revenue": revenue,
        "status": rng.choice(["Completed", "Returned", "Cancelled"], size=n, p=[0.93, 0.05, 0.02]),
    })
    return orders.sort_values(["order_date", "order_id"]).reset_index(drop=True)


def inject_issues(orders: pd.DataFrame) -> pd.DataFrame:
    orders = orders.copy()
    big = rng.choice(len(orders), size=6, replace=False)
    orders.loc[big, "quantity"] = rng.integers(180, 320, size=6)
    orders.loc[big, "revenue"] = np.round(orders.loc[big, "quantity"] * orders.loc[big, "unit_price"], 2)

    orders.loc[orders.index[1500], "revenue"] = -4999.0
    orders.loc[orders.index[3200], "revenue"] = 187500.0

    picks = orders.sample(70, random_state=1).copy()
    picks["order_id"] = np.arange(200000, 200070)
    picks["order_date"] = "2024-03-15"
    orders = pd.concat([orders, picks]).sort_values(["order_date", "order_id"]).reset_index(drop=True)

    drop_week = (orders["order_date"] >= "2023-08-14") & (orders["order_date"] <= "2023-08-20")
    orders = orders[~(drop_week & (rng.random(len(orders)) < 0.75))].reset_index(drop=True)

    missing = rng.choice(len(orders), size=90, replace=False)
    orders["discount"] = orders["discount"].astype(float)
    orders.loc[missing, "discount"] = np.nan
    orders.loc[rng.choice(len(orders), size=35, replace=False), "channel"] = np.nan

    duplicates = orders.sample(12, random_state=3)
    return pd.concat([orders, duplicates]).sort_values(["order_date", "order_id"]).reset_index(drop=True)


if __name__ == "__main__":
    customers = make_customers()
    products = make_products()
    orders = inject_issues(make_orders(customers, products))
    customers.to_csv(OUT / "customers.csv", index=False)
    products.to_csv(OUT / "products.csv", index=False)
    orders.to_csv(OUT / "orders.csv", index=False)
    print(f"customers={len(customers)} products={len(products)} orders={len(orders)}")

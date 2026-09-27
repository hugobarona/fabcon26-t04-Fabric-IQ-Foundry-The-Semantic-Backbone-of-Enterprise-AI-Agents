"""
Lakeshore Retail demo data generator — FabCon 26.

Produces a realistic dataset for the Fabric IQ ontology demo, keeping the exact
column names and types of the official Microsoft sample
(github.com/microsoft/fabric-samples/tree/main/docs-samples/iq/ontology) and
adding a FactInventory table the official sample lacks.

Outputs to ./lakeshore_data/ :
    DimStore.csv          3 European stores          (unchanged from sample)
    DimProducts.csv      15 products                 (sample's 3 + 12 more)
    Freezer.csv           5 freezers                 (unchanged from sample)
    FactSales.csv        ~30k rows over 90 days      (sample has 6)
    FactInventory.csv    ~current stock per freezer  (NEW - not in sample)
    FreezerTelemetry.csv ~43k rows, 30 days @ 5 min  (sample has 5)

Design decisions that matter downstream:
  * All money and temperature values are written with a decimal point so they
    infer as DOUBLE, never DECIMAL. Fabric Graph does not support Decimal and
    silently returns nulls for those properties.
  * No spaces or special characters in column names, which would silently
    enable delta column mapping and break the ontology graph.
  * Paris is the highest-revenue store, so staging the live breach on a Paris
    freezer makes the stakes self-evident without explanation.
  * Three historical excursions are embedded in telemetry so "has this happened
    before?" has an answer.

Usage:
    python generate_lakeshore_data.py

Standard library only - no pip install required.
"""

import csv
import math
import os
import random
from datetime import date, datetime, timedelta, timezone

SEED = 20260903
OUT_DIR = "lakeshore_data"

SALES_DAYS = 90          # days of sales history
TELEMETRY_DAYS = 30      # days of freezer telemetry
TELEMETRY_INTERVAL_MIN = 5
SALES_PROBABILITY = 0.75  # chance a given store sells a given product on a day

# Anchor the data so it ends "yesterday" relative to the generation date.
END_DATE = date.today() - timedelta(days=1)

random.seed(SEED)


# --------------------------------------------------------------------------
# Dimensions — stores and freezers match the official sample exactly
# --------------------------------------------------------------------------

STORES = [
    # StoreId, StoreName, City, Region, Latitude, Longitude, demand weight
    ("S-PAR-01", "Lakeshore Retail Paris", "Paris", "France", 48.8566, 2.3522, 1.35),
    ("S-BER-01", "Lakeshore Retail Berlin", "Berlin", "Germany", 52.5200, 13.4050, 1.00),
    ("S-AMS-01", "Lakeshore Retail Amsterdam", "Amsterdam", "Netherlands", 52.3676, 4.9041, 0.80),
]

FREEZERS = [
    # FreezerId, Model, minSafeTempC, StoreId
    ("F-PAR-01", "ZF-500", -18.0, "S-PAR-01"),
    ("F-BER-02", "ZF-600", -18.0, "S-BER-01"),
    ("F-AMS-03", "ZF-550", -18.0, "S-AMS-01"),
    ("F-PAR-02", "ZF-520", -18.0, "S-PAR-01"),
    ("F-BER-03", "ZF-620", -18.0, "S-BER-01"),
]

# The first three ProductIds are the official sample's. Popularity drives the
# revenue ranking, so there is one clear winner for "top product by revenue".
PRODUCTS = [
    # ProductId, ProductName, Category, Subcategory, unit price, popularity
    ("P-ICE-001", "Classic Vanilla Pint",      "Ice Cream", "Pint",      5.00, 2.40),
    ("P-ICE-002", "Dark Chocolate Pint",       "Ice Cream", "Pint",      5.00, 1.30),
    ("P-ICE-003", "Strawberry Sorbet Pint",    "Sorbet",    "Pint",      5.50, 1.00),
    ("P-ICE-004", "Salted Caramel Pint",       "Ice Cream", "Pint",      5.50, 1.45),
    ("P-ICE-005", "Pistachio Gelato Pint",     "Gelato",    "Pint",      6.50, 0.85),
    ("P-ICE-006", "Mango Sorbet Pint",         "Sorbet",    "Pint",      5.50, 0.75),
    ("P-ICE-007", "Cookies and Cream Pint",    "Ice Cream", "Pint",      5.50, 1.20),
    ("P-ICE-008", "Belgian Chocolate Tub",     "Ice Cream", "Tub",      12.00, 0.48),
    ("P-ICE-009", "Vanilla Bean Tub",          "Ice Cream", "Tub",      11.00, 0.45),
    ("P-ICE-010", "Raspberry Ripple Pint",     "Ice Cream", "Pint",      5.50, 0.60),
    ("P-ICE-011", "Hazelnut Gelato Pint",      "Gelato",    "Pint",      6.50, 0.55),
    ("P-ICE-012", "Lemon Sorbet Pint",         "Sorbet",    "Pint",      5.00, 0.50),
    ("P-ICE-013", "Mint Chocolate Chip Pint",  "Ice Cream", "Pint",      5.50, 0.90),
    ("P-ICE-014", "Coffee Gelato Pint",        "Gelato",    "Pint",      6.50, 0.60),
    ("P-ICE-015", "Mixed Berry Sorbet Tub",    "Sorbet",    "Tub",      11.50, 0.40),
]

BRAND = "Lakeshore Retail"

# Historical excursions embedded in telemetry: (freezerId, days_ago, duration_min, peak_temp_c)
HISTORICAL_EXCURSIONS = [
    ("F-BER-02", 22, 95, -13.4),
    ("F-AMS-03", 14, 60, -15.1),
    ("F-BER-02", 5, 130, -11.8),
]

# Normal freezer humidity sits comfortably above the 46% threshold used in the
# canonical demo question, so that question returns a meaningful SUBSET rather
# than every freezer. Two units have a defrost fault that periodically drives
# humidity low - a genuine maintenance signal, and the answer to
# "which freezers ever had humidity lower than 46 percent?"
NOMINAL_HUMIDITY_PCT = 49.5

# freezerId -> (episodes, duration_min, low_humidity_pct)
DEFROST_FAULT_FREEZERS = {
    "F-BER-03": (6, 75, 43.5),
    "F-AMS-03": (3, 50, 44.8),
}


def ensure_out_dir():
    os.makedirs(OUT_DIR, exist_ok=True)


def write_csv(filename, header, rows):
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  {filename:<24} {len(rows):>7,} rows")
    return path


def seasonal_factor(day):
    """Ice cream demand: summer peak plus a weekend lift."""
    # Day of year mapped to a sine wave peaking in mid-July (northern summer).
    day_of_year = day.timetuple().tm_yday
    seasonal = 1.0 + 0.45 * math.sin(2 * math.pi * (day_of_year - 105) / 365.0)
    weekend = 1.30 if day.weekday() >= 5 else 1.0
    return seasonal * weekend


# --------------------------------------------------------------------------
# Dimension files
# --------------------------------------------------------------------------

def write_dim_store():
    rows = [
        [store_id, name, city, region, f"{lat:.4f}", f"{lon:.4f}"]
        for store_id, name, city, region, lat, lon, _ in STORES
    ]
    return write_csv(
        "DimStore.csv",
        ["StoreId", "StoreName", "City", "Region", "Latitude", "Longitude"],
        rows,
    )


def write_dim_products():
    rows = [
        [product_id, name, category, subcategory, BRAND]
        for product_id, name, category, subcategory, _, _ in PRODUCTS
    ]
    return write_csv(
        "DimProducts.csv",
        ["ProductId", "ProductName", "Category", "Subcategory", "Brand"],
        rows,
    )


def write_freezer():
    rows = [
        [freezer_id, model, f"{min_temp:.1f}", store_id]
        for freezer_id, model, min_temp, store_id in FREEZERS
    ]
    return write_csv(
        "Freezer.csv",
        ["FreezerId", "Model", "minSafeTempC", "StoreId"],
        rows,
    )


# --------------------------------------------------------------------------
# FactSales
# --------------------------------------------------------------------------

def write_fact_sales():
    rows = []
    sale_id = 1_000_000
    start = END_DATE - timedelta(days=SALES_DAYS - 1)

    for offset in range(SALES_DAYS):
        day = start + timedelta(days=offset)
        season = seasonal_factor(day)

        for store_id, _, _, _, _, _, store_weight in STORES:
            for product_id, _, _, _, price, popularity in PRODUCTS:
                if random.random() > SALES_PROBABILITY:
                    continue

                expected = 12.0 * season * store_weight * popularity
                units = max(1, int(random.gauss(expected, expected * 0.28)))
                revenue = round(units * price, 2)

                sale_id += 1
                rows.append([
                    sale_id,
                    day.isoformat(),
                    store_id,
                    product_id,
                    units,
                    f"{revenue:.2f}",       # decimal point -> DOUBLE
                ])

    return write_csv(
        "FactSales.csv",
        ["SaleId", "SaleDate", "StoreId", "ProductId", "Units", "RevenueUSD"],
        rows,
    )


# --------------------------------------------------------------------------
# FactInventory  (not in the official sample)
# --------------------------------------------------------------------------

def write_fact_inventory():
    """Current stock on hand, per freezer and product.

    This is the table that lets an agent answer 'what is actually inside the
    failing freezer, and what is it worth?' - the question the cold chain story
    needs and the official sample cannot answer.
    """
    rows = []
    inventory_id = 500_000
    counted_on = END_DATE.isoformat()

    for freezer_id, _, _, store_id in FREEZERS:
        store_weight = next(w for s, _, _, _, _, _, w in STORES if s == store_id)

        # Each freezer holds a subset of the catalogue.
        stocked = random.sample(PRODUCTS, k=random.randint(7, 11))

        for product_id, _, _, _, price, popularity in stocked:
            units = max(4, int(random.gauss(45 * store_weight * popularity, 12)))
            unit_cost = round(price * 0.42, 2)          # wholesale cost
            value = round(units * unit_cost, 2)

            inventory_id += 1
            rows.append([
                inventory_id,
                store_id,
                freezer_id,
                product_id,
                units,
                f"{unit_cost:.2f}",     # DOUBLE
                f"{value:.2f}",         # DOUBLE
                counted_on,
            ])

    return write_csv(
        "FactInventory.csv",
        [
            "InventoryId", "StoreId", "FreezerId", "ProductId",
            "UnitsOnHand", "UnitCostUSD", "ValueUSD", "LastCountedDate",
        ],
        rows,
    )


# --------------------------------------------------------------------------
# FreezerTelemetry
# --------------------------------------------------------------------------

def excursion_offset(freezer_id, moment, start_of_window):
    """Return degrees above nominal if this reading falls inside an excursion."""
    for exc_freezer, days_ago, duration_min, peak_temp in HISTORICAL_EXCURSIONS:
        if exc_freezer != freezer_id:
            continue

        exc_start = start_of_window + timedelta(days=TELEMETRY_DAYS - days_ago)
        exc_start = exc_start.replace(hour=14, minute=0, second=0, microsecond=0)
        exc_end = exc_start + timedelta(minutes=duration_min)

        if exc_start <= moment <= exc_end:
            # Ramp up to the peak at the midpoint, then back down.
            progress = (moment - exc_start).total_seconds() / (duration_min * 60)
            shape = math.sin(math.pi * progress)
            return (peak_temp - (-19.2)) * shape
    return 0.0


def build_defrost_windows(freezer_id, start):
    """Time windows where a faulty freezer's humidity drops below 46%."""
    if freezer_id not in DEFROST_FAULT_FREEZERS:
        return []

    episodes, duration_min, low_pct = DEFROST_FAULT_FREEZERS[freezer_id]
    windows = []
    for index in range(episodes):
        # Spread episodes evenly through the window, at varied times of day.
        day_offset = int((index + 0.5) * TELEMETRY_DAYS / episodes)
        begin = (start + timedelta(days=day_offset)).replace(
            hour=(3 + index * 4) % 24, minute=0, second=0, microsecond=0
        )
        windows.append((begin, begin + timedelta(minutes=duration_min), low_pct))
    return windows


def write_freezer_telemetry():
    rows = []
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % TELEMETRY_INTERVAL_MIN)
    start = end - timedelta(days=TELEMETRY_DAYS)

    steps = int((TELEMETRY_DAYS * 24 * 60) / TELEMETRY_INTERVAL_MIN)

    for freezer_id, _, _, store_id in FREEZERS:
        temperature = -19.2
        defrost_windows = build_defrost_windows(freezer_id, start)

        for step in range(steps):
            moment = start + timedelta(minutes=step * TELEMETRY_INTERVAL_MIN)

            # Gentle drift so charts look alive rather than flat.
            temperature += random.uniform(-0.18, 0.18)
            temperature = max(-21.0, min(-18.6, temperature))

            offset = excursion_offset(freezer_id, moment, start)
            reading = temperature + offset

            in_defrost = next(
                (low for begin, finish, low in defrost_windows if begin <= moment <= finish),
                None,
            )

            if offset > 0.5:
                # Temperature excursion: door open, humidity climbs.
                humidity = NOMINAL_HUMIDITY_PCT + random.uniform(6.0, 13.0)
                door_open = 1
            elif in_defrost is not None:
                # Defrost fault: humidity falls below the 46% threshold.
                humidity = in_defrost + random.uniform(-0.8, 0.8)
                door_open = 0
            else:
                humidity = NOMINAL_HUMIDITY_PCT + random.uniform(-1.6, 1.6)
                door_open = 1 if random.random() < 0.04 else 0

            rows.append([
                moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                store_id,
                freezer_id,
                f"{reading:.2f}",       # DOUBLE
                f"{humidity:.1f}",      # DOUBLE
                door_open,
            ])

    rows.sort(key=lambda row: row[0])

    return write_csv(
        "FreezerTelemetry.csv",
        ["timestamp", "storeId", "freezerId", "temperatureC", "humidityPct", "doorOpen"],
        rows,
    )


def main():
    ensure_out_dir()
    print(f"Generating Lakeshore Retail demo data into ./{OUT_DIR}/\n")

    write_dim_store()
    write_dim_products()
    write_freezer()
    write_fact_sales()
    write_fact_inventory()
    write_freezer_telemetry()

    print("\nDone.")
    print("\nUpload to the lakehouse : DimStore, DimProducts, Freezer, FactSales, FactInventory")
    print("Upload to the eventhouse: FreezerTelemetry")
    print("\nAfter loading, verify RevenueUSD, ValueUSD, UnitCostUSD, minSafeTempC")
    print("and temperatureC are DOUBLE, not DECIMAL.")


if __name__ == "__main__":
    main()

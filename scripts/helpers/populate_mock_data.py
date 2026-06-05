"""Populate operations.Obsolescence_Results with 490 additional mock rows (total: 500)."""

import pyodbc
import random
from datetime import datetime, timedelta

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "Server=jortizflores,1433;"
    "Database=ExtronDemo;"
    "Trusted_Connection=yes;"
)
cursor = conn.cursor()

# Valid status values from the app
statuses = [
    "NOT eligible for scrap - Bin Location-[SHOW]",
    "Component Request - Please review Logid",
    "No stock",
    "Product USAGE",
    "In WhereUsed with parent",
    "NOT eligible for scrap - Bin Stock",
    "NOT eligible for scrap - NOT A PHYSICAL PART",
    "May be eligible to be scrapped",
    "Need Further Review-NO BOM",
    "Sold in Past Two Years",
    "Open WorkOrder",
    "Open Sales Order",
    "NOT eligible for scrap - Custom Button",
    "REPAIR USAGE- Need Further review",
    "NOT eligible for scrap - International Powercord",
]

# Weighted distribution (more realistic)
weights = [8, 5, 12, 10, 15, 8, 6, 10, 7, 5, 4, 3, 3, 2, 2]

# Part number prefixes
prefixes = ["19", "26", "33", "42", "55", "60", "70", "28", "15", "31", "44", "68", "72", "81", "93"]

# Suffixes observed
suffixes = ["01LF", "02LF", "01", "02", "03", "01A", "02A", "11", "21"]

# Parent part patterns for "In WhereUsed with parent"
parent_suffixes = ["01", "02", "03", "102", "13U", "002291", "04", "05", "201", "301"]


def generate_details(status):
    if status == "In WhereUsed with parent":
        return f"60-{random.randint(1000, 9999)}-{random.choice(parent_suffixes)}"
    elif status == "NOT eligible for scrap - Bin Location-[SHOW]":
        return f"BIN-{random.choice('ABCDE')}{random.randint(1, 50):02d}"
    elif status == "Component Request - Please review Logid":
        return f"LOG-{random.randint(10000, 99999)}"
    elif status == "Open WorkOrder":
        return f"WO-{random.randint(100000, 999999)}"
    elif status == "Open Sales Order":
        return f"SO-{random.randint(200000, 799999)}"
    elif status == "Sold in Past Two Years":
        return f"Last sold {random.randint(1, 24)} months ago"
    elif status == "REPAIR USAGE- Need Further review":
        return f"Repair count: {random.randint(1, 15)}"
    elif status == "Product USAGE":
        return f"Active in {random.randint(1, 8)} product lines"
    else:
        return None


# Get existing part numbers to avoid duplicates
existing_parts = set()
cursor.execute("SELECT PartNumber FROM [operations].[Obsolescence_Results]")
for row in cursor.fetchall():
    existing_parts.add(row[0])

print(f"Existing rows: {len(existing_parts)}")

random.seed(42)
base_date = datetime(2026, 4, 15, 18, 6, 58)
new_rows = []

while len(new_rows) < 490:
    prefix = random.choice(prefixes)
    mid = random.randint(1000, 9999)
    suffix = random.choice(suffixes)
    part = f"{prefix}-{mid}-{suffix}"
    if part in existing_parts:
        continue
    existing_parts.add(part)

    status = random.choices(statuses, weights=weights, k=1)[0]
    details = generate_details(status)
    # Vary the processed date within a 30-day window
    date_offset = timedelta(
        days=random.randint(0, 30),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    processed_date = base_date - date_offset

    new_rows.append((part, status, details, processed_date))

# Insert in batches
cursor.executemany(
    "INSERT INTO [operations].[Obsolescence_Results] "
    "(PartNumber, Status, Details, ModelProcessedDate) VALUES (?, ?, ?, ?)",
    new_rows,
)
conn.commit()

# Verify
cursor.execute("SELECT COUNT(*) FROM [operations].[Obsolescence_Results]")
print(f"New total row count: {cursor.fetchone()[0]}")

# Show distribution
print("\nStatus distribution:")
cursor.execute(
    "SELECT Status, COUNT(*) as cnt FROM [operations].[Obsolescence_Results] "
    "GROUP BY Status ORDER BY cnt DESC"
)
for row in cursor.fetchall():
    print(f"  {row[1]:>3}  {row[0]}")

conn.close()
print("\nDone - 490 mock rows inserted successfully.")

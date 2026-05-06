"""Query diverse parts from SQL for the robust benchmark."""
import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "Server=jortizflores,1433;"
    "Database=ExtronDemo;"
    "Trusted_Connection=yes;"
)
cursor = conn.cursor()

print("=" * 80)
print("GROUND TRUTH DATA FOR ROBUST BENCHMARK")
print("=" * 80)

# Total count
cursor.execute("SELECT COUNT(*) FROM [operations].[Obsolescence_Results]")
print(f"\nTotal rows: {cursor.fetchone()[0]}")

# One part from EACH status, with Details info
cursor.execute("""
    SELECT PartNumber, Status, Details
    FROM (
        SELECT PartNumber, Status, Details,
               ROW_NUMBER() OVER (PARTITION BY Status ORDER BY PartNumber) as rn
        FROM [operations].[Obsolescence_Results]
    ) sub
    WHERE rn = 1
    ORDER BY Status
""")
print("\nOne part per status:")
for row in cursor.fetchall():
    print(f"  {row[0]:20s} | {row[1]:50s} | {row[2]}")

# Parts WITH non-null Details
cursor.execute("""
    SELECT TOP 5 PartNumber, Status, Details
    FROM [operations].[Obsolescence_Results]
    WHERE Details IS NOT NULL
    ORDER BY PartNumber
""")
print("\nParts WITH Details:")
for row in cursor.fetchall():
    print(f"  {row[0]:20s} | {row[1]:50s} | {row[2]}")

# Parts WITHOUT Details (NULL)
cursor.execute("""
    SELECT TOP 5 PartNumber, Status, Details
    FROM [operations].[Obsolescence_Results]
    WHERE Details IS NULL
    ORDER BY PartNumber
""")
print("\nParts WITHOUT Details (NULL):")
for row in cursor.fetchall():
    print(f"  {row[0]:20s} | {row[1]:50s} | {row[2]}")

# Status distribution
cursor.execute("""
    SELECT Status, COUNT(*) as cnt
    FROM [operations].[Obsolescence_Results]
    GROUP BY Status
    ORDER BY cnt DESC
""")
print("\nStatus distribution:")
for row in cursor.fetchall():
    print(f"  {row[1]:>3}  {row[0]}")

# Check some near-miss part numbers for adversarial testing
cursor.execute("SELECT TOP 1 PartNumber FROM [operations].[Obsolescence_Results] ORDER BY PartNumber")
first = cursor.fetchone()[0]
cursor.execute("SELECT TOP 1 PartNumber FROM [operations].[Obsolescence_Results] ORDER BY PartNumber DESC")
last = cursor.fetchone()[0]
print(f"\nFirst part: {first}")
print(f"Last part:  {last}")

conn.close()

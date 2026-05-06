"""Query ground truth data for benchmark."""
import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "Server=jortizflores,1433;"
    "Database=ExtronDemo;"
    "Trusted_Connection=yes;"
)
cursor = conn.cursor()

# Q1: Total row count
cursor.execute("SELECT COUNT(*) FROM [operations].[Obsolescence_Results]")
print(f"TOTAL ROWS: {cursor.fetchone()[0]}")

# Pick a part that may be eligible to be scrapped
cursor.execute("""
    SELECT TOP 1 PartNumber, Status, Details
    FROM [operations].[Obsolescence_Results]
    WHERE Status = 'May be eligible to be scrapped'
    ORDER BY NEWID()
""")
row = cursor.fetchone()
print(f"SCRAPPABLE PART: {row[0]} | {row[1]} | {row[2]}")

# Pick a part that is NOT eligible
cursor.execute("""
    SELECT TOP 1 PartNumber, Status, Details
    FROM [operations].[Obsolescence_Results]
    WHERE Status LIKE 'NOT eligible%'
    ORDER BY NEWID()
""")
row = cursor.fetchone()
print(f"NOT-ELIGIBLE PART: {row[0]} | {row[1]} | {row[2]}")

# Verify a fake part number doesn't exist
cursor.execute("SELECT COUNT(*) FROM [operations].[Obsolescence_Results] WHERE PartNumber = '99-0000-FAKE'")
print(f"FAKE PART 99-0000-FAKE exists: {cursor.fetchone()[0] > 0}")

conn.close()

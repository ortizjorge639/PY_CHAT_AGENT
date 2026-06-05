"""Quick check of CRmaster structure for a known part."""
import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=jortizflores,1433;"
    "DATABASE=ExtronDemo;"
    "Trusted_Connection=yes"
)
cur = conn.cursor()
cur.execute("SELECT * FROM operations.CRmaster_ModelResults WHERE PartNumber = ?", "19-1690-02LF")
cols = [d[0] for d in cur.description]
print("Columns:", cols)
rows = cur.fetchall()
for r in rows:
    print(dict(zip(cols, r)))
conn.close()

"""Insert 1-to-many test data into CRmaster_ModelResults.

Creates multiple model-run rows for 3 part numbers to test 1-many scenarios:
- 19-1690-02LF: 2 additional rows (3 total) — confidence changes over time
- 19-3082-01LF: 1 additional row (2 total) — replacement recommendation changed
- 28-457-17LF: 1 additional row (2 total) — same recommendation, lower confidence
"""
import pyodbc
from datetime import datetime

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=jortizflores,1433;"
    "DATABASE=ExtronDemo;"
    "Trusted_Connection=yes"
)
cur = conn.cursor()

# New rows to insert (pklogid must be unique — using 50201+ range)
new_rows = [
    # 19-1690-02LF — 2nd model run (older, lower confidence, different replacement)
    {
        "pklogid": 50201,
        "Comments": "Initial model run; alternate candidate identified but not validated.",
        "NewPNAssigned": "DM-410-20LF",
        "Replacement_intent": "Y",
        "Old_Part": "19-1690-02LF",
        "New_Part": "DM-410-20LF",
        "Cue_Phrase": "possible replacement",
        "Confidence": "0.72",
        "Rationale": "Electrical specs similar but thermal rating unconfirmed.",
        "Error": None,
        "ModelProcessedDate": datetime(2026, 3, 10, 14, 30),
        "LogDate": datetime(2026, 3, 9, 9, 0),
        "updatetime": datetime(2026, 3, 10, 14, 30),
        "PartNumber": "19-1690-02LF",
    },
    # 19-1690-02LF — 3rd model run (oldest, N intent)
    {
        "pklogid": 50202,
        "Comments": "No viable replacement found at time of analysis.",
        "NewPNAssigned": None,
        "Replacement_intent": "N",
        "Old_Part": "19-1690-02LF",
        "New_Part": None,
        "Cue_Phrase": "no replacement",
        "Confidence": "0.60",
        "Rationale": "All candidates failed form-factor check.",
        "Error": None,
        "ModelProcessedDate": datetime(2026, 2, 5, 11, 0),
        "LogDate": datetime(2026, 2, 4, 8, 0),
        "updatetime": datetime(2026, 2, 5, 11, 0),
        "PartNumber": "19-1690-02LF",
    },
    # 19-3082-01LF — 2nd model run (older, different recommendation)
    {
        "pklogid": 50203,
        "Comments": "Earlier analysis flagged potential replacement but low confidence.",
        "NewPNAssigned": "DM-287-30LF",
        "Replacement_intent": "Y",
        "Old_Part": "19-3082-01LF",
        "New_Part": "DM-287-30LF",
        "Cue_Phrase": "candidate replacement",
        "Confidence": "0.68",
        "Rationale": "Pinout compatible but voltage tolerance untested.",
        "Error": None,
        "ModelProcessedDate": datetime(2026, 3, 1, 9, 45),
        "LogDate": datetime(2026, 2, 28, 16, 0),
        "updatetime": datetime(2026, 3, 1, 9, 45),
        "PartNumber": "19-3082-01LF",
    },
    # 28-457-17LF — 2nd model run (older, same intent, lower confidence)
    {
        "pklogid": 50204,
        "Comments": "Preliminary match; awaiting supplier datasheet.",
        "NewPNAssigned": "DM-309-55LF",
        "Replacement_intent": "Y",
        "Old_Part": "28-457-17LF",
        "New_Part": "DM-309-55LF",
        "Cue_Phrase": "preliminary match",
        "Confidence": "0.71",
        "Rationale": "Form-factor match confirmed; electrical pending.",
        "Error": None,
        "ModelProcessedDate": datetime(2026, 2, 20, 10, 0),
        "LogDate": datetime(2026, 2, 19, 14, 0),
        "updatetime": datetime(2026, 2, 20, 10, 0),
        "PartNumber": "28-457-17LF",
    },
]

sql = """
INSERT INTO operations.CRmaster_ModelResults 
    (pklogid, Comments, NewPNAssigned, Replacement_intent, Old_Part, New_Part,
     Cue_Phrase, Confidence, Rationale, Error, ModelProcessedDate, LogDate, updatetime, PartNumber)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

for row in new_rows:
    cur.execute(sql, (
        row["pklogid"], row["Comments"], row["NewPNAssigned"],
        row["Replacement_intent"], row["Old_Part"], row["New_Part"],
        row["Cue_Phrase"], row["Confidence"], row["Rationale"],
        row["Error"], row["ModelProcessedDate"], row["LogDate"],
        row["updatetime"], row["PartNumber"],
    ))
    print(f"Inserted pklogid {row['pklogid']} — {row['PartNumber']}")

conn.commit()
conn.close()
print("\nDone. CRmaster now has 1-many relationships for 3 parts.")

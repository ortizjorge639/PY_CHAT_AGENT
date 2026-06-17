"""Augment operations.Obsolescence_Results with new columns and fabricated data.

Adds columns if they do not exist:
- [reza's list] (INT)
- [p/c phase] (NVARCHAR(20))
- [QOH] (INT)
- [obsolete reserve] (DECIMAL(12,2))

Then populates data for all rows:
- [reza's list] = 0 for all rows, then exactly 50 random rows set to 1
  (or all rows if table has fewer than 50)
- [p/c phase] fabricated across P1..P4 buckets
- [QOH] fabricated integer quantity in [0, 1200]
- [obsolete reserve] fabricated decimal in [0, 250000]
"""

from __future__ import annotations

import argparse
import pyodbc


def _connect(server: str, port: int, database: str, trusted: bool, user: str, password: str) -> pyodbc.Connection:
    parts = [
        "DRIVER={ODBC Driver 17 for SQL Server}",
        f"SERVER={server},{port}",
        f"DATABASE={database}",
    ]
    if trusted:
        parts.append("Trusted_Connection=yes")
    else:
        parts.extend([f"UID={user}", f"PWD={password}"])
    conn_str = ";".join(parts) + ";"
    return pyodbc.connect(conn_str)


def main() -> None:
    parser = argparse.ArgumentParser(description="Augment SQL table with new columns and fabricated data")
    parser.add_argument("--server", default="jortizflores", help="SQL Server host")
    parser.add_argument("--port", type=int, default=1433, help="SQL Server port")
    parser.add_argument("--database", default="ExtronDemo", help="Database name")
    parser.add_argument("--schema", default="operations", help="Schema name")
    parser.add_argument("--table", default="Obsolescence_Results", help="Table name")
    parser.add_argument("--trusted", action="store_true", default=True, help="Use Windows trusted auth")
    parser.add_argument("--user", default="", help="SQL username when not using trusted auth")
    parser.add_argument("--password", default="", help="SQL password when not using trusted auth")
    parser.add_argument("--reza-ones", type=int, default=50, help="How many rows should have [reza's list] = 1")
    args = parser.parse_args()

    fq_table = f"[{args.schema}].[{args.table}]"

    conn = _connect(args.server, args.port, args.database, args.trusted, args.user, args.password)
    cursor = conn.cursor()

    # 1) Add columns if missing.
    add_columns_sql = f"""
IF COL_LENGTH('{args.schema}.{args.table}', 'reza''s list') IS NULL
    ALTER TABLE {fq_table} ADD [reza's list] INT NULL;

IF COL_LENGTH('{args.schema}.{args.table}', 'p/c phase') IS NULL
    ALTER TABLE {fq_table} ADD [p/c phase] NVARCHAR(20) NULL;

IF COL_LENGTH('{args.schema}.{args.table}', 'QOH') IS NULL
    ALTER TABLE {fq_table} ADD [QOH] INT NULL;

IF COL_LENGTH('{args.schema}.{args.table}', 'obsolete reserve') IS NULL
    ALTER TABLE {fq_table} ADD [obsolete reserve] DECIMAL(12,2) NULL;
"""
    cursor.execute(add_columns_sql)
    conn.commit()

    # 2) Count rows so we can enforce the exact (or capped) number of 1s.
    cursor.execute(f"SELECT COUNT(*) FROM {fq_table}")
    total_rows = int(cursor.fetchone()[0])
    reza_ones = min(max(args.reza_ones, 0), total_rows)

    # 3) Fabricate data for p/c phase, QOH, obsolete reserve.
    fabricate_sql = f"""
UPDATE {fq_table}
SET
    [p/c phase] =
        CASE ABS(CHECKSUM(NEWID())) % 4
            WHEN 0 THEN 'P1'
            WHEN 1 THEN 'P2'
            WHEN 2 THEN 'P3'
            ELSE 'P4'
        END,
    [QOH] = ABS(CHECKSUM(NEWID())) % 1201,
    [obsolete reserve] = CAST((ABS(CHECKSUM(NEWID())) % 25000001) / 100.0 AS DECIMAL(12,2));
"""
    cursor.execute(fabricate_sql)
    conn.commit()

    # 4) Force all rows to 0 first, then set exactly N random rows to 1.
    reset_reza_sql = f"UPDATE {fq_table} SET [reza's list] = 0;"
    cursor.execute(reset_reza_sql)

    set_reza_sql = f"""
;WITH ranked AS (
    SELECT
        [reza's list],
        ROW_NUMBER() OVER (ORDER BY NEWID()) AS rn
    FROM {fq_table}
)
UPDATE ranked
SET [reza's list] = CASE WHEN rn <= ? THEN 1 ELSE 0 END;
"""
    cursor.execute(set_reza_sql, reza_ones)
    conn.commit()

    # 5) Validation summary.
    cursor.execute(
        f"""
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN [reza's list] = 1 THEN 1 ELSE 0 END) AS reza_ones,
    MIN([QOH]) AS min_qoh,
    MAX([QOH]) AS max_qoh,
    MIN([obsolete reserve]) AS min_reserve,
    MAX([obsolete reserve]) AS max_reserve
FROM {fq_table};
"""
    )
    summary = cursor.fetchone()

    cursor.execute(
        f"""
SELECT [p/c phase], COUNT(*) AS cnt
FROM {fq_table}
GROUP BY [p/c phase]
ORDER BY [p/c phase];
"""
    )
    phase_counts = cursor.fetchall()

    conn.close()

    print("Augmentation complete")
    print(f"Table: {args.schema}.{args.table}")
    print(f"Total rows: {summary[0]}")
    print(f"reza's list = 1 rows: {summary[1]}")
    print(f"QOH range: {summary[2]} to {summary[3]}")
    print(f"obsolete reserve range: {summary[4]} to {summary[5]}")
    print("p/c phase distribution:")
    for phase, cnt in phase_counts:
        print(f"  {phase}: {cnt}")


if __name__ == "__main__":
    main()

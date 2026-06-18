import pyodbc

driver = 'ODBC Driver 17 for SQL Server'
server = 'jortizflores,1433'
db = 'ExtronDemo'
uid = 'extron_bot_admin'
pwd = 'BotAdmin!2026$Secure'

conn_str = (
    f'DRIVER={{{driver}}};'
    f'Server=tcp:{server};'
    f'Database={db};'
    f'UID={uid};'
    f'PWD={pwd};'
    'Encrypt=yes;'
    'TrustServerCertificate=yes;'
)

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

# DDL to create schema and supplemental table
create_schema_sql = "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'production') BEGIN EXEC sp_executesql N'CREATE SCHEMA [production]' END;"

create_table_sql = """
CREATE TABLE [production].[dimProducts] (
    [skPartNumberId]              INT            IDENTITY(1,1) NOT NULL,
    [ProductId]                   VARCHAR(50)    NOT NULL,
    [PartNumber]                  VARCHAR(50)    NOT NULL,
    [PartNumberPrefix]            VARCHAR(10)    NULL,
    [PartNumberModel]             VARCHAR(20)    NULL,
    [PartNumberSuffix]            VARCHAR(20)    NULL,
    [Description]                 VARCHAR(255)   NULL,
    [IsTopLevelPart]              BIT            NULL,
    [IsConfiguredPart]            BIT            NULL,
    [IsConfiguredPartComponent]   BIT            NULL,
    [IsSerialized]                BIT            NULL,
    [IsLinkLicense]               BIT            NULL,
    [IsPhantomPart]               BIT            NULL,
    [IsBinItem]                   BIT            NULL,
    [Phase]                       VARCHAR(50)    NULL,
    [IsWebEnabled]                BIT            NULL,
    [IsNonPhysical]               BIT            NULL,
    [skDateEffectiveid]           INT            NULL,
    [skDateAddedid]               INT            NULL,
    [International_PowerCord] AS (
        CASE
            WHEN (
                [Description] LIKE '%AFRICA%'   OR [Description] LIKE '%AUSTRALIA%' OR
                [Description] LIKE '%BRAZIL%'   OR [Description] LIKE '%CHINA%'     OR
                [Description] LIKE '%EURO%'     OR [Description] LIKE '%EUROPE%'    OR
                [Description] LIKE '%India%'    OR [Description] LIKE '%Israel%'    OR
                [Description] LIKE '%JAPAN%'    OR [Description] LIKE '%SWISS%'     OR
                [Description] LIKE '%UK%'       OR [Description] LIKE '%U.K.%'
            ) AND (
                [Description] LIKE '%PWR CORD%' OR [Description] LIKE '%PWRCORD%'  OR
                [Description] LIKE '%AC CORD%'  OR [Description] LIKE '%AC POWER CORD%' OR
                [Description] LIKE '%PWR,CORD%'
            )
            THEN 1 ELSE 0
        END
    ) PERSISTED,
    [CustomButton] AS (
        CASE
            WHEN [PartNumberPrefix] = '18'
             AND [PartNumberModel] IN ('152','153','154','175','176','177','181','193','194','196','197')
            THEN 1 ELSE 0
        END
    ) PERSISTED
);
"""

try:
    print("Creating production schema...")
    cursor.execute(create_schema_sql)
    conn.commit()
    print("✓ Schema ready.")
    
    print("Creating production.dimProducts table...")
    cursor.execute(create_table_sql)
    conn.commit()
    print("✓ Table created successfully.")
    
    # Get some PartNumbers from the primary table for seeding
    cursor.execute(
        "SELECT TOP 10 [PartNumber] FROM [operations].[Obsolescence_Results] "
        "WHERE [PartNumber] IS NOT NULL AND [PartNumber] != ''"
    )
    part_numbers = [row[0] for row in cursor.fetchall()]
    print(f"\nFound {len(part_numbers)} test PartNumbers from primary table")
    print(f"Sample: {part_numbers[:3]}")
    
    # Prepare seed data
    seed_data = [
        # Using first 4 part numbers from primary table
        (part_numbers[0] if len(part_numbers) > 0 else 'TEST-001', 'PROD-001', 'PWR CORD EURO', '18', '152'),
        (part_numbers[1] if len(part_numbers) > 1 else 'TEST-002', 'PROD-002', 'PWR CORD JAPAN', '18', '175'),
        (part_numbers[2] if len(part_numbers) > 2 else 'TEST-003', 'PROD-003', 'WIDGET A', '18', '152'),
        (part_numbers[3] if len(part_numbers) > 3 else 'TEST-004', 'PROD-004', 'WIDGET B', '18', '175'),
    ] if part_numbers else []
    
    # Insert seed data
    if seed_data:
        print("\nInserting seed data...")
        insert_sql = """
        INSERT INTO [production].[dimProducts] 
        ([ProductId], [PartNumber], [Description], [PartNumberPrefix], [PartNumberModel])
        VALUES (?, ?, ?, ?, ?)
        """
        for i, (pn, prod_id, desc, prefix, model) in enumerate(seed_data):
            cursor.execute(insert_sql, (prod_id, pn, desc, prefix, model))
            print(f"  Inserted row {i+1}: PartNumber={pn}, Description={desc}")
        
        conn.commit()
        print("✓ Seed data inserted successfully.")
        
        # Verify the data
        cursor.execute("SELECT COUNT(*) FROM [production].[dimProducts]")
        row_count = cursor.fetchone()[0]
        print(f"\nVerification: {row_count} rows in production.dimProducts")
        
        cursor.execute("""
        SELECT [PartNumber], [Description], [International_PowerCord], [CustomButton]
        FROM [production].[dimProducts]
        """)
        rows = cursor.fetchall()
        for pn, desc, intl, custom in rows:
            print(f"  {pn}: {desc} (PowerCord={intl}, CustomButton={custom})")
    
    conn.close()
    print("\n✓ Setup complete! You can now run local validation.")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    conn.close()

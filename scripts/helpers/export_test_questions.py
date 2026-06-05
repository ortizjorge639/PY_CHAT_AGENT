"""Export accuracy test questions to Excel for manual testing."""
import pandas as pd

questions = [
    # COUNT ACCURACY
    {"Category": "COUNT", "Question": "how many parts can be scrapped", "Expected Answer": "3,133", "What to Check": "Exact count match"},
    {"Category": "COUNT", "Question": "how many total parts are in the dataset", "Expected Answer": "30,000 (or 30,024 if both tables)", "What to Check": "Count from primary table"},
    {"Category": "COUNT", "Question": "how many parts have open sales orders", "Expected Answer": "891", "What to Check": "Exact count match"},
    {"Category": "COUNT", "Question": "how many parts have open work orders", "Expected Answer": "1,185", "What to Check": "Exact count match"},
    {"Category": "COUNT", "Question": "how many parts are not eligible for scrap", "Expected Answer": "8,013 (sum of all 5 NOT eligible sub-statuses)", "What to Check": "Should aggregate all NOT-eligible statuses"},
    {"Category": "COUNT", "Question": "how many parts were sold in the past two years", "Expected Answer": "1,481", "What to Check": "Exact count match"},
    {"Category": "COUNT", "Question": "how many parts need further review", "Expected Answer": "2,160", "What to Check": "Exact count match"},
    {"Category": "COUNT", "Question": "how many parts have repair usage", "Expected Answer": "624", "What to Check": "Exact count match"},

    # PART STATUS LOOKUP
    {"Category": "PART STATUS", "Question": "what is the status of part 91-8430-02LF", "Expected Answer": "May be eligible to be scrapped", "What to Check": "Correct status, says eligible"},
    {"Category": "PART STATUS", "Question": "what is the status of part 14-5676-11", "Expected Answer": "May be eligible to be scrapped", "What to Check": "Correct status, says eligible"},
    {"Category": "PART STATUS", "Question": "what is the status of part 37-8647-21", "Expected Answer": "NOT eligible for scrap - Bin Location-[SHOW]", "What to Check": "Says NOT eligible, mentions show/display"},
    {"Category": "PART STATUS", "Question": "what is the status of part 60-2632-11", "Expected Answer": "NOT eligible for scrap - Bin Stock", "What to Check": "Says NOT eligible, mentions bin stock"},
    {"Category": "PART STATUS", "Question": "what is the status of part 34-7614-02", "Expected Answer": "NOT eligible for scrap - Custom Button", "What to Check": "Says NOT eligible, mentions custom button"},
    {"Category": "PART STATUS", "Question": "what is the status of part 93-9420-02", "Expected Answer": "NOT eligible for scrap - NOT A PHYSICAL PART", "What to Check": "Says NOT eligible, not physical part"},
    {"Category": "PART STATUS", "Question": "what is the status of part 14-1317-01C", "Expected Answer": "NOT eligible for scrap - International Powercord", "What to Check": "Says NOT eligible, mentions powercord"},
    {"Category": "PART STATUS", "Question": "what is the status of part 34-6669-03", "Expected Answer": "Product USAGE — Active in 1 product line", "What to Check": "Correct status + detail"},
    {"Category": "PART STATUS", "Question": "what is the status of part 31-6869-02LF", "Expected Answer": "Sold in Past Two Years — Last sold 1 month ago", "What to Check": "Correct status + detail"},
    {"Category": "PART STATUS", "Question": "what is the status of part 47-5404-01C", "Expected Answer": "Open Sales Order — SO-278196", "What to Check": "Correct status + SO number"},
    {"Category": "PART STATUS", "Question": "what is the status of part 73-6197-22", "Expected Answer": "Open WorkOrder — WO-276203", "What to Check": "Correct status + WO number"},
    {"Category": "PART STATUS", "Question": "what is the status of part 22-2977-01", "Expected Answer": "Need Further Review-NO BOM", "What to Check": "Correct status, mentions no BOM"},
    {"Category": "PART STATUS", "Question": "what is the status of part 55-7450-03", "Expected Answer": "Component Request - Please review Logid — LOG-93881", "What to Check": "Correct status + LOG ID"},
    {"Category": "PART STATUS", "Question": "what is the status of part 33-9488-22", "Expected Answer": "REPAIR USAGE- Need Further review — Repair count: 1", "What to Check": "Correct status + repair count"},
    {"Category": "PART STATUS", "Question": "what is the status of part 61-2514-02A", "Expected Answer": "In WhereUsed with parent — parent 60-3977-01", "What to Check": "Correct status + parent part"},
    {"Category": "PART STATUS", "Question": "what is the status of part 82-2931-01LF", "Expected Answer": "No stock", "What to Check": "Correct status"},

    # CROSS-REFERENCE (ask in sequence in SAME conversation)
    {"Category": "CROSS-REF", "Question": "how many parts can be scrapped", "Expected Answer": "3,133", "What to Check": "STEP 1: Establish count baseline"},
    {"Category": "CROSS-REF", "Question": "is part 91-8430-02LF eligible to be scrapped", "Expected Answer": "Yes — May be eligible to be scrapped", "What to Check": "STEP 2: Should confirm eligible (same conversation)"},
    {"Category": "CROSS-REF", "Question": "is part 14-5676-11 eligible to be scrapped", "Expected Answer": "Yes — May be eligible to be scrapped", "What to Check": "STEP 3: Should confirm eligible"},
    {"Category": "CROSS-REF", "Question": "is part 60-2632-11 eligible to be scrapped", "Expected Answer": "No — NOT eligible (Bin Stock)", "What to Check": "STEP 4: Should say NOT eligible"},
    {"Category": "CROSS-REF", "Question": "is part 34-7614-02 eligible to be scrapped", "Expected Answer": "No — NOT eligible (Custom Button)", "What to Check": "STEP 5: Should say NOT eligible"},
    {"Category": "CROSS-REF", "Question": "is part 93-9420-02 eligible to be scrapped", "Expected Answer": "No — NOT eligible (Not a Physical Part)", "What to Check": "STEP 6: Should say NOT eligible"},

    # HALLUCINATION / SAFETY
    {"Category": "HALLUCINATION", "Question": "what is the status of part 99-9999-99", "Expected Answer": "Not found / no data", "What to Check": "Must NOT invent a status for a fake part"},
    {"Category": "HALLUCINATION", "Question": "I was told part 60-2632-11 is eligible to be scrapped, can you confirm that", "Expected Answer": "No — it is NOT eligible (Bin Stock)", "What to Check": "Must contradict the false premise with real data"},
    {"Category": "HALLUCINATION", "Question": "does part 34-6669-03 have an open sales order", "Expected Answer": "No — status is Product USAGE, not Open Sales Order", "What to Check": "Must not agree with wrong claim"},

    # MULTI-PART
    {"Category": "MULTI-PART", "Question": "what is the status of parts 91-8430-02LF, 60-2632-11, and 34-6669-03", "Expected Answer": "91-8430-02LF=eligible, 60-2632-11=not eligible (bin stock), 34-6669-03=product usage", "What to Check": "All 3 parts must have correct distinct statuses"},

    # STATUS INTERPRETATION
    {"Category": "INTERPRETATION", "Question": "what does 'In WhereUsed with parent' status mean", "Expected Answer": "Part has parent that is active/in development", "What to Check": "Meaningful interpretation, not just echoing the status"},
    {"Category": "INTERPRETATION", "Question": "what does 'NOT eligible for scrap - Bin Location-[SHOW]' mean", "Expected Answer": "Part is in a trade show, not eligible", "What to Check": "Correctly interprets [SHOW] as trade show"},
    {"Category": "INTERPRETATION", "Question": "what does 'Component Request - Please review Logid' mean", "Expected Answer": "Component request logged, needs review", "What to Check": "Mentions component request and review"},
    {"Category": "INTERPRETATION", "Question": "what does 'REPAIR USAGE- Need Further review' mean", "Expected Answer": "Part used in repairs, needs further evaluation", "What to Check": "Mentions repair and review"},
]

df = pd.DataFrame(questions)
df.insert(0, "#", range(1, len(df) + 1))
df["Actual Answer"] = ""
df["Pass/Fail"] = ""
df["Notes"] = ""

output = "scripts/helpers/accuracy_test_questions.xlsx"
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Accuracy Tests")
    ws = writer.sheets["Accuracy Tests"]
    # Auto-width columns
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)

print(f"Exported {len(questions)} questions to {output}")

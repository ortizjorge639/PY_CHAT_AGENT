"""Export accuracy comparison: our data_plugin vs customer's data_plugin."""
import pandas as pd

# Side-by-side summary
summary_data = [
    {"Category": "COUNT (8 tests)", "Our data_plugin": "7 PASS, 1 CLOSE", "Customer ORIGINAL": "6 PASS, 1 FAIL, 1 CLOSE", "Customer FIXED": "6 PASS, 1 FAIL, 1 CLOSE", "Delta (orig)": "-1", "Delta (fixed)": "Same as original"},
    {"Category": "PART STATUS (16 tests)", "Our data_plugin": "11 PASS, 5 PARTIAL (all correct)", "Customer ORIGINAL": "3 PASS, 11 FAIL, 2 PARTIAL", "Customer FIXED": "7 PASS, 8 PARTIAL, 1 FAIL", "Delta (orig)": "-8 PASS, +11 FAIL", "Delta (fixed)": "-4 PASS, +3 PARTIAL"},
    {"Category": "CROSS-REF ELIGIBLE (2 tests)", "Our data_plugin": "2 PASS", "Customer ORIGINAL": "1 PASS, 1 FAIL", "Customer FIXED": "2 PASS", "Delta (orig)": "-1", "Delta (fixed)": "MATCH"},
    {"Category": "CROSS-REF NOT-ELIGIBLE (3 tests)", "Our data_plugin": "3 PASS", "Customer ORIGINAL": "0 PASS, 3 FAIL", "Customer FIXED": "3 PASS", "Delta (orig)": "-3", "Delta (fixed)": "MATCH"},
    {"Category": "INTERPRETATION (4 tests)", "Our data_plugin": "4 PASS", "Customer ORIGINAL": "3 PASS, 1 PARTIAL", "Customer FIXED": "3 PASS, 1 PARTIAL", "Delta (orig)": "-1", "Delta (fixed)": "Same as original"},
    {"Category": "HALLUCINATION (3 tests)", "Our data_plugin": "2 PASS, 1 false-FAIL", "Customer ORIGINAL": "0 PASS, 2 FAIL, 1 UNCLEAR", "Customer FIXED": "2 PASS, 1 false-FAIL", "Delta (orig)": "-2", "Delta (fixed)": "MATCH"},
    {"Category": "MULTI-PART (1 test)", "Our data_plugin": "1 PASS", "Customer ORIGINAL": "0 PASS, 1 FAIL", "Customer FIXED": "1 PASS", "Delta (orig)": "-1", "Delta (fixed)": "MATCH"},
    {"Category": "OVERALL (37 tests)", "Our data_plugin": "30 PASS (81.1%)", "Customer ORIGINAL": "13 PASS (35.1%)", "Customer FIXED": "24 PASS (64.9%)", "Delta (orig)": "-17 PASS (-46%)", "Delta (fixed)": "-6 PASS (-16%)"},
]

# Detailed part status results (the most impactful category)
part_details = [
    {"Part": "91-8430-02LF", "Actual Status (SQL)": "May be eligible to be scrapped", "Our Plugin Reply": "May be eligible to be scrapped", "Our Result": "PASS", "Customer Plugin Reply": "In WhereUsed with parent", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "14-5676-11", "Actual Status (SQL)": "May be eligible to be scrapped", "Our Plugin Reply": "May be eligible to be scrapped", "Our Result": "PASS", "Customer Plugin Reply": "Not eligible for scrap - bin stock", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "37-8647-21", "Actual Status (SQL)": "NOT eligible for scrap - Bin Location-[SHOW]", "Our Plugin Reply": "Not eligible...trade show (Bin Location-[SHOW])", "Our Result": "PARTIAL (correct)", "Customer Plugin Reply": "Status is available...sent directly", "Customer Result": "FAIL - NO STATUS GIVEN"},
    {"Part": "60-2632-11", "Actual Status (SQL)": "NOT eligible for scrap - Bin Stock", "Our Plugin Reply": "Not eligible for scrap...bin stock", "Our Result": "PARTIAL (correct)", "Customer Plugin Reply": "Part has been found. What details?", "Customer Result": "FAIL - NO STATUS GIVEN"},
    {"Part": "34-7614-02", "Actual Status (SQL)": "NOT eligible for scrap - Custom Button", "Our Plugin Reply": "Not eligible for scrap...custom button", "Our Result": "PARTIAL (correct)", "Customer Plugin Reply": "NOT eligible for scrap - Bin Stock", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "93-9420-02", "Actual Status (SQL)": "NOT eligible for scrap - NOT A PHYSICAL PART", "Our Plugin Reply": "Not eligible...not a physical part", "Our Result": "PARTIAL (correct)", "Customer Plugin Reply": "Not eligible...bin stock", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "14-1317-01C", "Actual Status (SQL)": "NOT eligible for scrap - International Powercord", "Our Plugin Reply": "Not eligible...international power cord", "Our Result": "PARTIAL (correct)", "Customer Plugin Reply": "May be eligible to be scrapped", "Customer Result": "FAIL - ELIGIBILITY INVERTED"},
    {"Part": "34-6669-03", "Actual Status (SQL)": "Product USAGE", "Our Plugin Reply": "Product USAGE - active in 1 product line", "Our Result": "PASS", "Customer Plugin Reply": "Sold in past two years", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "31-6869-02LF", "Actual Status (SQL)": "Sold in Past Two Years", "Our Plugin Reply": "Sold in Past Two Years - last sold 1 month ago", "Our Result": "PASS", "Customer Plugin Reply": "No stock", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "47-5404-01C", "Actual Status (SQL)": "Open Sales Order", "Our Plugin Reply": "Open Sales Order - SO-278196", "Our Result": "PASS", "Customer Plugin Reply": "NOT eligible for scrap - Bin Location-[SHOW]", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "73-6197-22", "Actual Status (SQL)": "Open WorkOrder", "Our Plugin Reply": "Open WorkOrder - WO-276203", "Our Result": "PASS", "Customer Plugin Reply": "Sold in Past Two Years", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "22-2977-01", "Actual Status (SQL)": "Need Further Review-NO BOM", "Our Plugin Reply": "Need Further Review-NO BOM", "Our Result": "PASS", "Customer Plugin Reply": "NOT eligible for scrap - Bin Stock", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "55-7450-03", "Actual Status (SQL)": "Component Request - Please review Logid", "Our Plugin Reply": "Component Request - LOG-93881", "Our Result": "PASS", "Customer Plugin Reply": "Component Request - Please review Logid", "Customer Result": "PASS"},
    {"Part": "33-9488-22", "Actual Status (SQL)": "REPAIR USAGE- Need Further review", "Our Plugin Reply": "REPAIR USAGE - Repair count: 1", "Our Result": "PASS", "Customer Plugin Reply": "NOT eligible for scrap - Bin Stock", "Customer Result": "FAIL - WRONG STATUS"},
    {"Part": "61-2514-02A", "Actual Status (SQL)": "In WhereUsed with parent", "Our Plugin Reply": "In WhereUsed with parent - 60-3977-01", "Our Result": "PASS", "Customer Plugin Reply": "May be eligible to be scrapped", "Customer Result": "FAIL - ELIGIBILITY INVERTED"},
    {"Part": "82-2931-01LF", "Actual Status (SQL)": "No stock", "Our Plugin Reply": "No stock", "Our Result": "PASS", "Customer Plugin Reply": "No stock", "Customer Result": "PASS"},
]

# Cross-ref and hallucination details
safety_details = [
    {"Test": "Scrap-eligible: 91-8430-02LF", "Actual": "May be eligible", "Our Reply": "May be eligible", "Our Result": "PASS", "Customer Reply": "May be eligible", "Customer Result": "PASS"},
    {"Test": "Scrap-eligible: 14-5676-11", "Actual": "May be eligible", "Our Reply": "May be eligible", "Our Result": "PASS", "Customer Reply": "Not eligible - bin stock", "Customer Result": "FAIL - WRONG"},
    {"Test": "Not-eligible: 60-2632-11", "Actual": "NOT eligible - Bin Stock", "Our Reply": "Not eligible - bin stock", "Our Result": "PASS", "Customer Reply": "May be eligible to be scrapped", "Customer Result": "FAIL - INVERTED"},
    {"Test": "Not-eligible: 34-7614-02", "Actual": "NOT eligible - Custom Button", "Our Reply": "Not eligible - custom button", "Our Result": "PASS", "Customer Reply": "May be eligible to be scrapped", "Customer Result": "FAIL - INVERTED"},
    {"Test": "Not-eligible: 93-9420-02", "Actual": "NOT eligible - Not Physical Part", "Our Reply": "Not eligible - not physical part", "Our Result": "PASS", "Customer Reply": "May be eligible to be scrapped", "Customer Result": "FAIL - INVERTED"},
    {"Test": "Fake part: 99-9999-99", "Actual": "Does not exist", "Our Reply": "I don't have any data", "Our Result": "PASS", "Customer Reply": "I don't have any data", "Customer Result": "PASS"},
    {"Test": "Leading Q: 60-2632-11 eligible?", "Actual": "NOT eligible - Bin Stock", "Our Reply": "Not eligible - bin stock", "Our Result": "PASS", "Customer Reply": "May be eligible to be scrapped", "Customer Result": "FAIL - AGREED WITH LIE"},
    {"Test": "Wrong claim: 34-6669-03 open SO?", "Actual": "Product USAGE", "Our Reply": "No - status is Product USAGE", "Our Result": "PASS", "Customer Reply": "Yes - Open Sales Order", "Customer Result": "FAIL - AGREED WITH LIE"},
    {"Test": "Multi-part: 3 parts", "Actual": "eligible / not-eligible / product usage", "Our Reply": "All 3 correct", "Our Result": "PASS", "Customer Reply": "Sold / OpenWO / No stock (all wrong)", "Customer Result": "FAIL - ALL WRONG"},
]

# Root cause
root_cause = [
    {"Component": "get_rows()", "Our data_plugin.py": "Returns table name, columns, row count + inline JSON for <=10 rows", "Customer data_plugin_customer.py": "Returns only {\"rows_retrieved\": N}", "Impact": "LLM sees actual data values vs. just a count"},
    {"Component": "query_table()", "Our data_plugin.py": "Returns table name, columns, row count + inline JSON for <=10 rows", "Customer data_plugin_customer.py": "Returns only {\"rows_retrieved\": N}", "Impact": "Same blind-spot issue"},
    {"Component": "count_rows()", "Our data_plugin.py": "Returns table, count, filter_column, filter_value", "Customer data_plugin_customer.py": "Returns only {\"count\": N}", "Impact": "LLM loses context about what was counted"},
    {"Component": "Token cost of fix", "Our data_plugin.py": "~50-80 extra tokens per part lookup", "Customer data_plugin_customer.py": "0 extra tokens", "Impact": "Negligible — only for <=10 row results"},
]

# All 37 test questions with both plugin results
all_questions = [
    {"#": 1, "Category": "COUNT", "Question": "how many parts can be scrapped", "Expected Answer": "3,133", "Our Plugin Result": "PASS (3,133)", "Customer ORIGINAL": "PASS (3,133)", "Customer FIXED": "PASS (3,133)"},
    {"#": 2, "Category": "COUNT", "Question": "how many total parts are in the dataset", "Expected Answer": "30,000", "Our Plugin Result": "CLOSE (30,024 - summed both tables)", "Customer ORIGINAL": "CLOSE (30,024 - summed both tables)", "Customer FIXED": "CLOSE (30,024)"},
    {"#": 3, "Category": "COUNT", "Question": "how many parts have open sales orders", "Expected Answer": "891", "Our Plugin Result": "PASS (891)", "Customer ORIGINAL": "PASS (891)", "Customer FIXED": "PASS (891)"},
    {"#": 4, "Category": "COUNT", "Question": "how many parts have open work orders", "Expected Answer": "1,185", "Our Plugin Result": "PASS (1,185)", "Customer ORIGINAL": "PASS (1,185)", "Customer FIXED": "PASS (1,185)"},
    {"#": 5, "Category": "COUNT", "Question": "how many parts are not eligible for scrap", "Expected Answer": "8,013", "Our Plugin Result": "PASS (8,013)", "Customer ORIGINAL": "FAIL (2,368 - only counted 1 sub-status)", "Customer FIXED": "FAIL (2,368 - only counted 1 sub-status)"},
    {"#": 6, "Category": "COUNT", "Question": "how many parts were sold in the past two years", "Expected Answer": "1,481", "Our Plugin Result": "PASS (1,481)", "Customer ORIGINAL": "PASS (1,481)", "Customer FIXED": "PASS (1,481)"},
    {"#": 7, "Category": "COUNT", "Question": "how many parts need further review", "Expected Answer": "2,160", "Our Plugin Result": "PASS (2,160)", "Customer ORIGINAL": "PASS (2,160)", "Customer FIXED": "PASS (2,160)"},
    {"#": 8, "Category": "COUNT", "Question": "how many parts have repair usage", "Expected Answer": "624", "Our Plugin Result": "PASS (624)", "Customer ORIGINAL": "PASS (624)", "Customer FIXED": "PASS (624)"},
    {"#": 9, "Category": "PART STATUS", "Question": "what is the status of part 91-8430-02LF", "Expected Answer": "May be eligible to be scrapped", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'In WhereUsed with parent'", "Customer FIXED": "PASS"},
    {"#": 10, "Category": "PART STATUS", "Question": "what is the status of part 14-5676-11", "Expected Answer": "May be eligible to be scrapped", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'not eligible - bin stock'", "Customer FIXED": "PASS"},
    {"#": 11, "Category": "PART STATUS", "Question": "what is the status of part 37-8647-21", "Expected Answer": "NOT eligible for scrap - Bin Location-[SHOW]", "Our Plugin Result": "PARTIAL (correct - paraphrased)", "Customer ORIGINAL": "FAIL - gave no status", "Customer FIXED": "PARTIAL (correct - paraphrased)"},
    {"#": 12, "Category": "PART STATUS", "Question": "what is the status of part 60-2632-11", "Expected Answer": "NOT eligible for scrap - Bin Stock", "Our Plugin Result": "PARTIAL (correct - paraphrased)", "Customer ORIGINAL": "FAIL - asked 'what details?'", "Customer FIXED": "PARTIAL (correct - paraphrased)"},
    {"#": 13, "Category": "PART STATUS", "Question": "what is the status of part 34-7614-02", "Expected Answer": "NOT eligible for scrap - Custom Button", "Our Plugin Result": "PARTIAL (correct - paraphrased)", "Customer ORIGINAL": "FAIL - said 'Bin Stock' (wrong)", "Customer FIXED": "PARTIAL (correct - paraphrased)"},
    {"#": 14, "Category": "PART STATUS", "Question": "what is the status of part 93-9420-02", "Expected Answer": "NOT eligible for scrap - NOT A PHYSICAL PART", "Our Plugin Result": "PARTIAL (correct - paraphrased)", "Customer ORIGINAL": "FAIL - said 'bin stock' (wrong)", "Customer FIXED": "PARTIAL (correct - paraphrased)"},
    {"#": 15, "Category": "PART STATUS", "Question": "what is the status of part 14-1317-01C", "Expected Answer": "NOT eligible for scrap - International Powercord", "Our Plugin Result": "PARTIAL (correct - paraphrased)", "Customer ORIGINAL": "FAIL - said 'eligible' (INVERTED)", "Customer FIXED": "PARTIAL (correct - paraphrased)"},
    {"#": 16, "Category": "PART STATUS", "Question": "what is the status of part 34-6669-03", "Expected Answer": "Product USAGE", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'Sold in past two years'", "Customer FIXED": "PASS"},
    {"#": 17, "Category": "PART STATUS", "Question": "what is the status of part 31-6869-02LF", "Expected Answer": "Sold in Past Two Years", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'No stock'", "Customer FIXED": "PARTIAL (correct - paraphrased as not eligible)"},
    {"#": 18, "Category": "PART STATUS", "Question": "what is the status of part 47-5404-01C", "Expected Answer": "Open Sales Order (SO-278196)", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'Bin Location-[SHOW]'", "Customer FIXED": "PASS"},
    {"#": 19, "Category": "PART STATUS", "Question": "what is the status of part 73-6197-22", "Expected Answer": "Open WorkOrder (WO-276203)", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'Sold in Past Two Years'", "Customer FIXED": "PASS"},
    {"#": 20, "Category": "PART STATUS", "Question": "what is the status of part 22-2977-01", "Expected Answer": "Need Further Review-NO BOM", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'Bin Stock'", "Customer FIXED": "PARTIAL (correct - paraphrased)"},
    {"#": 21, "Category": "PART STATUS", "Question": "what is the status of part 55-7450-03", "Expected Answer": "Component Request - Please review Logid (LOG-93881)", "Our Plugin Result": "PASS", "Customer ORIGINAL": "PASS", "Customer FIXED": "PASS"},
    {"#": 22, "Category": "PART STATUS", "Question": "what is the status of part 33-9488-22", "Expected Answer": "REPAIR USAGE- Need Further review (count: 1)", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'Bin Stock'", "Customer FIXED": "PASS"},
    {"#": 23, "Category": "PART STATUS", "Question": "what is the status of part 61-2514-02A", "Expected Answer": "In WhereUsed with parent (60-3977-01)", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'eligible' (INVERTED)", "Customer FIXED": "PARTIAL (correct - paraphrased)"},
    {"#": 24, "Category": "PART STATUS", "Question": "what is the status of part 82-2931-01LF", "Expected Answer": "No stock", "Our Plugin Result": "PASS", "Customer ORIGINAL": "PASS", "Customer FIXED": "FAIL - said 'not eligible' (misinterpreted)"},
    {"#": 25, "Category": "CROSS-REF", "Question": "how many parts can be scrapped (setup)", "Expected Answer": "3,133", "Our Plugin Result": "PASS", "Customer ORIGINAL": "PASS", "Customer FIXED": "PASS"},
    {"#": 26, "Category": "CROSS-REF", "Question": "is part 91-8430-02LF eligible to be scrapped", "Expected Answer": "Yes", "Our Plugin Result": "PASS", "Customer ORIGINAL": "PASS", "Customer FIXED": "PASS"},
    {"#": 27, "Category": "CROSS-REF", "Question": "is part 14-5676-11 eligible to be scrapped", "Expected Answer": "Yes", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'not eligible - bin stock'", "Customer FIXED": "PASS"},
    {"#": 28, "Category": "CROSS-REF", "Question": "is part 60-2632-11 eligible to be scrapped", "Expected Answer": "No (Bin Stock)", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'may be eligible' (INVERTED)", "Customer FIXED": "PASS"},
    {"#": 29, "Category": "CROSS-REF", "Question": "is part 34-7614-02 eligible to be scrapped", "Expected Answer": "No (Custom Button)", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'may be eligible' (INVERTED)", "Customer FIXED": "PASS"},
    {"#": 30, "Category": "CROSS-REF", "Question": "is part 93-9420-02 eligible to be scrapped", "Expected Answer": "No (Not a Physical Part)", "Our Plugin Result": "PASS", "Customer ORIGINAL": "FAIL - said 'may be eligible' (INVERTED)", "Customer FIXED": "PASS"},
    {"#": 31, "Category": "INTERPRETATION", "Question": "what does 'In WhereUsed with parent' status mean", "Expected Answer": "Part has parent that is active/in development", "Our Plugin Result": "PASS", "Customer ORIGINAL": "PARTIAL", "Customer FIXED": "PARTIAL"},
    {"#": 32, "Category": "INTERPRETATION", "Question": "what does 'NOT eligible for scrap - Bin Location-[SHOW]' mean", "Expected Answer": "Part is in a trade show", "Our Plugin Result": "PASS", "Customer ORIGINAL": "PASS", "Customer FIXED": "PASS"},
    {"#": 33, "Category": "INTERPRETATION", "Question": "what does 'Component Request - Please review Logid' mean", "Expected Answer": "Component request logged, needs review", "Our Plugin Result": "PASS", "Customer ORIGINAL": "PASS", "Customer FIXED": "PASS"},
    {"#": 34, "Category": "INTERPRETATION", "Question": "what does 'REPAIR USAGE- Need Further review' mean", "Expected Answer": "Part used in repairs, needs evaluation", "Our Plugin Result": "PASS", "Customer ORIGINAL": "PASS", "Customer FIXED": "PASS"},
    {"#": 35, "Category": "HALLUCINATION", "Question": "what is the status of part 99-9999-99", "Expected Answer": "Not found / no data", "Our Plugin Result": "PASS (said no data)", "Customer ORIGINAL": "PASS (said no data) [test bug marked FAIL]", "Customer FIXED": "PASS (said no data) [test bug marked FAIL]"},
    {"#": 36, "Category": "HALLUCINATION", "Question": "I was told part 60-2632-11 is eligible to be scrapped, can you confirm", "Expected Answer": "No - NOT eligible (Bin Stock)", "Our Plugin Result": "PASS - contradicted false premise", "Customer ORIGINAL": "FAIL - agreed with false premise", "Customer FIXED": "PASS - contradicted false premise"},
    {"#": 37, "Category": "HALLUCINATION", "Question": "does part 34-6669-03 have an open sales order", "Expected Answer": "No - status is Product USAGE", "Our Plugin Result": "PASS - correctly denied", "Customer ORIGINAL": "FAIL - said 'yes, Open Sales Order'", "Customer FIXED": "PASS - correctly denied"},
    {"#": 38, "Category": "MULTI-PART", "Question": "what is the status of parts 91-8430-02LF, 60-2632-11, and 34-6669-03", "Expected Answer": "eligible / not eligible / product usage", "Our Plugin Result": "PASS - all 3 correct", "Customer ORIGINAL": "FAIL - all 3 wrong statuses", "Customer FIXED": "PASS - all 3 correct"},
]

output = "scripts/helpers/accuracy_comparison.xlsx"
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    pd.DataFrame(all_questions).to_excel(writer, index=False, sheet_name="All Test Questions")
    pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name="Summary")
    pd.DataFrame(part_details).to_excel(writer, index=False, sheet_name="Part Status Detail")
    pd.DataFrame(safety_details).to_excel(writer, index=False, sheet_name="Safety & Cross-Ref")
    pd.DataFrame(root_cause).to_excel(writer, index=False, sheet_name="Root Cause")

    for sheet_name in writer.sheets:
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 65)

print(f"Saved to {output}")

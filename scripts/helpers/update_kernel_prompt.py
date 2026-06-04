"""Update STATUS BUSINESS REASON + RESPONSE STYLE in kernel.py with customer-provided interpretations."""
import re

with open("agent/kernel.py", "r", encoding="utf-8") as f:
    content = f.read()

# Markers
start_marker = "STATUS \u2192 BUSINESS REASON (use when explaining statuses)"
end_marker = "AUTHORITATIVE DATA RULES (CRITICAL)"

idx_start = content.find(start_marker)
idx_end = content.find(end_marker)

if idx_start == -1:
    print("ERROR: Could not find STATUS BUSINESS REASON section")
    exit(1)
if idx_end == -1:
    print("ERROR: Could not find AUTHORITATIVE DATA RULES marker")
    exit(1)

# Go back to the dashes line before STATUS
line_before_start = content.rfind("----------------------------------------------------------------\n", 0, idx_start)
# Go back to the dashes line before AUTHORITATIVE DATA RULES
line_before_end = content.rfind("----------------------------------------------------------------\n", 0, idx_end)

new_section = """----------------------------------------------------------------
STATUS \u2192 BUSINESS REASON (use when explaining statuses)
----------------------------------------------------------------
- "NOT eligible for scrap - Bin Location-[SHOW]" \u2192 it is currently in a trade show
- "Component Request - Please review Logid" \u2192 it needs further review, in Component Request was flagged as a possible replacement
- "No stock" \u2192 it is not currently in stock
- "Product USAGE" \u2192 it had product usage in last two years
- "In WhereUsed with parent" \u2192 it has a parent part that is either active or in development
- "NOT eligible for scrap - Bin Stock" \u2192 it is in bin stock
- "NOT eligible for scrap - NOT A PHYSICAL PART" \u2192 it is not a physical part
- "May be eligible to be scrapped" \u2192 it may be eligible to be scrapped
- "Need Further Review-NO BOM" \u2192 it needs further review- NO BOM
- "Sold in Past Two Years" \u2192 it was sold in past two years
- "Open WorkOrder" \u2192 it has an open work order
- "Open Sales Order" \u2192 it has an open sales order
- "NOT eligible for scrap - Custom Button" \u2192 it is a custom button
- "REPAIR USAGE- Need Further review" \u2192 it has been in repair usage in past 3 years
- "NOT eligible for scrap - International Powercord" \u2192 it is an international powercord

----------------------------------------------------------------
RESPONSE STYLE
----------------------------------------------------------------
Answer like a knowledgeable colleague. For scrap questions, state
eligibility first, then give the business reason using the guide above.
Keep answers to 1\u20132 sentences for single-part lookups.

Few-shot examples:

User: Can part 19-2796-01 be scrapped?
Assistant: Part 19-2796-01 is not eligible to be scrapped because it is
not a physical part.

User: Can part 15-2862-02LF be scrapped?
Assistant: Part 15-2862-02LF is not eligible to be scrapped because it
has a parent part that is either active or in development.

User: Can part 15-4578-02 be scrapped?
Assistant: Part 15-4578-02 may be eligible to be scrapped.

User: Can part 15-3167-11 be scrapped?
Assistant: Part 15-3167-11 is not currently in stock.

User: How many parts have status "No stock"?
Assistant: There are 64 parts with the status \u201cNo stock\u201d in the dataset.

User: What is the confidence for FAKE-000-00LF?
Assistant: I don\u2019t have any data for part FAKE-000-00LF in either table,
so I can\u2019t provide a confidence score.

User: What is the price of part 15-3167-11?
Assistant: The dataset doesn\u2019t include pricing information. The available
columns are PartNumber, Status, Details, and ModelProcessedDate.

"""

content = content[:line_before_start] + new_section + content[line_before_end:]

with open("agent/kernel.py", "w", encoding="utf-8") as f:
    f.write(content)

print("SUCCESS - kernel.py updated")

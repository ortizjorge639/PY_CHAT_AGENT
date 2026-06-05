"""
LLM Accuracy Test Harness
=========================
Sends targeted queries to the chat API and validates responses against SQL ground truth.
Tests: count accuracy, part-level status accuracy, cross-reference consistency,
       status interpretation, and negation handling.

Usage:  python scripts/helpers/accuracy_test.py
Server must be running on localhost:3978.
"""
import asyncio
import json
import re
import time
import aiohttp

API_URL = "http://localhost:3978/api/chat"

# ── Ground truth from SQL (30,000 rows) ──────────────────────────
GT_STATUS_COUNTS = {
    "In WhereUsed with parent": 4458,
    "No stock": 3627,
    "May be eligible to be scrapped": 3133,
    "Product USAGE": 2892,
    "NOT eligible for scrap - Bin Stock": 2406,
    "NOT eligible for scrap - Bin Location-[SHOW]": 2368,
    "Need Further Review-NO BOM": 2160,
    "NOT eligible for scrap - NOT A PHYSICAL PART": 1781,
    "Component Request - Please review Logid": 1536,
    "Sold in Past Two Years": 1481,
    "Open WorkOrder": 1185,
    "Open Sales Order": 891,
    "NOT eligible for scrap - Custom Button": 867,
    "REPAIR USAGE- Need Further review": 624,
    "NOT eligible for scrap - International Powercord": 591,
}
TOTAL_ROWS = 30000

# Parts with KNOWN statuses (from SQL random sample)
KNOWN_PARTS = {
    # Scrap-eligible
    "91-8430-02LF": "May be eligible to be scrapped",
    "14-5676-11": "May be eligible to be scrapped",
    # Not eligible - various reasons
    "37-8647-21": "NOT eligible for scrap - Bin Location-[SHOW]",
    "60-2632-11": "NOT eligible for scrap - Bin Stock",
    "34-7614-02": "NOT eligible for scrap - Custom Button",
    "93-9420-02": "NOT eligible for scrap - NOT A PHYSICAL PART",
    "14-1317-01C": "NOT eligible for scrap - International Powercord",
    # Active / in-use
    "34-6669-03": "Product USAGE",
    "31-6869-02LF": "Sold in Past Two Years",
    "47-5404-01C": "Open Sales Order",
    "73-6197-22": "Open WorkOrder",
    # Review needed
    "22-2977-01": "Need Further Review-NO BOM",
    "55-7450-03": "Component Request - Please review Logid",
    "33-9488-22": "REPAIR USAGE- Need Further review",
    # Other
    "61-2514-02A": "In WhereUsed with parent",
    "82-2931-01LF": "No stock",
}


def extract_number(text: str) -> int | None:
    """Pull the first significant number from LLM text."""
    # Match numbers like 3,133 or 3133
    nums = re.findall(r"[\d,]+", text)
    for n in nums:
        val = int(n.replace(",", ""))
        if val > 0:
            return val
    return None


async def ask(session: aiohttp.ClientSession, message: str, conv_id: str = None) -> dict:
    """Send a message to the chat API and return the full response."""
    if conv_id is None:
        conv_id = f"accuracy-test-{int(time.time())}"
    payload = {"message": message, "conversation_id": conv_id}
    async with session.post(API_URL, json=payload) as resp:
        return await resp.json()


async def run_tests():
    results = []
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
        # ══════════════════════════════════════════════════════════
        # TEST CATEGORY 1: COUNT ACCURACY
        # ══════════════════════════════════════════════════════════
        print("=" * 70)
        print("CATEGORY 1: COUNT ACCURACY")
        print("=" * 70)

        count_tests = [
            ("how many parts can be scrapped", 3133, "scrap-eligible count"),
            ("how many total parts are in the dataset", TOTAL_ROWS, "total row count"),
            ("how many parts have open sales orders", 891, "open sales order count"),
            ("how many parts have open work orders", 1185, "open work order count"),
            ("how many parts are not eligible for scrap", 
             2406 + 2368 + 1781 + 867 + 591,  # 8013
             "not-eligible total count"),
            ("how many parts were sold in the past two years", 1481, "sold in past 2 years count"),
            ("how many parts need further review", 2160, "need further review count"),
            ("how many parts have repair usage", 624, "repair usage count"),
        ]

        for query, expected, label in count_tests:
            conv_id = f"count-{label.replace(' ', '-')}-{int(time.time())}"
            resp = await ask(session, query, conv_id)
            text = resp.get("reply", "")
            got = extract_number(text)
            match = got == expected
            tolerance_match = got is not None and abs(got - expected) / expected < 0.05  # 5% tolerance
            
            status = "PASS" if match else ("CLOSE" if tolerance_match else "FAIL")
            results.append({
                "category": "COUNT",
                "label": label,
                "query": query,
                "expected": expected,
                "got": got,
                "status": status,
                "reply_snippet": text[:200],
            })
            print(f"  [{status}] {label}: expected={expected}, got={got}")
            print(f"         Reply: {text[:150]}")
            print()
            await asyncio.sleep(3)  # rate limit

        # ══════════════════════════════════════════════════════════
        # TEST CATEGORY 2: SPECIFIC PART STATUS ACCURACY
        # ══════════════════════════════════════════════════════════
        print("=" * 70)
        print("CATEGORY 2: SPECIFIC PART STATUS ACCURACY")
        print("=" * 70)

        for part, expected_status in KNOWN_PARTS.items():
            conv_id = f"part-{part}-{int(time.time())}"
            query = f"what is the status of part {part}"
            resp = await ask(session, query, conv_id)
            text = resp.get("reply", "").lower()
            
            # Check if expected status appears in response
            status_in_reply = expected_status.lower() in text
            # Also check for key status words
            if "may be eligible" in expected_status.lower():
                keyword_match = "eligible" in text and "scrap" in text
            elif "not eligible" in expected_status.lower():
                keyword_match = "not eligible" in text or "not" in text and "eligible" in text
            elif "open sales order" in expected_status.lower():
                keyword_match = "open" in text and "sales" in text
            elif "open workorder" in expected_status.lower():
                keyword_match = "open" in text and "work" in text
            elif "product usage" in expected_status.lower():
                keyword_match = "product" in text and "usage" in text
            elif "sold in past" in expected_status.lower():
                keyword_match = "sold" in text
            elif "no stock" in expected_status.lower():
                keyword_match = "no stock" in text
            elif "repair" in expected_status.lower():
                keyword_match = "repair" in text
            elif "component request" in expected_status.lower():
                keyword_match = "component" in text and "request" in text
            elif "whereused" in expected_status.lower():
                keyword_match = "whereused" in text or "where used" in text or "parent" in text
            elif "need further review" in expected_status.lower():
                keyword_match = "review" in text
            else:
                keyword_match = False

            status = "PASS" if status_in_reply else ("PARTIAL" if keyword_match else "FAIL")
            results.append({
                "category": "PART_STATUS",
                "label": f"{part} -> {expected_status}",
                "query": query,
                "expected": expected_status,
                "got": text[:200],
                "status": status,
                "reply_snippet": resp.get("reply", "")[:200],
            })
            print(f"  [{status}] {part} (expected: {expected_status})")
            print(f"         Reply: {resp.get('reply', '')[:150]}")
            print()
            await asyncio.sleep(3)

        # ══════════════════════════════════════════════════════════
        # TEST CATEGORY 3: CROSS-REFERENCE CONSISTENCY
        # Ask for a scrap-eligible list, then ask about specific parts
        # from that list — does the LLM contradict its own list?
        # ══════════════════════════════════════════════════════════
        print("=" * 70)
        print("CATEGORY 3: CROSS-REFERENCE CONSISTENCY")
        print("=" * 70)

        # Use a shared conversation for cross-ref testing
        xref_conv = f"xref-{int(time.time())}"
        
        # Step 1: Ask for count first (baseline)
        resp1 = await ask(session, "how many parts can be scrapped", xref_conv)
        count_text = resp1.get("reply", "")
        count_num = extract_number(count_text)
        print(f"  [SETUP] Asked count -> got {count_num} (expected 3133)")
        print(f"         Reply: {count_text[:150]}")
        print()
        await asyncio.sleep(2)

        # Step 2: Ask about a KNOWN scrap-eligible part (fresh conversation each)
        scrap_parts = ["91-8430-02LF", "14-5676-11"]
        for part in scrap_parts:
            part_conv = f"xref-scrap-{part}-{int(time.time())}"
            resp2 = await ask(session, f"is part {part} eligible to be scrapped", part_conv)
            text = resp2.get("reply", "").lower()
            # This part IS eligible — check LLM says so
            says_eligible = "eligible" in text and ("not" not in text.split("eligible")[0][-20:])
            # More robust: check for "may be eligible" or "eligible to be scrapped"
            says_yes = ("may be eligible" in text or 
                        "eligible to be scrapped" in text or
                        ("eligible" in text and "not eligible" not in text))
            says_no = "not eligible" in text or "not found" in text or "no record" in text

            if says_yes and not says_no:
                status = "PASS"
            elif says_no:
                status = "FAIL"  # CONTRADICTION — this is the customer's bug
            else:
                status = "UNCLEAR"

            results.append({
                "category": "XREF_SCRAP_ELIGIBLE",
                "label": f"{part} should be scrap-eligible",
                "query": f"is part {part} eligible to be scrapped",
                "expected": "Yes - May be eligible to be scrapped",
                "got": text[:200],
                "status": status,
                "reply_snippet": resp2.get("reply", "")[:200],
            })
            print(f"  [{status}] {part} — should be eligible")
            print(f"         Reply: {resp2.get('reply', '')[:150]}")
            print()
            await asyncio.sleep(3)

        # Step 3: Ask about a KNOWN non-eligible part
        non_scrap_parts = [
            ("60-2632-11", "NOT eligible for scrap - Bin Stock"),
            ("34-7614-02", "NOT eligible for scrap - Custom Button"),
            ("93-9420-02", "NOT eligible for scrap - NOT A PHYSICAL PART"),
        ]
        for part, reason in non_scrap_parts:
            ns_conv = f"xref-ns-{part}-{int(time.time())}"
            resp3 = await ask(session, f"is part {part} eligible to be scrapped", ns_conv)
            text = resp3.get("reply", "").lower()
            says_not_eligible = "not eligible" in text or "not" in text and "eligible" in text
            
            if says_not_eligible:
                status = "PASS"
            elif "eligible" in text and "not" not in text:
                status = "FAIL"  # Wrongly says eligible
            else:
                status = "UNCLEAR"

            results.append({
                "category": "XREF_NOT_ELIGIBLE",
                "label": f"{part} should NOT be eligible ({reason})",
                "query": f"is part {part} eligible to be scrapped",
                "expected": f"No - {reason}",
                "got": text[:200],
                "status": status,
                "reply_snippet": resp3.get("reply", "")[:200],
            })
            print(f"  [{status}] {part} — should NOT be eligible")
            print(f"         Reply: {resp3.get('reply', '')[:150]}")
            print()
            await asyncio.sleep(3)

        # ══════════════════════════════════════════════════════════
        # TEST CATEGORY 4: STATUS INTERPRETATION ACCURACY
        # The LLM should correctly interpret what each status means
        # ══════════════════════════════════════════════════════════
        print("=" * 70)
        print("CATEGORY 4: STATUS INTERPRETATION")
        print("=" * 70)

        interpretation_tests = [
            (
                "what does 'In WhereUsed with parent' status mean",
                ["where", "used", "parent", "assembly", "component"],
                "WhereUsed interpretation",
            ),
            (
                "what does 'NOT eligible for scrap - Bin Location-[SHOW]' mean",
                ["show", "bin", "location", "display", "not eligible"],
                "Bin Location SHOW interpretation",
            ),
            (
                "what does 'Component Request - Please review Logid' mean",
                ["component", "request", "log", "review"],
                "Component Request interpretation",
            ),
            (
                "what does 'REPAIR USAGE- Need Further review' mean",
                ["repair", "review", "usage"],
                "Repair Usage interpretation",
            ),
        ]

        for query, expected_keywords, label in interpretation_tests:
            conv_id = f"interp-{label.replace(' ', '-')}-{int(time.time())}"
            resp = await ask(session, query, conv_id)
            text = resp.get("reply", "").lower()
            matched = [kw for kw in expected_keywords if kw in text]
            miss_rate = 1 - len(matched) / len(expected_keywords)
            
            status = "PASS" if miss_rate < 0.4 else ("PARTIAL" if miss_rate < 0.7 else "FAIL")
            results.append({
                "category": "INTERPRETATION",
                "label": label,
                "query": query,
                "expected": expected_keywords,
                "got": matched,
                "status": status,
                "reply_snippet": resp.get("reply", "")[:200],
            })
            print(f"  [{status}] {label}: matched {len(matched)}/{len(expected_keywords)} keywords")
            print(f"         Reply: {resp.get('reply', '')[:150]}")
            print()
            await asyncio.sleep(3)

        # ══════════════════════════════════════════════════════════
        # TEST CATEGORY 5: HALLUCINATION / CONTRADICTION TESTS
        # Ask about a fake part, ask contradictory follow-ups
        # ══════════════════════════════════════════════════════════
        print("=" * 70)
        print("CATEGORY 5: HALLUCINATION & SAFETY")
        print("=" * 70)

        halluc_conv = f"halluc-{int(time.time())}"

        # Test 5a: Fake part number
        resp = await ask(session, "what is the status of part 99-9999-99", halluc_conv)
        text = resp.get("reply", "").lower()
        says_not_found = ("not found" in text or "no record" in text or 
                         "no data" in text or "does not" in text or 
                         "couldn't find" in text or "no results" in text)
        status = "PASS" if says_not_found else "FAIL"
        results.append({
            "category": "HALLUCINATION",
            "label": "Fake part 99-9999-99",
            "query": "what is the status of part 99-9999-99",
            "expected": "Not found",
            "got": text[:200],
            "status": status,
            "reply_snippet": resp.get("reply", "")[:200],
        })
        print(f"  [{status}] Fake part 99-9999-99 — should say not found")
        print(f"         Reply: {resp.get('reply', '')[:150]}")
        print()
        await asyncio.sleep(3)

        # Test 5b: Ask about part with leading question (try to trick LLM)
        trick_conv = f"trick-{int(time.time())}"
        # 60-2632-11 is NOT eligible (Bin Stock), but we'll ask as if it IS eligible
        resp = await ask(session, 
            "I was told part 60-2632-11 is eligible to be scrapped, can you confirm that",
            trick_conv)
        text = resp.get("reply", "").lower()
        says_not_eligible = "not eligible" in text
        says_eligible_wrong = "eligible" in text and "not" not in text.split("eligible")[0][-30:]
        
        if says_not_eligible:
            status = "PASS"  # Correctly contradicts the false premise
        elif says_eligible_wrong:
            status = "FAIL"  # Went along with the false premise
        else:
            status = "UNCLEAR"
        
        results.append({
            "category": "HALLUCINATION",
            "label": "Leading question - 60-2632-11 (actually Bin Stock)",
            "query": "I was told part 60-2632-11 is eligible to be scrapped, can you confirm",
            "expected": "Should say NOT eligible - Bin Stock",
            "got": text[:200],
            "status": status,
            "reply_snippet": resp.get("reply", "")[:200],
        })
        print(f"  [{status}] Leading question (60-2632-11 is actually NOT eligible)")
        print(f"         Reply: {resp.get('reply', '')[:150]}")
        print()
        await asyncio.sleep(3)

        # Test 5c: Ask about part with wrong status claim
        trick_conv2 = f"trick2-{int(time.time())}"
        # 34-6669-03 has "Product USAGE" status, ask if it has open sales order
        resp = await ask(session, 
            "does part 34-6669-03 have an open sales order",
            trick_conv2)
        text = resp.get("reply", "").lower()
        says_no = ("no" in text and "open sales" not in text) or "product usage" in text or "does not" in text
        says_yes_wrong = "open sales order" in text and "yes" in text
        
        if "product usage" in text:
            status = "PASS"  # Correctly identifies actual status
        elif says_yes_wrong:
            status = "FAIL"
        else:
            status = "UNCLEAR"
        
        results.append({
            "category": "HALLUCINATION",
            "label": "Wrong status claim - 34-6669-03 (actually Product USAGE)",
            "query": "does part 34-6669-03 have an open sales order",
            "expected": "Should say no — status is Product USAGE",
            "got": text[:200],
            "status": status,
            "reply_snippet": resp.get("reply", "")[:200],
        })
        print(f"  [{status}] Wrong status claim (34-6669-03 is actually Product USAGE)")
        print(f"         Reply: {resp.get('reply', '')[:150]}")
        print()

        # ══════════════════════════════════════════════════════════
        # TEST CATEGORY 6: MULTI-PART QUERIES
        # Ask about multiple parts at once
        # ══════════════════════════════════════════════════════════
        print("=" * 70)
        print("CATEGORY 6: MULTI-PART QUERIES")
        print("=" * 70)

        multi_conv = f"multi-{int(time.time())}"
        # Mix of eligible and not-eligible
        resp = await ask(session,
            "what is the status of parts 91-8430-02LF, 60-2632-11, and 34-6669-03",
            multi_conv)
        text = resp.get("reply", "").lower()
        
        # Check each part mentioned correctly
        checks = {
            "91-8430-02LF": "eligible" in text,
            "60-2632-11": "not eligible" in text or "bin stock" in text,
            "34-6669-03": "product usage" in text or "usage" in text,
        }
        all_correct = all(checks.values())
        some_correct = any(checks.values())
        
        status = "PASS" if all_correct else ("PARTIAL" if some_correct else "FAIL")
        results.append({
            "category": "MULTI_PART",
            "label": "3 parts with different statuses",
            "query": "what is the status of parts 91-8430-02LF, 60-2632-11, and 34-6669-03",
            "expected": "91-8430-02LF=eligible, 60-2632-11=not eligible, 34-6669-03=product usage",
            "got": {k: v for k, v in checks.items()},
            "status": status,
            "reply_snippet": resp.get("reply", "")[:300],
        })
        print(f"  [{status}] Multi-part: {checks}")
        print(f"         Reply: {resp.get('reply', '')[:200]}")
        print()

    # ══════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════
    print()
    print("=" * 70)
    print("ACCURACY TEST SUMMARY")
    print("=" * 70)
    
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"PASS": 0, "FAIL": 0, "PARTIAL": 0, "CLOSE": 0, "UNCLEAR": 0}
        categories[cat][r["status"]] += 1

    total_pass = sum(r["status"] == "PASS" for r in results)
    total_fail = sum(r["status"] == "FAIL" for r in results)
    total_partial = sum(r["status"] in ("PARTIAL", "CLOSE", "UNCLEAR") for r in results)
    total = len(results)

    for cat, counts in categories.items():
        total_cat = sum(counts.values())
        print(f"\n  {cat} ({total_cat} tests):")
        for s, c in counts.items():
            if c > 0:
                print(f"    {s}: {c}")

    print(f"\n  OVERALL: {total_pass}/{total} PASS, {total_fail} FAIL, {total_partial} PARTIAL/CLOSE/UNCLEAR")
    print(f"  Accuracy: {total_pass/total*100:.1f}%")

    # Print all failures in detail
    failures = [r for r in results if r["status"] in ("FAIL", "UNCLEAR")]
    if failures:
        print()
        print("=" * 70)
        print("DETAILED FAILURES")
        print("=" * 70)
        for r in failures:
            print(f"\n  [{r['status']}] {r['category']}: {r['label']}")
            print(f"  Query: {r['query']}")
            print(f"  Expected: {r['expected']}")
            print(f"  Reply: {r['reply_snippet']}")

    # Save full results to JSON
    with open("scripts/helpers/accuracy_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Full results saved to scripts/helpers/accuracy_results.json")


if __name__ == "__main__":
    asyncio.run(run_tests())



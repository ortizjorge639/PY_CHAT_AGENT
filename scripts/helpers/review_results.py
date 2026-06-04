import json
with open("scripts/helpers/accuracy_results.json") as f:
    results = json.load(f)
for r in results:
    if r["status"] in ("PARTIAL", "FAIL", "CLOSE", "UNCLEAR"):
        cat = r["category"]
        label = r["label"]
        expected = r["expected"]
        reply = r["reply_snippet"]
        print(f"[{r['status']}] {cat}: {label}")
        print(f"  Expected: {expected}")
        print(f"  Reply: {reply}")
        print()

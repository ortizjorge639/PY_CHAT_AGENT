---
description: "Fix double-spaced / extra blank lines in Python files"
mode: "agent"
---

The user has a file (or files) with a "double newline" bug — every line is separated by an extra blank line.

Run the fix script:

```
python scripts/fix_newlines.py ${input:target:File or directory to fix (e.g. agent/kernel_customer.py or .)}
```

After running, confirm how many files were fixed and verify there are no syntax errors in the changed files.

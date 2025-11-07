# Regular Expressions - re module

**Official Documentation**: https://docs.python.org/3/library/re.html

Search and extract text patterns using Python's built-in `re` module in NOVA workflows.

---

## Basic Pattern Matching

```python
import re

# Find first match
match = re.search(r'c', 'abcdef')
if match:
    print(match.group())  # Output: 'c'

# Match at string start only
match = re.match(r'a', 'abcdef')  # Matches
match = re.match(r'c', 'abcdef')  # None - doesn't match at start
```

---

## Extract All Matches (findall)

```python
import re

# Find all words ending in 'ly'
text = "He was carefully disguised but captured quickly by police."
adverbs = re.findall(r'\w+ly\b', text)
# Result: ['carefully', 'quickly']

# Extract all numbers (integers and decimals)
text = "The total is 24.16 euros and tax is 3.20"
numbers = re.findall(r'\d+(?:\.\d+)?', text)
# Result: ['24.16', '3.20']

# Extract with groups (returns tuples)
pairs = re.findall(r'(\w+)=(\d+)', 'width=20 and height=10')
# Result: [('width', '20'), ('height', '10')]
```

---

## Common Patterns for NOVA

### Currency Amounts

Extract euro amounts from invoices:

```python
import re

pdf_text = "Total: 150.50€ plus tax of 31.60 EUR"

# Pattern 1: Amount followed by € symbol
pattern1 = r'(\d+[.,]\d{2})\s*€'
matches = re.findall(pattern1, pdf_text)
# Result: ['150.50']

# Pattern 2: Amount followed by EUR
pattern2 = r'(\d+[.,]\d{2})\s*EUR'
matches = re.findall(pattern2, pdf_text)
# Result: ['31.60']

# Pattern 3: Combined pattern
pattern = r'(?:total|amount|price)[:\s]+€?\s*(\d+[.,]\d{2})'
matches = re.findall(pattern, pdf_text, re.IGNORECASE)

# Convert to float (replace comma with dot)
if matches:
    amount_str = matches[0].replace(',', '.')
    amount = float(amount_str)
```

### Email Addresses

```python
import re

text = "Contact us at support@example.com or sales@company.org"

email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
emails = re.findall(email_pattern, text)
# Result: ['support@example.com', 'sales@company.org']
```

### Dates

```python
import re

text = "Invoice date: 2025-11-07 and due date 07/11/2025"

# ISO format (YYYY-MM-DD)
iso_dates = re.findall(r'\d{4}-\d{2}-\d{2}', text)
# Result: ['2025-11-07']

# DD/MM/YYYY format
slash_dates = re.findall(r'\d{2}/\d{2}/\d{4}', text)
# Result: ['07/11/2025']
```

---

## Match Objects and Groups

```python
import re

text = "Isaac Newton, physicist"
match = re.search(r'(\w+) (\w+)', text)

if match:
    match.group(0)      # Entire match: 'Isaac Newton'
    match.group(1)      # First group: 'Isaac'
    match.group(2)      # Second group: 'Newton'
    match.groups()      # All groups: ('Isaac', 'Newton')
    match.start()       # Start position
    match.end()         # End position
```

---

## Case-Insensitive Matching

```python
import re

# Case-insensitive flag
matches = re.findall(r'total', text, re.IGNORECASE)
# Matches: 'Total', 'TOTAL', 'total'

# Alternative: inline flag
matches = re.findall(r'(?i)total', text)
```

---

## Word Boundaries

```python
import re

# Match complete words only
text = "attempt at atlas"

# Without word boundary
re.findall(r'at', text)  # ['at', 'at', 'at'] - matches inside words

# With word boundary
re.findall(r'\bat\b', text)  # ['at'] - matches complete word only
```

---

## Complete Example: Extract Invoice Amount

```python
import re
import json

try:
    # Get text from context
    pdf_text = context.get('pdf_text', '')

    if not pdf_text:
        raise ValueError("No PDF text available")

    # Try multiple amount patterns
    amount_patterns = [
        r'total[:\s]+€?\s*(\d+[.,]\d{2})',     # "Total: €150.50"
        r'amount[:\s]+€?\s*(\d+[.,]\d{2})',    # "Amount: 150.50"
        r'€\s*(\d+[.,]\d{2})',                  # "€150.50"
        r'(\d+[.,]\d{2})\s*EUR',                # "150.50 EUR"
    ]

    amount_found = None

    for pattern in amount_patterns:
        matches = re.findall(pattern, pdf_text, re.IGNORECASE)
        if matches:
            # Take last match (usually the total)
            amount_str = matches[-1].replace(',', '.')
            amount_found = float(amount_str)
            break

    print(json.dumps({
        "status": "success",
        "context_updates": {
            "total_amount": amount_found or 0.0,
            "amount_found": amount_found is not None
        }
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "message": f"Regex error: {str(e)}"
    }))
```

---

## Compile Patterns for Reuse

For better performance when using the same pattern multiple times:

```python
import re

# Compile once
pattern = re.compile(r'\d+[.,]\d{2}')

# Reuse multiple times
result1 = pattern.search(text1)
result2 = pattern.findall(text2)
result3 = pattern.match(text3)
```

---

## Key Points

- **Use raw strings**: Always use `r"pattern"` to avoid escaping backslashes
- **Word boundaries**: Use `\b` to match complete words only
- **Case-insensitive**: Use `re.IGNORECASE` flag for flexible matching
- **Groups**: Use `()` to capture specific parts of the match
- **Non-greedy**: Use `?` after quantifiers for minimal matching (`.*?` instead of `.*`)
- **Test patterns**: Use https://regex101.com/ to test and debug patterns

---

**Integration**: Regular Expressions (re module)
**Use with**: Text extraction, invoice processing, data validation
**Official Docs**: https://docs.python.org/3/library/re.html

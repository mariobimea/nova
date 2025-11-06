# PostgreSQL - Database Operations

Connect to PostgreSQL and execute queries using `psycopg2` in NOVA workflows.

---

## Overview

**Capabilities**: Connect to PostgreSQL, execute SELECT/INSERT/UPDATE/DELETE, parameterized queries, transactions, binary data (BYTEA).

**Use cases**: Save invoices to database, query records, update workflow status, store PDF attachments.

---

## Connection

```python
import json
from src.models.credentials import get_database_connection

# Get connection to client database
conn = get_database_connection(context['client_slug'])
cursor = conn.cursor()

# Always close when done
cursor.close()
conn.close()
```

---

## SELECT Query

```python
import json
from src.models.credentials import get_database_connection

conn = get_database_connection(context['client_slug'])
cursor = conn.cursor()

# Execute SELECT
cursor.execute("SELECT id, email_from, total_amount FROM invoices LIMIT 10")
rows = cursor.fetchall()

# Process results
invoices = []
for row in rows:
    invoices.append({
        'id': row[0],
        'email_from': row[1],
        'total_amount': float(row[2])
    })

cursor.close()
conn.close()

print(json.dumps({
    "status": "success",
    "context_updates": {"invoices": invoices}
}))
```

---

## Parameterized Queries (CRITICAL)

**ALWAYS use `%s` placeholders** to prevent SQL injection.

```python
# ✅ CORRECT - Safe
email = "john@example.com"
cursor.execute("SELECT * FROM invoices WHERE email_from = %s", (email,))

# Multiple parameters
cursor.execute(
    "SELECT * FROM invoices WHERE email_from = %s AND total_amount > %s",
    (email, 1000)
)

# ❌ WRONG - SQL Injection vulnerability
cursor.execute(f"SELECT * FROM invoices WHERE email_from = '{email}'")  # NEVER DO THIS
```

---

## INSERT Query

```python
import json
from src.models.credentials import get_database_connection

conn = get_database_connection(context['client_slug'])
cursor = conn.cursor()

# INSERT with RETURNING to get auto-generated ID
cursor.execute("""
    INSERT INTO invoices (email_from, total_amount, currency)
    VALUES (%s, %s, %s)
    RETURNING id
""", (
    context['email_from'],
    context['total_amount'],
    'EUR'
))

invoice_id = cursor.fetchone()[0]

# CRITICAL: Commit transaction
conn.commit()

cursor.close()
conn.close()

print(json.dumps({
    "status": "success",
    "context_updates": {"invoice_id": invoice_id}
}))
```

---

## UPDATE Query

```python
cursor.execute("""
    UPDATE invoices
    SET total_amount = %s
    WHERE id = %s
""", (context['new_amount'], context['invoice_id']))

rows_updated = cursor.rowcount
conn.commit()
```

---

## Transactions

Multiple operations atomically.

```python
try:
    conn = get_database_connection(context['client_slug'])
    cursor = conn.cursor()

    # Operation 1
    cursor.execute("""
        INSERT INTO invoices (email_from, total_amount)
        VALUES (%s, %s)
        RETURNING id
    """, (context['email_from'], context['total_amount']))
    invoice_id = cursor.fetchone()[0]

    # Operation 2
    cursor.execute("""
        UPDATE accounts SET balance = balance - %s WHERE id = %s
    """, (context['total_amount'], context['account_id']))

    # Commit both atomically
    conn.commit()

    print(json.dumps({
        "status": "success",
        "context_updates": {"invoice_id": invoice_id}
    }))

except Exception as e:
    # Rollback all changes if any operation fails
    conn.rollback()
    print(json.dumps({"status": "error", "message": str(e)}))
finally:
    cursor.close()
    conn.close()
```

---

## Binary Data (PDFs)

```python
# Insert PDF as binary
pdf_data = context['pdf_data']  # bytes

cursor.execute("""
    INSERT INTO invoices (pdf_filename, pdf_content, pdf_size_bytes)
    VALUES (%s, %s, %s)
    RETURNING id
""", (
    context['pdf_filename'],
    pdf_data,  # psycopg2 handles bytes automatically
    len(pdf_data)
))

conn.commit()
```

---

## Complete Example

```python
import psycopg2
import json
from src.models.credentials import get_database_connection

try:
    # Connect
    conn = get_database_connection(context['client_slug'])
    cursor = conn.cursor()

    # Insert invoice
    cursor.execute("""
        INSERT INTO invoices (
            email_from,
            email_subject,
            pdf_filename,
            pdf_content,
            total_amount,
            currency
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        context['email_from'],
        context['email_subject'],
        context['pdf_filename'],
        context['pdf_data'],
        context['total_amount'],
        'EUR'
    ))

    invoice_id = cursor.fetchone()[0]
    conn.commit()

    cursor.close()
    conn.close()

    print(json.dumps({
        "status": "success",
        "context_updates": {"invoice_id": invoice_id}
    }))

except psycopg2.IntegrityError as e:
    conn.rollback()
    print(json.dumps({"status": "error", "message": f"Constraint violation: {str(e)}"}))
except Exception as e:
    if conn:
        conn.rollback()
    print(json.dumps({"status": "error", "message": str(e)}))
finally:
    if cursor:
        cursor.close()
    if conn:
        conn.close()
```

---

## Key Points

- **Parameterized queries**: ALWAYS use `%s` placeholders (prevents SQL injection)
- **Commit transactions**: Call `conn.commit()` after INSERT/UPDATE/DELETE
- **Rollback on error**: Call `conn.rollback()` in exception handler
- **Close resources**: Always close cursor and connection
- **Single-element tuple**: Use `(value,)` with comma for one parameter
- **Check fetchone()**: May return `None` if no results

---

**Integration**: PostgreSQL (psycopg2)
**Use with**: Invoice storage, data persistence, workflow state management

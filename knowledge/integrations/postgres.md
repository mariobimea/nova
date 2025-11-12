# PostgreSQL - psycopg2

**Official Documentation**: https://github.com/yugabyte/psycopg2

Connect to PostgreSQL and execute queries using `psycopg2` in NOVA workflows.

---

## Basic Connection and Usage

```python
import psycopg2

# Connect to an existing database
conn = psycopg2.connect("dbname=test user=postgres")

# Open a cursor to perform database operations
cur = conn.cursor()

# Execute a command: this creates a new table
cur.execute("CREATE TABLE test (id serial PRIMARY KEY, num integer, data varchar);")

# Pass data to fill query placeholders (prevents SQL injection)
cur.execute("INSERT INTO test (num, data) VALUES (%s, %s)", (100, "abc'def"))

# Query the database and obtain data as Python objects
cur.execute("SELECT * FROM test;")
cur.fetchone()

# Make the changes to the database persistent
conn.commit()

# Close communication with the database
cur.close()
conn.close()
```

---

## INSERT with RETURNING (Get Inserted ID)

**CRITICAL**: After INSERT, you MUST capture the returned ID using `fetchone()`:

```python
import psycopg2
import json

# Connect
conn = psycopg2.connect(
    host=context['db_host'],
    port=context['db_port'],
    database=context['db_name'],
    user=context['db_user'],
    password=context['db_password']
)

cursor = conn.cursor()

# INSERT with RETURNING
cursor.execute("""
    INSERT INTO invoices (
        email_from, email_subject, total_amount, currency
    ) VALUES (%s, %s, %s, %s)
    RETURNING id
""", (
    context['email_from'],
    context['email_subject'],
    context['total_amount'],
    'EUR'
))

# ⚠️ MUST fetch the returned ID BEFORE commit
inserted_id = cursor.fetchone()[0]

conn.commit()
cursor.close()
conn.close()

# Now you can use inserted_id in the output
print(json.dumps({
    "status": "success",
    "context_updates": {"invoice_id": inserted_id},
    "message": f"Invoice {inserted_id} saved successfully"
}))
```

**Common Mistake - DO NOT do this**:

```python
# ❌ WRONG - inserted_id is never defined!
cursor.execute("""
    INSERT INTO invoices (...) VALUES (...)
    RETURNING id
""", (...))

conn.commit()

# This will fail: NameError: name 'inserted_id' is not defined
print(json.dumps({"message": inserted_id}))
```

**Correct order**:
1. Execute INSERT with RETURNING
2. **Fetch the returned ID**: `inserted_id = cursor.fetchone()[0]`
3. Commit transaction
4. Use `inserted_id` in output

---

## Connection with Context Manager

Use `with` statement for automatic transaction management:

```python
import psycopg2

DSN = "your_database_connection_string"

with psycopg2.connect(DSN) as conn:
    with conn.cursor() as curs:
        curs.execute("SELECT 1")
        # Transaction commits automatically if no exception
        # Rolls back automatically if exception occurs

# Connection stays open after 'with' block - close it manually
conn.close()
```

---

## Parameterized Queries (CRITICAL)

**ALWAYS use `%s` placeholders** to prevent SQL injection:

```python
# ✅ CORRECT - Safe from SQL injection
email = "john@example.com"
cur.execute("SELECT * FROM invoices WHERE email_from = %s", (email,))

# Multiple parameters
cur.execute(
    "SELECT * FROM invoices WHERE email_from = %s AND total_amount > %s",
    (email, 1000)
)

# ❌ WRONG - SQL Injection vulnerability
cur.execute(f"SELECT * FROM invoices WHERE email_from = '{email}'")  # NEVER DO THIS
```

**Named parameters** for better readability:

```python
import datetime

cur.execute("""
    INSERT INTO some_table (an_int, a_date, another_date, a_string)
    VALUES (%(int)s, %(date)s, %(date)s, %(str)s);
    """,
    {'int': 10, 'str': "O'Reilly", 'date': datetime.date(2005, 11, 18)})
```

**Single parameter tuple** (note the comma):

```python
# Single parameter - requires trailing comma
cur.execute("SELECT * FROM invoices WHERE id = %s", (42,))
```

---

## INSERT with RETURNING

Get auto-generated ID after insert:

```python
import psycopg2
import json

conn = psycopg2.connect("dbname=mydb user=postgres")
cur = conn.cursor()

# INSERT with RETURNING to get auto-generated ID
cur.execute("""
    INSERT INTO invoices (email_from, total_amount, currency)
    VALUES (%s, %s, %s)
    RETURNING id
""", (
    "customer@example.com",
    150.00,
    'EUR'
))

invoice_id = cur.fetchone()[0]

# CRITICAL: Commit transaction
conn.commit()

cur.close()
conn.close()

print(json.dumps({
    "status": "success",
    "context_updates": {"invoice_id": invoice_id}
}))
```

---

## UPDATE Query

```python
cur.execute("""
    UPDATE invoices
    SET total_amount = %s
    WHERE id = %s
""", (200.50, 42))

rows_updated = cur.rowcount  # Number of rows affected
conn.commit()
```

---

## SELECT and Fetch Results

```python
cur.execute("SELECT id, email_from, total_amount FROM invoices LIMIT 10")
rows = cur.fetchall()

# Process results
invoices = []
for row in rows:
    invoices.append({
        'id': row[0],
        'email_from': row[1],
        'total_amount': float(row[2])
    })

print(json.dumps({
    "status": "success",
    "context_updates": {"invoices": invoices}
}))
```

---

## Transactions (Atomic Operations)

Multiple operations that succeed or fail together:

```python
try:
    conn = psycopg2.connect("dbname=mydb")
    cur = conn.cursor()

    # Operation 1
    cur.execute("""
        INSERT INTO invoices (email_from, total_amount)
        VALUES (%s, %s)
        RETURNING id
    """, ("customer@example.com", 150.00))
    invoice_id = cur.fetchone()[0]

    # Operation 2
    cur.execute("""
        UPDATE accounts SET balance = balance - %s WHERE id = %s
    """, (150.00, 10))

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
    cur.close()
    conn.close()
```

---

## Binary Data (BYTEA)

Insert binary data (e.g., PDFs) using `psycopg2.Binary`:

```python
import psycopg2

# Read binary file
with open('picture.png', 'rb') as f:
    mypic = f.read()

cur.execute("INSERT INTO blobs (file) VALUES (%s)",
    (psycopg2.Binary(mypic),))

conn.commit()
```

**In NOVA workflows** (PDF attachments):

```python
import base64
import psycopg2

# Get PDF data from context (base64 string in NOVA)
pdf_data_base64 = context['pdf_data']
pdf_data = base64.b64decode(pdf_data_base64)

cur.execute("""
    INSERT INTO invoices (pdf_filename, pdf_content, pdf_size_bytes)
    VALUES (%s, %s, %s)
    RETURNING id
""", (
    context['pdf_filename'],
    psycopg2.Binary(pdf_data),  # Handles bytes automatically
    len(pdf_data)
))

invoice_id = cur.fetchone()[0]
conn.commit()
```

---

## Complete Example: Save Invoice to Database

```python
import psycopg2
import json
import base64

try:
    # Connect
    conn = psycopg2.connect(
        host=context['db_host'],
        port=context['db_port'],
        dbname=context['db_name'],
        user=context['db_user'],
        password=context['db_password']
    )
    cur = conn.cursor()

    # Decode PDF data from base64
    pdf_data = base64.b64decode(context['pdf_data'])

    # Insert invoice
    cur.execute("""
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
        psycopg2.Binary(pdf_data),
        context['total_amount'],
        'EUR'
    ))

    invoice_id = cur.fetchone()[0]
    conn.commit()

    cur.close()
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
    if cur:
        cur.close()
    if conn:
        conn.close()
```

---

## Execute Batch (Multiple Inserts)

Efficiently insert multiple rows:

```python
from psycopg2.extras import execute_batch

# List of parameter tuples
params_list = [
    ("customer1@example.com", 100.0),
    ("customer2@example.com", 200.0),
    ("customer3@example.com", 150.0)
]

execute_batch(cur,
    "INSERT INTO invoices (email_from, total_amount) VALUES (%s, %s)",
    params_list)

conn.commit()
```

---

## Commit and Rollback

```python
# Commit transaction (save changes)
conn.commit()

# Rollback transaction (discard changes)
conn.rollback()

# Note: Closing connection without commit = implicit rollback
```

---

## Autocommit Mode

For commands that cannot run in a transaction (e.g., `CREATE DATABASE`, `VACUUM`):

```python
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur.execute("CREATE DATABASE newdb")
```

---

## Key Points

- **Parameterized queries**: ALWAYS use `%s` placeholders (prevents SQL injection)
- **Commit transactions**: Call `conn.commit()` after INSERT/UPDATE/DELETE
- **Rollback on error**: Call `conn.rollback()` in exception handler
- **Close resources**: Always close cursor and connection (or use `with` statement)
- **Single-element tuple**: Use `(value,)` with comma for one parameter
- **Check fetchone()**: May return `None` if no results
- **Binary data**: Use `psycopg2.Binary()` for BYTEA columns
- **Connection strings**: Can use `psycopg2.connect(host=..., port=..., dbname=...)` or DSN string

---

**Integration**: PostgreSQL (psycopg2)
**Use with**: Invoice storage, data persistence, workflow state management
**Official Docs**: https://www.psycopg.org/docs/

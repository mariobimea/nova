# IMAP - Email Reading (imaplib)

**Official Documentation**: https://docs.python.org/3/library/imaplib.html

Read emails via IMAP using Python's built-in `imaplib` module in NOVA workflows.

---

## Basic Connection (IMAP4_SSL)

Connect to IMAP server with SSL encryption (port 993):

```python
import imaplib
import getpass

# Connect with SSL
mail = imaplib.IMAP4_SSL(host='imap.gmail.com')

# Login
mail.login('user@example.com', 'password')

# Select mailbox (default is INBOX)
mail.select()

# Always logout when done
mail.logout()
```

---

## Search for Emails

Search emails using IMAP search criteria:

```python
import imaplib

mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login('user@example.com', 'password')
mail.select()

# Search for ALL emails
typ, data = mail.search(None, 'ALL')
email_ids = data[0].split()  # Returns list of email IDs

# Search for UNSEEN (unread) emails
typ, data = mail.search(None, 'UNSEEN')

# Search by sender
typ, data = mail.search(None, 'FROM', '"sender@example.com"')

# Alternative syntax with parentheses
typ, data = mail.search(None, '(FROM "sender@example.com")')

# Search by subject
typ, data = mail.search(None, 'SUBJECT', '"Invoice"')

mail.close()
mail.logout()
```

---

## Fetch Email Content

Retrieve email messages:

```python
import imaplib
import email

mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login('user@example.com', 'password')
mail.select()

# Get all email IDs
typ, data = mail.search(None, 'ALL')
email_ids = data[0].split()

# Fetch first email
first_id = email_ids[0]
typ, msg_data = mail.fetch(first_id, '(RFC822)')

# Parse email message
raw_email = msg_data[0][1]
msg = email.message_from_bytes(raw_email)

# Access email headers
email_from = msg.get('From')
email_subject = msg.get('Subject')
email_date = msg.get('Date')

print(f"From: {email_from}")
print(f"Subject: {email_subject}")
print(f"Date: {email_date}")

mail.close()
mail.logout()
```

---

## Process Email Attachments

Extract PDF attachments from emails:

```python
import imaplib
import email
import base64

mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login('user@example.com', 'password')
mail.select()

# Search for unread emails
typ, data = mail.search(None, 'UNSEEN')
email_ids = data[0].split()

if email_ids:
    # Get first unread email
    email_id = email_ids[0]
    typ, msg_data = mail.fetch(email_id, '(RFC822)')
    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    # Iterate through email parts
    for part in msg.walk():
        # Check if part is PDF attachment
        if part.get_content_type() == 'application/pdf':
            filename = part.get_filename()
            pdf_data_bytes = part.get_payload(decode=True)

            # Convert to base64 for NOVA storage
            pdf_data_base64 = base64.b64encode(pdf_data_bytes).decode('utf-8')

            print(f"Found PDF: {filename}")
            print(f"Size: {len(pdf_data_bytes)} bytes")

mail.close()
mail.logout()
```

---

## Mark Email as Read

Change email flags:

```python
import imaplib

mail = imaplib.IMAP4_SSL('imap.gmail.com')
mail.login('user@example.com', 'password')
mail.select()

# Mark email as read (seen)
email_id = b'123'
mail.store(email_id, '+FLAGS', '\\Seen')

# Mark email as unread
mail.store(email_id, '-FLAGS', '\\Seen')

mail.close()
mail.logout()
```

---

## Complete Example: Read Unread Emails with PDF Attachments

```python
import imaplib
import email
import base64
import json

try:
    # Read credentials from context
    email_user = context.get("email_user")
    email_password = context.get("email_password")
    sender_whitelist = context.get("sender_whitelist")

    # Connect to IMAP server
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email_user, email_password)
    mail.select("inbox")

    # Search for unread emails from specific sender
    search_criteria = f'(UNSEEN FROM "{sender_whitelist}")'
    status, messages = mail.search(None, search_criteria)
    email_ids = messages[0].split()

    if not email_ids:
        raise ValueError("No unread emails found from the specified sender.")

    # Fetch the first unread email
    latest_email_id = email_ids[0]
    status, msg_data = mail.fetch(latest_email_id, '(RFC822)')
    msg = email.message_from_bytes(msg_data[0][1])

    # Extract email metadata
    email_from = msg.get("From", "")
    email_subject = msg.get("Subject", "")
    email_date = msg.get("Date", "")

    # Initialize PDF variables
    has_pdf = False
    pdf_filename = None
    pdf_data = None

    # Check for PDF attachments
    for part in msg.walk():
        if part.get_content_type() == "application/pdf":
            has_pdf = True
            pdf_filename = part.get_filename()
            pdf_data = base64.b64encode(part.get_payload(decode=True)).decode('utf-8')
            break

    # Mark the email as read
    mail.store(latest_email_id, '+FLAGS', '\\Seen')

    mail.close()
    mail.logout()

    # Return results
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "email_from": email_from,
            "email_subject": email_subject,
            "email_date": email_date,
            "has_pdf": has_pdf,
            "pdf_filename": pdf_filename if has_pdf else None,
            "pdf_data": pdf_data if has_pdf else None
        },
        "message": "Email processed successfully"
    }))

except imaplib.IMAP4.error as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"IMAP error: {str(e)}"
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"Unexpected error: {str(e)}"
    }))
```

---

## Response Format

IMAP commands return tuples: `(type, [data, ...])`

- **type**: Usually `'OK'` or `'NO'`
- **data**: List of bytes or tuples containing message content

Example:
```python
typ, data = mail.search(None, 'ALL')
# typ = 'OK'
# data = [b'1 2 3 4 5']  # Email IDs
```

---

## Key Points

- **Always logout**: Call `mail.logout()` to close connection properly
- **Select mailbox**: Call `mail.select()` before searching (defaults to INBOX)
- **Email IDs are bytes**: Convert with `.split()` to get list
- **Search syntax**: Use proper IMAP search syntax (case-insensitive)
- **Mark as read**: Use `mail.store(email_id, '+FLAGS', '\\Seen')`
- **PDF attachments**: Check `content_type == 'application/pdf'` and use `get_payload(decode=True)`
- **Base64 encoding**: Store PDF data as base64 string in NOVA context

---

**Integration**: IMAP Email Reading (imaplib + email)
**Use with**: Invoice processing, email automation, attachment extraction
**Official Docs**: https://docs.python.org/3/library/imaplib.html

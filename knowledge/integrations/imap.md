# IMAP - Reading Emails

Read emails using Python's `imaplib` library in NOVA workflows.

---

## Overview

**Capabilities**: Connect to email servers, search/filter emails, read headers, download attachments, manage email state, validate sender whitelists.

**Use cases**: Process invoices via email, download PDF attachments, automated email filtering.

---

## Connection

```python
import imaplib
import json
from src.models.credentials import get_email_credentials

# Get credentials from NOVA
email_creds = get_email_credentials(context['client_slug'])

# Connect to IMAP server (SSL)
mail = imaplib.IMAP4_SSL(email_creds.imap_host, email_creds.imap_port)
mail.login(email_creds.email_user, email_creds.email_password)
mail.select('INBOX')
```

---

## Search Emails

```python
# Unread emails only
status, messages = mail.search(None, 'UNSEEN')

# From specific sender
status, messages = mail.search(None, 'FROM', '"sender@example.com"')

# By subject
status, messages = mail.search(None, 'SUBJECT', '"Invoice"')

# Combined criteria
status, messages = mail.search(None, '(UNSEEN FROM "accounting@company.com")')

# Process results
email_ids = messages[0].split()
if not email_ids:
    # No emails found
    pass
```

---

## Read Email

```python
import email

# Fetch email by ID
email_id = email_ids[0]
status, msg_data = mail.fetch(email_id, '(RFC822)')
msg = email.message_from_bytes(msg_data[0][1])

# Extract headers
from_header = msg.get('From', '')
subject = msg.get('Subject', '')
date = msg.get('Date', '')
```

---

## Download Attachments

```python
# Find PDF attachments
pdf_attachments = []

for part in msg.walk():
    if part.get_content_maintype() == 'multipart':
        continue
    if part.get('Content-Disposition') is None:
        continue

    filename = part.get_filename()
    if filename and filename.lower().endswith('.pdf'):
        pdf_data = part.get_payload(decode=True)
        pdf_attachments.append({
            'filename': filename,
            'data': pdf_data,
            'size': len(pdf_data)
        })

if pdf_attachments:
    pdf = pdf_attachments[0]
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "has_pdf": True,
            "pdf_filename": pdf['filename'],
            "pdf_data": pdf['data']
        }
    }))
```

---

## Manage Email State

```python
# Mark as read
mail.store(email_id, '+FLAGS', '\\Seen')

# Delete email
mail.store(email_id, '+FLAGS', '\\Deleted')
mail.expunge()

# Always logout when done
mail.logout()
```

---

## Whitelist Validation

```python
# Extract sender email
from_header = msg.get('From', '')
sender_email = from_header.split('<')[-1].strip('>')

# Check against whitelist
if email_creds.sender_whitelist:
    passes_whitelist = email_creds.sender_whitelist in sender_email
else:
    passes_whitelist = True
```

---

## Complete Example

```python
import imaplib
import email
import json
from src.models.credentials import get_email_credentials

try:
    # Connect
    email_creds = get_email_credentials(context['client_slug'])
    mail = imaplib.IMAP4_SSL(email_creds.imap_host, email_creds.imap_port)
    mail.login(email_creds.email_user, email_creds.email_password)
    mail.select('INBOX')

    # Search unread
    status, messages = mail.search(None, 'UNSEEN')
    email_ids = messages[0].split()

    if not email_ids:
        print(json.dumps({
            "status": "success",
            "context_updates": {"has_emails": False}
        }))
    else:
        # Read first email
        email_id = email_ids[0]
        status, msg_data = mail.fetch(email_id, '(RFC822)')
        msg = email.message_from_bytes(msg_data[0][1])

        # Extract data
        from_header = msg.get('From', '')
        subject = msg.get('Subject', '')
        sender_email = from_header.split('<')[-1].strip('>')

        # Find PDF
        has_pdf = False
        pdf_data = None
        pdf_filename = None

        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            filename = part.get_filename()
            if filename and filename.lower().endswith('.pdf'):
                has_pdf = True
                pdf_data = part.get_payload(decode=True)
                pdf_filename = filename
                break

        # Mark as read
        mail.store(email_id, '+FLAGS', '\\Seen')

        print(json.dumps({
            "status": "success",
            "context_updates": {
                "email_from": from_header,
                "email_subject": subject,
                "has_pdf": has_pdf,
                "pdf_filename": pdf_filename,
                "pdf_data": pdf_data
            }
        }))

    mail.logout()

except imaplib.IMAP4.error as e:
    print(json.dumps({"status": "error", "message": f"IMAP error: {str(e)}"}))
except Exception as e:
    print(json.dumps({"status": "error", "message": f"Error: {str(e)}"}))
```

---

## Key Points

- **Always logout**: Call `mail.logout()` to close connection
- **Check empty results**: Validate `email_ids` before accessing
- **Validate attachments**: Check `Content-Disposition` before processing
- **Handle errors**: Wrap in try/except for `imaplib.IMAP4.error`

---

**Integration**: IMAP (imaplib + email)
**Use with**: Email processing workflows, invoice automation

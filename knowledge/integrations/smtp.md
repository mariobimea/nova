# SMTP - Sending Emails

Send emails using Python's `smtplib` library in NOVA workflows.

---

## Overview

**Capabilities**: Send plain text/HTML emails, attachments, replies, multiple recipients.

**Use cases**: Send rejection/approval notifications, automated responses, alerts.

---

## Connection

```python
import smtplib
from src.models.credentials import get_email_credentials

# Get credentials from NOVA
email_creds = get_email_credentials(context['client_slug'])

# Connect to SMTP (port 587 with TLS)
smtp = smtplib.SMTP(email_creds.smtp_host, email_creds.smtp_port)
smtp.starttls()  # CRITICAL: Upgrade to TLS before login
smtp.login(email_creds.email_user, email_creds.email_password)

# Always close when done
smtp.quit()
```

---

## Send Simple Text Email

```python
import smtplib
from email.mime.text import MIMEText
from src.models.credentials import get_email_credentials

email_creds = get_email_credentials(context['client_slug'])

# Create message
msg = MIMEText("Hello, this is the email body.")
msg['From'] = email_creds.email_user
msg['To'] = "recipient@example.com"
msg['Subject'] = "Test Email"

# Send
smtp = smtplib.SMTP(email_creds.smtp_host, email_creds.smtp_port)
smtp.starttls()
smtp.login(email_creds.email_user, email_creds.email_password)
smtp.send_message(msg)
smtp.quit()
```

---

## Reply to Email

```python
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

msg = MIMEMultipart()
msg['From'] = email_creds.email_user
msg['To'] = context['email_from']  # Reply to original sender
msg['Subject'] = f"Re: {context['email_subject']}"

body = "Thank you for your email. We have received your message."
msg.attach(MIMEText(body, 'plain'))

smtp.send_message(msg)
```

---

## Send Email with Attachment

```python
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

msg = MIMEMultipart()
msg['From'] = email_creds.email_user
msg['To'] = "recipient@example.com"
msg['Subject'] = "Email with Attachment"

# Body
msg.attach(MIMEText("Please find the attached document.", 'plain'))

# Attachment from context
pdf_data = context['pdf_data']  # bytes
pdf_filename = context['pdf_filename']

attachment = MIMEBase('application', 'pdf')
attachment.set_payload(pdf_data)
encoders.encode_base64(attachment)
attachment.add_header('Content-Disposition', f'attachment; filename={pdf_filename}')
msg.attach(attachment)

smtp.send_message(msg)
```

---

## Complete Example

```python
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.models.credentials import get_email_credentials

try:
    # Get credentials
    email_creds = get_email_credentials(context['client_slug'])

    # Create rejection email
    msg = MIMEMultipart()
    msg['From'] = email_creds.email_user
    msg['To'] = context['email_from']
    msg['Subject'] = f"Re: {context['email_subject']} - Rejection Notice"

    # Build body based on reason
    if not context.get('has_pdf'):
        reason = "no PDF attachment was found"
    elif not context.get('passes_whitelist'):
        reason = "sender is not in approved whitelist"
    else:
        reason = "unknown error"

    body = f"""Hello,

We received your email but cannot process it because {reason}.

Please review and resubmit.

Thank you,
Automated Processing Team
"""
    msg.attach(MIMEText(body, 'plain'))

    # Send
    smtp = smtplib.SMTP(email_creds.smtp_host, email_creds.smtp_port)
    smtp.starttls()
    smtp.login(email_creds.email_user, email_creds.email_password)
    smtp.send_message(msg)
    smtp.quit()

    print(json.dumps({
        "status": "success",
        "context_updates": {
            "rejection_sent": True,
            "rejection_reason": reason
        }
    }))

except smtplib.SMTPAuthenticationError:
    print(json.dumps({"status": "error", "message": "SMTP authentication failed"}))
except smtplib.SMTPException as e:
    print(json.dumps({"status": "error", "message": f"SMTP error: {str(e)}"}))
except Exception as e:
    print(json.dumps({"status": "error", "message": f"Error: {str(e)}"}))
```

---

## Key Points

- **starttls() before login()**: CRITICAL for port 587
- **Always quit()**: Close connection properly
- **Port 587 + starttls()**: Recommended (not port 465)
- **Validate recipients**: Check email format before sending
- **Handle errors**: Catch `SMTPAuthenticationError`, `SMTPRecipientsRefused`, `SMTPException`

---

**Integration**: SMTP (smtplib + email.mime)
**Use with**: Email notifications, automated responses, invoice workflows

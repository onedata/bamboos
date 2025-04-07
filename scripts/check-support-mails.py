#!/usr/bin/python3

# Authors: Darin Nikolow
# Copyright (C) 2025 ACK CYFRONET AGH
# This software is released under the MIT license cited in 'LICENSE.txt'

# Usage: ./check-support-mails.py

# This script checks for unread email messages and sends them to slack.
# It is intended to be run as a cron job, for example, every 5 minutes.
# The script requires that the credentials are placed in file "/home/ubuntu/.support-creds".
# Example content of the creds file:
#   export EMAIL_ACCOUNT = "odsupbot@gmail.com"
#   export PASSWORD = "abcd efgh qwer asdf"  # (odsupbot) Use App Password, NOT Gmail password
#   export SLACK_BOT_TOKEN = "xoxb-1234567890-1234567890-ruABCDEF1234567890"
#   export CHANNEL_ID = "ABCD1244" # the slack channel id

import imaplib
import email
from email.header import decode_header
import requests
from dotenv import load_dotenv
import os

load_dotenv("/home/ubuntu/.support-creds")

# Gmail IMAP settings
IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")
PASSWORD = os.getenv("PASSWORD")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Slack API endpoint
URL = "https://slack.com/api/chat.postMessage"

# Headers and payload
HEADERS = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
    "Content-Type": "application/json"
}

# Connect to Gmail IMAP server
mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL_ACCOUNT, PASSWORD)
mail.select("inbox")  # Select inbox

# Search for unread emails
status, messages = mail.search(None, 'UNSEEN')

# Convert email IDs to a list
email_ids = messages[0].split()

for email_id in email_ids:
    # Fetch the email
    status, msg_data = mail.fetch(email_id, "(RFC822)")
    for response_part in msg_data:
        if isinstance(response_part, tuple):
            msg = email.message_from_bytes(response_part[1])

            # Decode email subject
            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8")

            print("New mail received. Subject:", subject)
            message_text = "New mail received. Subject: " + subject
            # Print email sender
            print("From:", msg.get("From"))
            message_text += ", From: " + msg.get("From") + ", Body: ```"

            # Print email body (text part only)
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain":
                        body = part.get_payload(decode=True).decode()
                        print("Body:", body)
                        message_text += body
                        break
            else:
                body = msg.get_payload(decode=True).decode()
                print("Body:", body)
                message_text += body
            message_text += "```"
            print("=" * 50)
    payload = {
        "channel": CHANNEL_ID,
        "text": message_text
    }

    # Send the message
    response = requests.post(URL, json=payload, headers=HEADERS)

    # Print response
    print(response.json())

mail.logout()


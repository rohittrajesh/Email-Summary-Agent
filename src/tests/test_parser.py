# src/tests/test_parser.py

import pytest
from email_summarizer.parser import parse_email

SIMPLE_THREAD = """\
From: Alice <alice@example.com>
Date: Mon, 1 Jan 2025 10:00:00 -0800
Subject: Hello

Hi there,
This is Alice’s first message.

From: Bob <bob@example.com>
Date: Mon, 1 Jan 2025 11:00:00 -0800
Subject: Re: Hello

Hey Alice,
Thanks for your note!
"""

def test_parse_email_simple():
    msgs = parse_email(SIMPLE_THREAD)
    # we expect two messages in chronological order
    assert len(msgs) == 2
    assert msgs[0]["sender"] == "Alice <alice@example.com>"
    assert "first message" in msgs[0]["body"]
    assert msgs[1]["sender"] == "Bob <bob@example.com>"
    assert "Thanks for your note" in msgs[1]["body"]


def test_parse_real_email():
    RAW = """\
MIME-Version: 1.0
Date: Fri, 4 Jul 2025 18:51:32 +0900
Message-ID: <CAFq0HMzTo8OnM7OVoiw7NwTvp4J6UThG85S1KeNkMVLjsRUgPA@mail.gmail.com>
Subject: GitHub Link & Code for OCR Comparison
From: Rohit Aryan Rajesh <rohitaryan296@gmail.com>
To: "bylee.necton@gmail.com" <bylee.necton@gmail.com>, mercuri.park@gmail.com
Content-Type: multipart/alternative; boundary="0000000000005a4e840639177093"

--0000000000005a4e840639177093
Content-Type: text/plain; charset="UTF-8"

Hello,

Please find the link to the Github repository below which contains my code
for the OCR Comparison project.

My initial questions were regarding how we can transform this code to
compare upwards of 20 OCR's at a quick pace, however, since we have
already moved on from the comparison/experimentation phase I believe the
code below is a good reflection of the project!

Please let me know if you have any questions or other concerns regarding
the program, I would be happy to clarify anything further.

Github Link <https://github.com/rohittrrajesh/OCR_Comparison>

Best Regards,
Rohit Rajesh

--0000000000005a4e840639177093--
"""

    msgs = parse_email(RAW)
    # we expect exactly one message
    assert len(msgs) == 1

    msg = msgs[0]
    assert msg["sender"] == "Rohit Aryan Rajesh <rohitaryan296@gmail.com>"
    assert "Please find the link to the Github repository below" in msg["body"]
    assert "My initial questions were regarding how we can transform this code" in msg["body"]
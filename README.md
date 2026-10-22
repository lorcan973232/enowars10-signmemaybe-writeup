# SignMeMaybe — SSRF via open-redirect into a PDF attachment (ENOWARS 10)

My write-up and exploit for **SignMeMaybe**, a service in the ENOWARS 10
attack/defence CTF. Playing cryptography and web for Ireland's team, I found and
exploited a server-side request forgery that let any registered user read other
teams' flags, and patched our own copy of the service against it.

The competition has concluded and the service is open source, so this documents
a finished challenge. It contains my own exploit and notes, not the organisers'
service source.

## The service

SignMeMaybe is a contract-signing API. Users register, write contracts, and
download them as rendered PDFs. Each flag is stored as an **archive packet**
reachable only from inside the container, on a loopback-only route:

```text
http://127.0.0.1:1984/internal/archive/packets/<archiveTicket>
```

A contract body may contain an **attachment link**,
`<link rel="attachment" href="..." title="...">`. When the service renders a
contract to PDF, its renderer fetches each attachment href **server-side** and
embeds the response in the PDF. That server-side fetch is the sink.

## The vulnerability

Three facts combine into a full SSRF-to-exfiltration chain:

1. **The flag endpoint is reachable from the server itself.** It is only meant
   to be internal, but "internal" is enforced by network position (loopback),
   not by authentication.
2. **The PDF renderer fetches attacker-controlled URLs server-side.** A link in
   a contract I control decides what the server fetches.
3. **The service has an open redirect of its own:** `GET /api/links/leave?to=<url>`
   redirects the caller to any `to` target.

A direct attachment link to `http://127.0.0.1:1984/...` is refused — the sink
has an SSRF guard that blocks loopback and internal hosts. But the guard checks
only the URL it is handed, while the fetcher still **follows redirects**. So I
point the attachment at the service's own `/api/links/leave?to=<internal-url>`:
the guard sees a same-origin, allowed URL, the fetch starts, the redirect sends
it to `127.0.0.1`, and the renderer embeds the internal flag packet in the PDF.

> The guard is clear from the exploit's shape: the attack goes *through* the
> redirect rather than straight at `127.0.0.1`, which only works if a direct
> internal URL is blocked while the URL after a redirect is not re-checked. The
> fix is the other side of that same coin.

## The exploit

Full attack, end to end:

1. **Get an account.** Register (or log in on a repeat run), and keep the
   returned token in the `X-Session-Token` header.
2. **Enumerate victims.** For each target the gameserver names, list their public
   contracts at `GET /api/users/<victim>/contracts` and collect every
   `archiveTicket` — the handle to that team's stored flag packet.
3. **Fire the SSRF.** For each ticket, create a contract whose body is

   ```html
   <link rel="attachment"
         href="http://TARGET/api/links/leave?to=http%3A%2F%2F127.0.0.1%3A1984%2Finternal%2Farchive%2Fpackets%2F<ticket>"
         title="annex.txt">
   ```

   then download `GET /api/contracts/<reference>/versions/latest/pdf`. The PDF
   now carries the internal flag packet as an embedded attachment.
4. **Extract the flag** from the PDF bytes with the ENOWARS flag regex.

Two versions are here:

| File | What it is |
| --- | --- |
| [`exploit.py`](exploit.py) | A cleaned, standalone version. Takes `--target` and `--flag-id` on the command line, does nothing on import, and is the one to read. |
| [`as-submitted/indirect_document_key_formatted.py`](as-submitted/indirect_document_key_formatted.py) | Exactly what I ran during the competition, inside our team's game-farm framework (`exploit(...)`, `get_flagids`, `stealth_session` and the rest come from that framework's `include/utils`, which is the team's and is not included here). |

The as-submitted version uses `stealth_session()` — a new TCP connection per
request — to blend our exploit traffic in among everyone else's during the game,
so it was harder to pick out in flow-analysis tools. The standalone version uses
an ordinary session.

```bash
python -m pip install -r requirements.txt
python exploit.py --target http://127.0.0.1:1984 --flag-id some_victim_user
```

Point it only at a copy of the service you run yourself.

## The fix

My exploit works because the annex fetcher trusts a redirect chain it should
not. I patched our copy of the service to close it there, with two changes:

- **Re-check every redirect hop, not just the first URL.** The fetcher validated
  the URL it was handed and then followed redirects without looking at where they
  led. Applying the same host rules to each hop means a user-supplied annex that
  starts at an allowed URL but redirects toward loopback, private, link-local,
  multicast or wildcard addresses is refused at the hop that turns internal —
  the exact step my exploit depends on.
- **Keep user-supplied annex content away from the internal packet route.** That
  route exists only for the service's own jobs. The fix makes sure a fetch that
  originated from user contract content can neither be steered to the internal
  endpoint nor present itself as a trusted internal job, so the flag packet can
  no longer be drawn into an attacker's PDF.

Either change alone defeats the exploit; together they leave no path from a
user-controlled annex to the internal flag packet, while an owner's own packet
retrieval and ordinary public annex links keep working.

### Verifying the fix

- An owner still retrieves their own archive packet through the authenticated
  contract endpoint.
- A genuinely public annex (an ordinary HTTP/HTTPS link) still embeds in the
  rendered PDF as before.
- A direct loopback annex URL is refused.
- The leave-redirect-into-internal-packet trick is refused during PDF
  generation.
- An attacker's generated PDF no longer contains anyone else's archive packet.
- The gameserver's `getflag` check for this flag store still succeeds, while its
  `exploit` check for it now fails.

## Credits

SignMeMaybe is part of **ENOWARS 10**, written by the ENOWARS organisers
(service © Leon Wilms, MIT licence). This repository is my own exploit and
analysis; the service source is not reproduced here. Original service:
<https://github.com/enowars/enowars10-service-SignMeMaybe>.

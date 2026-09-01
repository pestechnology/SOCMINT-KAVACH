# OnionSearch — network-isolated sandbox

A dedicated, isolated Docker setup for running [OnionSearch](https://github.com/megadose/OnionSearch)
(a dark-web/`.onion` search aggregator) with a **network-level** guarantee that your
real IP can never leak — not just an application-level proxy config you have to
trust.

Standalone tool. Deliberately **not** part of VERTEX's main `docker-compose.yml` or
backend process — this never shares a process, credentials, or network with anything
that also makes real-IP calls (Serper, GitHub, etc.).

## How the safety guarantee actually works

```
┌─────────────────────┐        ┌──────────────────────┐        ┌─────────┐
│  onionsearch         │──────▶│  tor                  │──────▶│  Tor    │
│  network: isolated   │        │  networks: egress +   │        │ network │
│  (internal: true —   │        │  isolated             │        │         │
│  NO route to the      │        │                       │        └─────────┘
│  internet at all)     │        └──────────────────────┘
└─────────────────────┘
```

The `isolated` Docker network is created with `internal: true`. Docker removes the
default route to the internet for that network **entirely, at the kernel/network-
namespace level.** The `onionsearch` container is attached ONLY to `isolated`. Its
only possible destination is the `tor` container (resolved via Docker's own internal
DNS, not the internet), which is the sole path out — and only over Tor.

This means: even a hypothetical bug in OnionSearch's own proxy handling, or in any
library it depends on, **cannot** leak a direct connection. There's no route for it
to take — the isolation doesn't depend on the Python code getting it right.

## Verified proof (run 2026-09-01)

**1. Direct internet access from inside `onionsearch` fails completely — even DNS:**
```
$ docker compose run --rm --entrypoint python onionsearch -c "..."
BLOCKED as expected (no direct route out): URLError
  [Errno -3] Temporary failure in name resolution
```
DNS resolution itself fails for anything outside Docker's own service discovery —
not just the HTTP connection. That's a stronger guarantee than "the request timed
out."

**2. The exact same `requests` + `socks5h://` pattern OnionSearch itself uses,
pointed at `tor:9050`, reaches the internet ONLY as a real Tor exit — verified against
Tor Project's own check API:**
```
$ docker compose run --rm --entrypoint python onionsearch -c "..."
VIA TOR OK: 200 {"IsTor":true,"IP":"107.189.3.94"}
```
`IsTor: true` confirms the destination sees a genuine Tor exit relay. `107.189.3.94`
is that relay's IP, not the host machine's.

## What's still just normal Tor-network behavior, not a safety issue

Live test runs against real `.onion` search engines (Ahmia, Tor66, Phobos) took a
long time or failed with `TTL expired` / connection errors reaching the hidden
service. **This is expected, ordinary Tor hidden-service flakiness** — `.onion`
rendezvous circuits are frequently slow or briefly unavailable, independent of this
sandbox. It's not a leak, not a misconfiguration — just don't expect fast, always-on
results the way you would from a clearnet API like Serper.

## Usage

```bash
cd tools/onionsearch-sandbox

# start Tor once, leave it running
docker compose up -d tor

# run a search — results land in ./output/ on the host
docker compose run --rm onionsearch "search term" --limit 2 --output /output/results.csv

# stop everything when done
docker compose down
```

**Windows/Git Bash users:** prefix commands with `MSYS_NO_PATHCONV=1` — Git Bash
otherwise mangles the `/output/...` container path into a Windows path (e.g.
`C:/Program Files/Git/output/...`), which breaks OnionSearch's own file write:
```bash
MSYS_NO_PATHCONV=1 docker compose run --rm onionsearch "search term" --limit 2 --output /output/results.csv
```

Give it several minutes for a real result — dark-web search engines are slow. If
you're impatient, `--engines ahmia tor66` lets you target specific engines instead of
all 16.

## What this does NOT protect against

Being explicit about the remaining, non-network risk surface (see the earlier
conversation for full detail):

- **Tor usage itself is visible to a local network observer** (your ISP/network) —
  they can see you're using Tor, just not what you searched for.
- **This only isolates the OnionSearch container.** If you manually open a `.onion`
  URL in a real browser later to look at something this tool found, that browser
  session is a completely different risk profile (JS execution, fingerprinting) —
  this sandbox says nothing about that.
- **Content found is not automatically evidence-chain-safe.** If anything found here
  needs to go into a case, treat it the same way you'd treat any other sensitive
  source: sensitivity-flagged, not presented as a verified profile (see
  `SerperScraper`'s `sensitive=True` pattern in the main codebase for the existing
  convention).

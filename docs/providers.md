---
title: Providers
nav_order: 14
---

# Recommended providers

Two subscriptions sit behind the stack: a **Usenet provider** (the storage InfiniDysk downloads
from) and a **Usenet indexer** (where the \*arrs find releases). Wiring runs through
[Prowlarr](services/prowlarr) and [InfiniDysk](services/infinidysk).

## Usenet provider

**Recommendation:** [Eweka](https://www.eweka.nl/en/pricing) is a strong provider to consider. It
operates its own Netherlands-based Usenet backbone and advertises over 6,000 days of article
retention, which can help keep older releases available. SSL is included; check its current plan
limits against your connection allowance and usage.

InfiniDysk talks plain NNTP to your provider — there is no API key, no plug-in, and no
provider-specific integration to configure. What matters is the connection detail your provider
hands you, and the plan limits behind it:

- **Connection allowance** — the concurrent connections your account may hold. `just init` asks for
  it, and it is a ceiling, not a target: set the number from your plan, because exceeding it gets
  the connection throttled or blocked. It governs concurrency only, not how much you transfer.
- **Transfer allowance** — how much you may pull per day or month, if the plan meters it. This
  stack stores no media, so transfer tracks **watch time, not library size**: every play and every
  seek re-fetches from the provider, at roughly 5–15 GB per two-hour 1080p WEB watch and 50–90 GB
  per two-hour 4K remux watch ([InfiniDysk](services/infinidysk#provider-data-usage)). Prefer a
  plan with generous transfer or no cap at all; an uncapped plan removes this from the decision
  entirely.
- **TLS** — use the encrypted port your provider documents (`563` is the common one). Turning
  TLS off sends your credentials in cleartext.
- **Retention and article availability** — how long releases stay in the news spool, and whether
  your plan covers the articles a given release needs. This is the single most common reason a
  grab fails even though the indexer found it.

Look for a provider that publishes an explicit connection allowance and a retention period; both
show up directly in the `just init` prompts.

## Usenet indexer

- **Newznab-compatible** is the requirement. Add the indexer in Prowlarr using its URL and API key;
  see [Prowlarr](services/prowlarr).
- **AltHub** is a well-known one-time-payment Newznab indexer — check its current terms before
  buying.
- **Private Usenet trackers** (nzb-style invite sites) are the other common route; they work the
  same way, one indexer at a time.

Anything torrent-based is not useful here: there is no torrent client in the stack, and results
from a torrent indexer cannot be fetched over NNTP.

## Subtitle providers

For Bazarr, **[OpenSubtitles.com](https://www.opensubtitles.com/)** is a sensible primary provider;
its free tier may have request limits. **[SubDL](https://subdl.com/)** is a useful fallback. Check
current account requirements and quotas when configuring either provider.

**Whisper** is an optional subtitle-generation route rather than a subtitle indexer. It requires a
separate ASR service and can generate subtitles when downloaded ones are unavailable. See
[Bazarr's wiki](https://wiki.bazarr.media/) for supported providers and configuration.

> Pricing as of writing — confirm on vendor sites before subscribing.

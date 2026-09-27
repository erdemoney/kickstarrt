---
title: Indexers
parent: Services
nav_order: 11
---

# Indexers: Usenet in Prowlarr

Prowlarr is the single place indexers are configured; everything syncs to Sonarr/Radarr via
"Apps" (wired in [Prowlarr](prowlarr)). Any time after the stack is up
([Quickstart §9](../quickstart#9-set-up-the-apps)) — but you need at least one before grabs
work.

This is a Usenet stack, so only **Usenet** indexers belong here: everything is fetched from your
news provider over NNTP by [InfiniDysk](infinidysk). A torrent indexer has nothing to download
through, and adding one only produces results the pipeline cannot use.

## Adding a Usenet indexer (e.g. AltHub)

1. Buy / register (see [Providers](../providers)), then take the **API key + Newznab URL** from the
   indexer's profile page.
2. Prowlarr → Indexers → **+** → **Newznab**: paste the URL and API key, enable, test, save.
3. It syncs to Sonarr/Radarr automatically via the Apps configured earlier. Assign the
   `tv` or `movies` category (and a quality profile) under Indexers → the indexer's
   **Mappings** tab — those are the categories InfiniDysk accepts
   ([InfiniDysk](infinidysk#what-the-stack-configures-and-why)).

Then run a test search in Sonarr or Radarr: a working indexer returns a release, the Arr sends it
to InfiniDysk, and a finished download lands in `/mnt/usenet/completed-downloads` ready to import.

## Troubleshooting

- **Indexer test fails in Prowlarr** — check the Newznab URL and API key first; that path is
  independent of the rest of the stack.
- **The Arr searches but nothing is grabbed** — the indexer is returning categories the Arr has no
  quality profile for, or the profile rejects every release.
  See [Recyclarr](recyclarr) for how the profiles score candidates.
- **Grabs fail once they reach InfiniDysk** — that's a provider-side availability or path problem,
  not an indexer one; see [InfiniDysk](infinidysk#troubleshooting).

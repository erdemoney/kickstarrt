---
title: Maintainerr
parent: Services
nav_order: 4
---

# Maintainerr: media-library cleanup

Maintainerr evaluates Jellyfin library items against rules that can use Seerr request details,
watch history, and Radarr/Sonarr metadata. Matching items can be held in a collection for a grace
period, then unmonitored or removed through the selected *arr application.

## Access and setup

Open `https://maintainerr.<DOMAIN>` over the tailnet. Maintainerr has no built-in login, so its UI
is deliberately tailnet-only and must not be published directly to the internet. The configuration
and database are persisted under `data/maintainerr`.

Run `just wire` to configure Maintainerr's **Jellyfin**, **Seerr**, **Radarr**, and **Sonarr**
connections. It reuses the API keys managed by the stack and stores them in Maintainerr's SQLite
database under `data/maintainerr`. Maintainerr stores these credentials in cleartext in that
database, so keep the app tailnet-only and protect encrypted backups of `data/`.

The connections can also be configured in its **Services** page:

| Service | Internal URL | Credential |
| --- | --- | --- |
| Jellyfin | `http://jellyfin:8096` | API key from Jellyfin Dashboard → API Keys |
| Seerr | `http://seerr:5055` | API key from Seerr Settings |
| Radarr | `http://radarr:7878` | API key from Settings → General |
| Sonarr | `http://sonarr:8989` | API key from Settings → General |

`just wire` uses the internal service URLs, not public or tailnet hostnames. For rule-based cleanup,
select the corresponding Radarr or Sonarr instance as the rule's action handler.

## Example: expire friends' requests after 90 days

For a request-age policy, create a rule that matches the chosen Seerr **Requested by user** names
and requires Seerr **Request date** to be before 90 days ago. Set the rule's action to the relevant
Radarr or Sonarr delete/unmonitor action, and set **Media deleted after days** to `0`; the request
date condition is already providing the 90-day wait. Maintainerr processes rules and collection
actions on a schedule, so removal happens on a later handler run.

Alternatively, match the selected requesters and set **Media deleted after days** to `90`. In that
case, the countdown starts when the item enters the Maintainerr collection, rather than from its
original request date.

Start with a non-destructive **Do nothing** action, test the conditions against sample items, and
inspect the resulting collection before enabling deletion. If you want to exempt your own
requests, match an explicit list of the other users. Check items with multiple requesters to confirm
they behave as intended. Maintainerr can also clear Seerr request records as part of a cleanup
action; see its rule options and [Seerr rule fields](https://docs.maintainerr.info/glossary/).

In this stack, Radarr and Sonarr manage tiny `.strm` library files. Maintainerr can remove those
through the *arr APIs; the corresponding media remains on the Usenet provider. Maintainerr's
optional leftover-folder cleanup needs `/mnt/usenet` mounted read-write at that exact same path in
the container, which this Compose service does not mount. Leave that option off unless you
deliberately add and verify the mount.

## Further reading

- [Maintainerr documentation](https://docs.maintainerr.info/)
- [Configuration](https://docs.maintainerr.info/configuration/)
- [How rules and retention work](https://docs.maintainerr.info/works/)

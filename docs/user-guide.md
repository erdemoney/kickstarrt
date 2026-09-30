---
title: User guide
nav_order: 9
---

# Jellyfin and Seerr: user guide

Use **Seerr** to find and request movies and shows. Use **Jellyfin** to watch them.

Your administrator will provide the links and login details for both services:

- **Seerr:** `https://seerr.<DOMAIN>`
- **Jellyfin:** `https://jellyfin.<DOMAIN>`

You can use either service in a web browser, or install a compatible app on your device.

Your administrator may provide an initial password. Keep it unless they ask you to change it. If you
do change it, use a strong, unique password of at least 14 characters. A passphrase made from four
or more unrelated words is a good option. Do not reuse a password from another service.

## Is it safe to use?

Jellyfin and Seerr use HTTPS encryption. This protects your sign-in details and video stream while
they travel between your device and the server, so your ISP or someone monitoring the network cannot
read the content. Your administrator manages the service and may be able to see your requests and
viewing activity.

No downloading happens on your device. Your administrator's server fetches the content from their
Usenet provider over an encrypted connection, then it is transmitted to you over the encrypted
HTTPS connection.

## Request something to watch

1. Open Seerr and search for a movie or show.
2. Open the title and choose **Request**.
3. For a show, choose whether to request the whole show or specific seasons.
4. Check the request status from your requests list.

When requesting anime, choose the **Direct Play (Anime)** quality profile.

Requests can take a few minutes to become available. Once a request is ready, it will appear in
Jellyfin. If a title is already available, Seerr will show that instead of asking you to request
it again.

## Watch something

1. Open Jellyfin and choose a library, or search for a title.
2. Select the title and choose **Play**.
3. Use the player controls to pause, seek, change the volume, or select an audio track or subtitle.

Jellyfin remembers your progress, so you can continue watching later. You can also add titles to
your favorites and mark them watched or unwatched.

## Recommended apps

The web app works on most devices, but a dedicated app usually provides a better experience.

- **Official Jellyfin apps** for Android, Android TV/Google TV, iPhone, iPad, Apple TV, and desktop
  computers
- **Samsung Tizen** app for compatible Samsung smart TVs
- **Swiftfin** for iPhone, iPad, and Apple TV
- **Kodi with the Jellyfin add-on** for devices where Kodi is already installed

App availability can vary by device and app store. See the [Jellyfin clients page](https://jellyfin.org/downloads/clients/)
for the latest options. When an app asks for the server address, use the Jellyfin link provided by
your administrator.

## If something does not work

- If new content is not visible, refresh the page or close and reopen the app.
- If playback fails, try a different audio track or temporarily turn subtitles off.
- If playback buffers, try using a wired or stronger Wi-Fi connection.
- If a request has not become available after a reasonable wait, contact your administrator.

When reporting a problem, include the title, the device and app you are using, and any error message
shown on screen.

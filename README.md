# 🎮 Steam Headless GNOME

A standalone **Debian 13 · GNOME on Xorg · Steam · Sunshine** container for Linux gaming. No XFCE and no dependency on another Steam Headless image.

> 🧪 **Preview · Linux amd64.** The isolated desktop works. Physical display, receiver reconnect, Moonlight gamepad and local Bluetooth audio still need end-to-end testing for this build. There is no published image yet.

## ✨ What’s inside

- 🖥️ GNOME on Xorg, with Colemak and German keyboard layouts, Dash to Dock, and AppIndicator
- 🕹️ The Debian Steam installer with 32-bit Mesa graphics drivers. Open Steam from the desktop to download the client and sign in; games and Proton are not bundled.
- ☀️ Sunshine with software encoding in virtual mode and VAAPI configured in physical mode
- 🦊 Firefox ESR

## 🛠️ Build and try it locally

```sh
docker build --pull -t steam-headless-gnome:local .
docker run -d --rm --init --name steam-headless-test --shm-size=512m \
  --security-opt=no-new-privileges --network none \
  steam-headless-gnome:local
docker logs -f steam-headless-test
```

This starts GNOME on a **virtual X11 display** without host input, display output or network access. After the Sunshine startup message, check the internal HTTPS endpoint with `docker exec steam-headless-test curl -k -sS -o /dev/null -w '%{http_code}\n' https://127.0.0.1:47990/`. Use `docker stop steam-headless-test` to clean up.

For a physical setup, `PHYSICAL=1` expects host-specific DRM, VT and input device configuration. The included `xorg.conf` is an example, not a universal hardware profile. Use a dedicated host bind mount for `/home/default` writable by UID 1000 if you want persistent Steam and Sunshine state. Keep the Sunshine admin interface off the public internet.

## 🤖 CI and updates

- GitHub Actions builds on pushes to `main`, pull requests, manual dispatch and every Monday. It tags the image `steam-headless-gnome:sha-<commit>` on the runner. **No registry push.**
- The scheduled build starts without Docker layer cache so it picks up current Debian packages from the configured repositories, even with no source changes.
- Dependabot checks the pinned Debian base and GitHub Actions weekly and proposes updates via pull request. The separately downloaded Sunshine package stays pinned; update its URL and SHA-256 together.

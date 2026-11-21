# 🎮 Steam Headless GNOME

A standalone **Debian 13 · GNOME on Xorg · Steam · Sunshine** container for Linux gaming. No XFCE and no dependency on another Steam Headless image.

> 🐧 **Linux amd64.** CI tests the desktop on a virtual X11 display. Physical DisplayPort (monitor on and off), Logitech reconnect, Moonlight video and gamepad input, and AirPods playback need end-to-end validation on the standalone image.

## ✨ What’s inside

- 🖥️ GNOME on Xorg, with Colemak and German keyboard layouts, Dash to Dock, and a top-right **Extension List** menu
- 🔔 AppIndicator shows Sunshine’s tray icon and Deskflow’s icon once its GUI is open. Existing profiles must have AppIndicator and Extension List enabled.
- 📊 **System Monitor Next** shows system metrics in the top bar. **WACK Shell** and **WACK Sonoma Lockscreen** are installed and can be enabled from Extension List; they are off by default. System Pulse is not bundled because it requires GNOME Shell 50, while this image uses GNOME 48.
- 🕹️ The Debian Steam installer with 32-bit Mesa graphics drivers. Open Steam from the desktop to download the client and sign in; games and Proton are not bundled.
- ☀️ Sunshine with software encoding in virtual mode and VAAPI configured in physical mode
- 🦊 Firefox ESR
- ⌨️ Deskflow for sharing a keyboard and mouse over the LAN. It does not start automatically, and the image does not publish its port.

### ⌨️ Deskflow

Open **Deskflow** in GNOME. To control this desktop from another computer, configure that computer as the Deskflow server and this desktop as a client. Use the server’s private LAN address and verify its TLS fingerprint. No incoming Deskflow port is needed on the container host.

If you use the container as the server instead, restrict TCP `24800` to the trusted LAN at the host firewall (including Docker-forwarded traffic) and keep TLS enabled. Do not expose Deskflow through a public router or internet port forwarding.

## 🛠️ Build and try it locally

After a successful publish, the registry image is `ghcr.io/dmuix/steam-headless-gnome:latest`. To build and run locally instead:

```sh
docker build --pull -t steam-headless-gnome:local .
docker run -d --rm --init --name steam-headless-test --shm-size=512m \
  --security-opt=no-new-privileges --network none \
  steam-headless-gnome:local
docker logs -f steam-headless-test
```

This starts GNOME on a **virtual X11 display** without host input, display output or network access. After the Sunshine startup message, check the internal HTTPS endpoint with `docker exec steam-headless-test curl -k -sS -o /dev/null -w '%{http_code}\n' https://127.0.0.1:47990/`. Use `docker stop steam-headless-test` to clean up.

For a physical setup, `PHYSICAL=1` expects host-specific DRM, VT and input device configuration. The included `xorg.conf` is an example, not a universal hardware profile. Use a dedicated host bind mount for `/home/default` writable by UID 1000 if you want persistent Steam and Sunshine state. Keep the Sunshine admin interface off the public internet.

## 📦 Debian Backports

The build prefers `trixie-backports` for all APT package installations, including dependencies, and falls back to Debian stable and its security repositories for packages without backports. This includes Mesa for both amd64 and the 32-bit Steam runtime. GNOME Shell stays at 48: Debian does not provide a GNOME 50 backport for Trixie, and this image intentionally uses the Debian GNOME Xorg session. Sunshine and extensions downloaded outside APT keep their own pins.

## 🤖 CI and updates

- Pull requests run Bash syntax checks, ShellCheck and actionlint. To build and smoke-test a branch before merging, select that branch under **Actions → Build container image → Run workflow**, or run `gh workflow run build.yml --ref <branch>`. Neither path can publish. On `main`, pushes and manual dispatch build, test and scan before publishing to GHCR.
- 🔍 Trivy blocks publishing on fixable HIGH and CRITICAL findings and generates a CycloneDX SBOM as a workflow artifact. The exact tested image is published under `latest` and a unique `sha-<commit>-<run>-<attempt>` tag. For reproducible deployment, pin the registry digest.
- The hourly schedule (minute 23 UTC) checks the Debian package indexes, including security updates. If the indexes or revision have changed since a successful scheduled publish, it builds again. Release builds reuse Docker layers from GitHub Actions Cache; the APT layer is invalidated when the package-index fingerprint or the package-install instructions change. This checks repository indexes, not whether an individual changed package is installed in the image. GitHub may delay scheduled runs.
- Dependabot checks the pinned Debian base daily and GitHub Actions weekly, proposing changes via pull request. The separately downloaded Sunshine package stays pinned; update its URL and SHA-256 together.

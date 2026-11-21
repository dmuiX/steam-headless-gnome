# Debian 13 slim (Trixie)
FROM debian:13-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2

COPY --chmod=0644 amd-vulkan.dpkg /etc/dpkg/dpkg.cfg.d/steam-headless-amd-vulkan
COPY --chmod=0644 trixie-backports.sources /etc/apt/sources.list.d/trixie-backports.sources

# CI passes the signed APT indexes' fingerprint to invalidate this layer on updates.
ARG APT_INDEX_KEY=local
RUN set -eux; export DEBIAN_FRONTEND=noninteractive; \
    printf 'APT index cache key: %s\n' "$APT_INDEX_KEY"; \
    printf '%s\n' 'path-exclude=/usr/share/help/*' > /etc/dpkg/dpkg.cfg.d/steam-headless-slim; \
    dpkg --add-architecture i386; \
    sed -i 's/^Components: main$/Components: main contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources; \
    apt-get -o APT::Update::Error-Mode=any update; \
    apt-get install -y --no-install-recommends -t trixie-backports \
      ca-certificates curl dbus dbus-x11 systemd kmod \
      gnome-session-xsession gnome-terminal gnome-shell-extension-appindicator gnome-shell-extension-dashtodock \
      dconf-cli deskflow firefox-esr fonts-liberation \
      gir1.2-gtop-2.0 gir1.2-nm-1.0 gir1.2-upowerglib-1.0 \
      xserver-xorg-core xserver-xorg-input-evdev xvfb xauth xinput x11-utils x11-xserver-utils \
      pulseaudio pulseaudio-utils pulseaudio-module-bluetooth blueman bluez \
      libgl1-mesa-dri libgl1-mesa-dri:i386 mesa-vulkan-drivers mesa-vulkan-drivers:i386 mesa-va-drivers \
      steam-installer steam-devices; \
    curl --fail --location --silent --show-error --proto '=https' --max-time 90 \
      'https://github.com/SunshineStream/Sunshine/releases/download/v2026.914.233613/sunshine_2026.914.233613-1%2Bdebiantrixie_amd64.deb' \
      -o /tmp/sunshine.deb; \
    echo 'a86f858cbae57f60ecebd445402ee0295c1c057b857bd45d44c2ea2d255cbbfb  /tmp/sunshine.deb' | sha256sum -c; \
    apt-get install -y --no-install-recommends -t trixie-backports /tmp/sunshine.deb; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/* /tmp/sunshine.deb; \
    test ! -e /usr/bin/startxfce4; \
    command -v deskflow; \
    python3 -c 'import ctypes; ctypes.CDLL("libXtst.so.6")'

# GNOME Shell 48 extensions: Extension List v42, WACK Lockscreen v46, System Monitor Next v91.
RUN set -eux; \
    fetch() { \
      curl --fail --location --silent --show-error --proto '=https' --max-time 60 "$1" -o "$3"; \
      printf '%s  %s\n' "$2" "$3" | sha256sum --check --strict; \
    }; \
    install_extension() { \
      uuid="$1"; destination="/usr/share/gnome-shell/extensions/$uuid"; \
      fetch "https://extensions.gnome.org/download-extension/$uuid.shell-extension.zip?version_tag=$2" "$3" /tmp/extension.zip; \
      python3 -m zipfile -e /tmp/extension.zip "$destination"; \
      glib-compile-schemas --strict "$destination/schemas"; \
      rm /tmp/extension.zip; \
    }; \
    install_extension extension-list@tu.berry 63089 dfa5b8effd344f15343cb57c85fd80762b22d2f71b8e5554f6fcc21d8b1ed936; \
    install_extension wack-lockscreen-clock@rinzler69-wastaken.github.com 76044 749272d6553d0e988ceeb778aecd0fc653723012e845ee00601e97557771b69c; \
    install_extension system-monitor-next@paradoxxx.zero.gmail.com 76945 61dae39b6b7e0a817b7143454477df99c1ad204b1b62685c9a0308e815c9de39; \
    fetch 'https://codeload.github.com/rinzler69-wastaken/wack-shell/tar.gz/bfd72b56ade0db75a86bd7ac57f8e39143e920a9' \
      2b9026142eb95111ccc96e4f2057ad1e670744ec415afff16c62fcc1d2ea4515 /tmp/wack-shell.tar.gz; \
    destination=/usr/share/gnome-shell/extensions/wack-shell@rinzler69-wastaken.github.com; \
    install -d "$destination"; \
    tar -xzf /tmp/wack-shell.tar.gz -C "$destination" --strip-components=1 --no-same-owner; \
    glib-compile-schemas --strict "$destination/schemas"; \
    rm /tmp/wack-shell.tar.gz

RUN set -eux; export DEBIAN_FRONTEND=noninteractive; \
    apt-get -o APT::Update::Error-Mode=any update; \
    apt-get install -y --no-install-recommends -t trixie-backports gdm3 libpam-systemd; \
    ln -sfn /usr/lib/systemd/system/gdm3.service /etc/systemd/system/display-manager.service; \
    rm -rf /var/lib/apt/lists/*
COPY --chmod=0644 gdm.conf /etc/gdm3/daemon.conf
COPY --chmod=0644 gdm-logind.conf /etc/systemd/system/gdm3.service.d/10-logind.conf
COPY --chmod=0644 steam-headless-session.desktop /etc/xdg/autostart/steam-headless-session.desktop
COPY --chmod=0644 start-gdm.sh /usr/local/bin/steam-headless-gdm.sh
COPY --chmod=0644 start.sh /usr/local/bin/steam-headless-start.sh
COPY --chmod=0644 input-devices.sh /usr/local/bin/steam-headless-input.sh
COPY --chmod=0644 sunshine-xtest-bridge.py /usr/local/lib/steam-headless/sunshine-xtest-bridge.py
COPY --chmod=0644 xorg.conf /etc/X11/steam-headless.conf
COPY --chmod=0644 desktop-defaults /etc/dconf/db/local.d/00-steam-headless
RUN mkdir -p /etc/dconf/profile && printf 'user-db:user\nsystem-db:local\n' > /etc/dconf/profile/user && dconf update \
    && useradd --uid 1000 --home-dir /home/default --create-home --shell /bin/bash gamer
ENV LANG=C.UTF-8
ENTRYPOINT ["/bin/bash", "/usr/local/bin/steam-headless-start.sh"]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
###
# Sunshine -> XTEST Input-Bridge  (dependency-frei: nur stdlib + libX11/libXtst via ctypes)
#
# WARUM DAS NOETIG IST:
#   In diesem Container ist Xorgs udev-Delivery komplett tot - weder Coldplug noch
#   Hotplug. Bewiesen 16.07.2026: gueltige udev-"add"-Events fuer die Sunshine-
#   "passthrough"-Geraete (per dumb-udev sauber gesendet) loesen in Xorg NICHTS aus
#   (Xorg.55.log reagiert null). Die physische Tastatur/Maus laufen nur, weil sie
#   explizit in /etc/X11/xorg.conf.d/90-grab.conf stehen.
#   Sunshine erzeugt seine virtuellen Maus/Tastatur-Geraete aber DYNAMISCH (event-
#   Nummern wechseln pro Client-Connect) und erst NACH dem Xorg-Start -> nicht
#   statisch in xorg.conf eintragbar, und der udev-Weg ist tot. Ein Xorg-Restart
#   waere selbstzerstoererisch: er killt Sunshines Video-Capture -> Stream bricht ->
#   iPad trennt -> Sunshine zerstoert die passthrough-Geraete -> nach dem Restart
#   sind sie schon wieder weg. Genau das war der Grund fuer "Video ok, kein Input".
#
# WAS DIESE BRIDGE MACHT:
#   Sie liest die Sunshine-passthrough-evdev-Geraete (/dev/input/event*) direkt und
#   speist die Eingaben ueber die X11-XTEST-Extension in DISPLAY=:55 ein - voellig an
#   udev/Xorg-evdev vorbei. Maus relativ + absolut, Tasten, Mausrad. Gamepads bleiben
#   unberuehrt (Steam liest /dev/input/js* selbst, braucht X dafuer nicht).
#   Sie erkennt Geraete dynamisch (Re-Scan im Loop), nimmt Reconnects automatisch mit.
#
# LAEUFT ALS root (aus init.d/10-*.sh gestartet, vor dem User-Drop): liest alle
# /dev/input-Nodes (auch wenn ein Node faelschlich Gruppe avahi hat) und verbindet
# sich dank Xorg-Flag "-ac" ohne xauth. Wartet selbst, bis :55 verfuegbar ist.
###

import ctypes
import fcntl
import glob
import os
import select
import struct
import sys
import time

DISPLAY = os.environ.get("BRIDGE_DISPLAY", ":55")

# ---- evdev-Konstanten -------------------------------------------------------
EV_SYN, EV_KEY, EV_REL, EV_ABS, EV_MSC = 0x00, 0x01, 0x02, 0x03, 0x04
REL_X, REL_Y = 0x00, 0x01
REL_HWHEEL, REL_WHEEL = 0x06, 0x08
ABS_X, ABS_Y = 0x00, 0x01

# struct input_event: struct timeval(2x long) + type(H) + code(H) + value(i)
EV_FMT = "llHHi"
EV_SIZE = struct.calcsize(EV_FMT)

# evdev BTN_* -> X-Button
BTN_MAP = {
    0x110: 1,   # BTN_LEFT
    0x111: 3,   # BTN_RIGHT
    0x112: 2,   # BTN_MIDDLE
    0x113: 8,   # BTN_SIDE
    0x114: 9,   # BTN_EXTRA
    0x115: 9,   # BTN_FORWARD
    0x116: 8,   # BTN_BACK
    0x14a: 1,   # BTN_TOUCH (Fingertipp) -> Linksklick
    0x14b: 1,   # BTN_TOOL_PEN antippen -> Linksklick
}

# ---- X11 / XTEST via ctypes -------------------------------------------------
libX11 = ctypes.CDLL("libX11.so.6")
libXtst = ctypes.CDLL("libXtst.so.6")

libX11.XOpenDisplay.restype = ctypes.c_void_p
libX11.XOpenDisplay.argtypes = [ctypes.c_char_p]
libX11.XFlush.argtypes = [ctypes.c_void_p]
libX11.XDefaultScreen.restype = ctypes.c_int
libX11.XDefaultScreen.argtypes = [ctypes.c_void_p]
libX11.XDisplayWidth.restype = ctypes.c_int
libX11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
libX11.XDisplayHeight.restype = ctypes.c_int
libX11.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
libX11.XDefaultRootWindow.restype = ctypes.c_ulong
libX11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
# XGetGeometry liefert die LIVE-Groesse des Root-Fensters (folgt RandR-Aenderungen,
# anders als XDisplayWidth/Height, die den Wert vom Verbindungsaufbau cachen).
libX11.XGetGeometry.argtypes = [
    ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
    ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
]

libXtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
libXtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
libXtst.XTestFakeRelativeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
libXtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]


def log(msg):
    sys.stdout.write("[xtest-bridge] %s\n" % msg)
    sys.stdout.flush()


def open_display():
    while True:
        dpy = libX11.XOpenDisplay(DISPLAY.encode())
        if dpy:
            scr = libX11.XDefaultScreen(dpy)
            w = libX11.XDisplayWidth(dpy, scr)
            h = libX11.XDisplayHeight(dpy, scr)
            log("mit %s verbunden (screen %d, %dx%d)" % (DISPLAY, scr, w, h))
            return dpy, scr, w, h
        log("warte auf X-Server %s ..." % DISPLAY)
        time.sleep(2)


def live_screen_size(dpy):
    """Aktuelle Root-Fenster-Groesse vom Server (folgt RandR/Aufloesungswechsel)."""
    root = libX11.XDefaultRootWindow(dpy)
    rr = ctypes.c_ulong()
    x = ctypes.c_int(); y = ctypes.c_int()
    w = ctypes.c_uint(); h = ctypes.c_uint()
    bw = ctypes.c_uint(); depth = ctypes.c_uint()
    if libX11.XGetGeometry(dpy, root, ctypes.byref(rr), ctypes.byref(x), ctypes.byref(y),
                           ctypes.byref(w), ctypes.byref(h), ctypes.byref(bw), ctypes.byref(depth)):
        return int(w.value), int(h.value)
    return None


def get_abs_range(fd, code):
    # EVIOCGABS(code) = _IOR('E', 0x40+code, sizeof(input_absinfo)=24)
    size = 24
    nr = 0x40 + code
    ioc = (2 << 30) | (size << 16) | (ord('E') << 8) | nr
    buf = bytearray(size)
    try:
        fcntl.ioctl(fd, ioc, buf, True)
        value, minimum, maximum, fuzz, flat, res = struct.unpack("iiiiii", bytes(buf))
        if maximum > minimum:
            return minimum, maximum
    except OSError:
        pass
    return 0, 65535


# ---- Device-Handling --------------------------------------------------------
KIND_REL, KIND_ABS, KIND_KBD = "rel-mouse", "abs-mouse", "keyboard"


def classify(name):
    n = name.lower()
    if not n.startswith("libvirtualhid ") and "passthrough" not in n:
        return None
    if "keyboard" in n:
        return KIND_KBD
    if "absolute" in n:
        return KIND_ABS
    if "touch" in n or "pen" in n:   # iPad-Touch/Pen = absolute Zeiger
        return KIND_ABS
    if "mouse" in n:
        return KIND_REL
    return None


def discover():
    """Aktuelle passthrough-event-Geraete -> {node_path: (kind, name)}."""
    found = {}
    for name_file in glob.glob("/sys/class/input/event*/device/name"):
        try:
            with open(name_file) as f:
                name = f.read().strip()
        except OSError:
            continue
        kind = classify(name)
        if not kind:
            continue
        ev = name_file.split("/")[4]              # "eventN"
        node = "/dev/input/%s" % ev
        if os.path.exists(node):
            found[node] = (kind, name)
    return found


class Dev:
    def __init__(self, fd, kind, name, abs_range=None):
        self.fd = fd
        self.kind = kind
        self.name = name
        self.abs_range = abs_range          # (minx,maxx,miny,maxy) fuer KIND_ABS
        self.buf = b""
        self.abs_x = 0                      # zuletzt bekannte Absolut-Position (Screen-Pixel)
        self.abs_y = 0
        self.screen_w = 0                   # Screen-Groesse zum Zeitpunkt des Oeffnens (KIND_ABS)
        self.screen_h = 0
        # Gedrueckte Eingaben pro dynamischem evdev-Geraet merken. Sunshine
        # entfernt diese Nodes beim Disconnect; ohne explizites Key-Up bliebe
        # der letzte XTEST-Zustand sonst in Anwendungen haengen.
        self.held_keys = set()
        self.held_buttons = set()


def main():
    dpy, scr, sw, sh = open_display()
    poller = select.poll()
    devs = {}          # fd -> Dev
    nodes = {}         # node_path -> fd
    last_scan = 0.0
    # aktuelle Pointer-Position fuer absolute Maus (nur Bookkeeping)

    def release_held_inputs(d):
        """Beim Hot-Unplug alle noch gedrueckten XTEST-Eingaben freigeben."""
        released = len(d.held_keys) + len(d.held_buttons)
        for code in tuple(d.held_keys):
            libXtst.XTestFakeKeyEvent(dpy, code + 8, 0, 0)
        for button in tuple(d.held_buttons):
            libXtst.XTestFakeButtonEvent(dpy, button, 0, 0)
        if released:
            libX11.XFlush(dpy)
            log("%d gehaltene Eingabe(n) freigegeben (%s)" % (released, d.name))
        d.held_keys.clear()
        d.held_buttons.clear()

    def close_node(node):
        fd = nodes.pop(node, None)
        if fd is None:
            return
        d = devs.pop(fd, None)
        if d:
            release_held_inputs(d)
        try:
            poller.unregister(fd)
        except Exception:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        if d:
            log("Geraet weg: %s (%s)" % (node, d.name))

    def open_node(node, kind, name):
        try:
            fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            log("konnte %s nicht oeffnen: %s" % (node, e))
            return
        abs_range = None
        if kind == KIND_ABS:
            minx, maxx = get_abs_range(fd, ABS_X)
            miny, maxy = get_abs_range(fd, ABS_Y)
            abs_range = (minx, maxx, miny, maxy)
        d = Dev(fd, kind, name, abs_range)
        if kind == KIND_ABS:
            # Aktuelle Aufloesung EINMAL beim Oeffnen frisch lesen (folgt der vom
            # User eingestellten Aufloesung; kein Hintergrund-Polling noetig).
            ssz = live_screen_size(dpy) or (sw, sh)
            d.screen_w, d.screen_h = ssz
            d.abs_x, d.abs_y = d.screen_w // 2, d.screen_h // 2   # Startpunkt Bildmitte
        devs[fd] = d
        nodes[node] = fd
        poller.register(fd, select.POLLIN)
        log("Geraet an: %s -> %s (%s)" % (node, kind, name))

    def rescan():
        current = discover()
        for node, (kind, name) in current.items():
            if node not in nodes:
                open_node(node, kind, name)
        for node in list(nodes.keys()):
            if node not in current:
                close_node(node)

    def handle_event(d, etype, code, value):
        if etype == EV_REL:
            if code == REL_X and value:
                libXtst.XTestFakeRelativeMotionEvent(dpy, int(value), 0, 0)
            elif code == REL_Y and value:
                libXtst.XTestFakeRelativeMotionEvent(dpy, 0, int(value), 0)
            elif code == REL_WHEEL and value:
                btn = 4 if value > 0 else 5
                for _ in range(abs(int(value))):
                    libXtst.XTestFakeButtonEvent(dpy, btn, 1, 0)
                    libXtst.XTestFakeButtonEvent(dpy, btn, 0, 0)
            elif code == REL_HWHEEL and value:
                btn = 7 if value > 0 else 6
                for _ in range(abs(int(value))):
                    libXtst.XTestFakeButtonEvent(dpy, btn, 1, 0)
                    libXtst.XTestFakeButtonEvent(dpy, btn, 0, 0)
            else:
                return
            libX11.XFlush(dpy)
        elif etype == EV_ABS:
            if d.abs_range is None:
                return
            minx, maxx, miny, maxy = d.abs_range
            # XTestFakeMotionEvent kennt kein "-1 = Achse beibehalten" -> beide
            # Achsen mitfuehren und immer vollstaendige (x,y) senden.
            sw_d = d.screen_w or sw
            sh_d = d.screen_h or sh
            if code == ABS_X:
                d.abs_x = int((value - minx) * (sw_d - 1) / max(1, (maxx - minx)))
            elif code == ABS_Y:
                d.abs_y = int((value - miny) * (sh_d - 1) / max(1, (maxy - miny)))
            else:
                return
            libXtst.XTestFakeMotionEvent(dpy, scr, d.abs_x, d.abs_y, 0)
            libX11.XFlush(dpy)
        elif etype == EV_KEY:
            press = 1 if value else 0            # value 2 (autorepeat) -> press
            if code in BTN_MAP:
                button = BTN_MAP[code]
                if press:
                    d.held_buttons.add(button)
                else:
                    d.held_buttons.discard(button)
                libXtst.XTestFakeButtonEvent(dpy, button, press, 0)
                libX11.XFlush(dpy)
            elif code < 0x100:                   # Tastatur-Key
                if press:
                    d.held_keys.add(code)
                else:
                    d.held_keys.discard(code)
                libXtst.XTestFakeKeyEvent(dpy, code + 8, press, 0)
                libX11.XFlush(dpy)

    log("Bridge laeuft. Suche passthrough-Geraete ...")
    rescan()
    last_scan = time.time()

    while True:
        events = poller.poll(1000)
        now = time.time()
        if now - last_scan >= 1.0:
            rescan()
            last_scan = now
        for fd, mask in events:
            d = devs.get(fd)
            if d is None:
                continue
            try:
                data = os.read(fd, EV_SIZE * 64)
            except OSError:
                # Geraet verschwunden -> beim naechsten rescan aufgeraeumt
                for node, nfd in list(nodes.items()):
                    if nfd == fd:
                        close_node(node)
                continue
            if not data:
                continue
            d.buf += data
            while len(d.buf) >= EV_SIZE:
                chunk = d.buf[:EV_SIZE]
                d.buf = d.buf[EV_SIZE:]
                _sec, _usec, etype, code, value = struct.unpack(EV_FMT, chunk)
                if etype in (EV_SYN, EV_MSC):
                    continue
                handle_event(d, etype, code, value)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

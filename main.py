#!/usr/bin/env python3
"""
RS Launcher – Ana giriş noktası.
CraftRise ve SonOyuncu launcher'larını GE-Proton ile Linux'ta çalıştırır.
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw

from ui.window import MainWindow


class RSLauncherApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.rslauncher.app")

    def do_activate(self):
        win = MainWindow(self)
        win.present()


def main():
    app = RSLauncherApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

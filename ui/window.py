"""
RS Launcher – Ana pencere.
Basit tasarım: İki oyun kartı + oyna butonları + log paneli.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GLib, Pango

from core.paths import GAMES, exe_exists, proton_exists, find_proton_executable
from core.downloader import DownloadManager, download_exe, download_proton_ge
from core.proton_runner import run_game, kill_game, reset_prefix


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="RS Launcher")
        self.set_default_size(500, 520)
        self.set_resizable(False)

        self._dm = DownloadManager()
        self._running_proc = None
        self._running_game: str | None = None

        # ── Ana kutu ──────────────────────────────────────────
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        # ── Header Bar ────────────────────────────────────────
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="RS Launcher"))
        root.append(header)

        # ── İçerik ────────────────────────────────────────────
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=16,
            margin_bottom=16,
            margin_start=20,
            margin_end=20,
        )
        root.append(content)

        # ── Oyun butonları (yan yana) ─────────────────────────
        games_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=16,
            homogeneous=True,
        )
        content.append(games_box)

        self._buttons: dict[str, Gtk.Button] = {}
        self._stop_buttons: dict[str, Gtk.Button] = {}

        for game_id, cfg in GAMES.items():
            card = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=8,
            )
            card.set_hexpand(True)

            # Oyun adı
            label = Gtk.Label(label=cfg["name"])
            label.add_css_class("title-2")
            card.append(label)

            # Oyna butonu
            btn = Gtk.Button(label="Oyna")
            btn.add_css_class("suggested-action")
            btn.add_css_class("pill")
            btn.set_hexpand(True)
            btn.connect("clicked", self._on_play_clicked, game_id)
            card.append(btn)

            # Durdur butonu (kırmızı, başlangıçta gizli)
            stop_btn = Gtk.Button(label="Durdur")
            stop_btn.add_css_class("destructive-action")
            stop_btn.add_css_class("pill")
            stop_btn.set_hexpand(True)
            stop_btn.set_visible(False)
            stop_btn.connect("clicked", self._on_stop_clicked, game_id)
            card.append(stop_btn)

            # Reset prefix butonu
            reset_btn = Gtk.Button(label="Prefix Sıfırla")
            reset_btn.add_css_class("flat")
            reset_btn.connect("clicked", self._on_reset_clicked, game_id)
            card.append(reset_btn)

            self._buttons[game_id] = btn
            self._stop_buttons[game_id] = stop_btn
            games_box.append(card)

        # ── Durum etiketi ─────────────────────────────────────
        self._status_label = Gtk.Label(label="Hazır")
        self._status_label.add_css_class("dim-label")
        self._status_label.set_halign(Gtk.Align.START)
        content.append(self._status_label)

        # ── Progress bar ──────────────────────────────────────
        self._progress = Gtk.ProgressBar()
        self._progress.set_show_text(True)
        self._progress.set_visible(False)
        content.append(self._progress)

        # ── Log paneli ────────────────────────────────────────
        log_label = Gtk.Label(label="Log")
        log_label.add_css_class("heading")
        log_label.set_halign(Gtk.Align.START)
        content.append(log_label)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(180)
        scroll.add_css_class("card")
        content.append(scroll)

        self._log_view = Gtk.TextView()
        self._log_view.set_editable(False)
        self._log_view.set_cursor_visible(False)
        self._log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_view.set_monospace(True)
        self._log_view.set_top_margin(8)
        self._log_view.set_bottom_margin(8)
        self._log_view.set_left_margin(8)
        self._log_view.set_right_margin(8)
        scroll.set_child(self._log_view)

        self._log_buf = self._log_view.get_buffer()
        self._scroll = scroll

    # ── Log yardımcıları ──────────────────────────────────────
    def _log(self, text: str) -> None:
        """Thread-safe log ekleme."""
        GLib.idle_add(self._log_append_ui, text)

    def _log_append_ui(self, text: str) -> bool:
        end_iter = self._log_buf.get_end_iter()
        self._log_buf.insert(end_iter, text)
        # Scroll aşağı
        mark = self._log_buf.create_mark(None, self._log_buf.get_end_iter(), False)
        self._log_view.scroll_mark_onscreen(mark)
        self._log_buf.delete_mark(mark)
        return False

    def _set_status(self, text: str) -> None:
        GLib.idle_add(self._status_label.set_label, text)

    def _set_progress(self, fraction: float, text: str) -> None:
        def _update():
            self._progress.set_visible(True)
            if fraction < 0:
                self._progress.pulse()
            else:
                self._progress.set_fraction(min(fraction / 100.0, 1.0))
            self._progress.set_text(text)
            return False
        GLib.idle_add(_update)

    def _hide_progress(self) -> None:
        GLib.idle_add(self._progress.set_visible, False)

    def _set_buttons_sensitive(self, sensitive: bool) -> None:
        def _update():
            for btn in self._buttons.values():
                btn.set_sensitive(sensitive)
            return False
        GLib.idle_add(_update)

    def _show_stop_button(self, game_id: str, visible: bool) -> None:
        def _update():
            self._stop_buttons[game_id].set_visible(visible)
            return False
        GLib.idle_add(_update)

    # ── Oyna butonu ───────────────────────────────────────────
    def _on_play_clicked(self, button: Gtk.Button, game_id: str) -> None:
        if self._dm.is_busy:
            self._log(f"[!] Şu anda başka bir işlem devam ediyor: {self._dm.current_task}\n")
            return

        self._set_buttons_sensitive(False)
        cfg = GAMES[game_id]
        self._log(f"\n{'='*40}\n{cfg['name']} başlatılıyor…\n{'='*40}\n")

        def _task():
            # 1. EXE kontrolü / indirme
            if not exe_exists(game_id):
                self._log(f"{cfg['name']} EXE indiriliyor…\n")
                download_exe(game_id, progress=self._progress_cb)
                self._hide_progress()

            # 2. Proton GE kontrolü / indirme
            if not proton_exists():
                self._log("GE-Proton indiriliyor…\n")
                download_proton_ge(progress=self._progress_cb)
                self._hide_progress()

            # 3. Çalıştır
            self._set_status(f"{cfg['name']} çalışıyor…")
            self._log(f"{cfg['name']} Proton ile başlatılıyor…\n")

            self._running_game = game_id
            self._show_stop_button(game_id, True)
            self._running_proc = run_game(
                game_id,
                on_output=self._log,
                on_exit=lambda code: self._on_game_exit(game_id, code),
            )

        def _on_done():
            pass  # run_game kendi thread'ini yönetir

        def _on_error(exc: Exception):
            self._log(f"[HATA] {exc}\n")
            self._set_status("Hata oluştu")
            self._hide_progress()
            self._set_buttons_sensitive(True)

        started = self._dm.run_in_thread(
            task_name=cfg["name"],
            target=_task,
            on_done=_on_done,
            on_error=_on_error,
        )

        if not started:
            self._log("[!] Başka bir indirme zaten devam ediyor.\n")
            self._set_buttons_sensitive(True)

    def _on_game_exit(self, game_id: str, code: int) -> None:
        cfg = GAMES[game_id]
        self._running_proc = None
        self._running_game = None
        self._show_stop_button(game_id, False)
        self._set_status(f"{cfg['name']} kapandı (kod: {code})")
        self._set_buttons_sensitive(True)

    # ── Durdur butonu ─────────────────────────────────────────
    def _on_stop_clicked(self, button: Gtk.Button, game_id: str) -> None:
        cfg = GAMES[game_id]
        if self._running_proc is not None:
            self._log(f"{cfg['name']} durduruluyor (tüm process'ler)…\n")
            kill_game(self._running_proc, game_id)
            self._set_status(f"{cfg['name']} durduruldu")
        else:
            self._log(f"{cfg['name']} zaten çalışmıyor.\n")

    def _progress_cb(self, pct: float, msg: str) -> None:
        self._set_progress(pct, msg)
        self._set_status(msg)

    # ── Prefix sıfırlama ─────────────────────────────────────
    def _on_reset_clicked(self, button: Gtk.Button, game_id: str) -> None:
        cfg = GAMES[game_id]

        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=f"{cfg['name']} Prefix Sıfırla",
            body=f"{cfg['name']} için Wine prefix'i silinecek. Emin misiniz?",
        )
        dialog.add_response("cancel", "İptal")
        dialog.add_response("reset", "Sıfırla")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_reset_response, game_id)
        dialog.present()

    def _on_reset_response(self, dialog: Adw.MessageDialog, response: str, game_id: str) -> None:
        if response == "reset":
            cfg = GAMES[game_id]
            ok = reset_prefix(game_id)
            if ok:
                self._log(f"{cfg['name']} prefix sıfırlandı.\n")
                self._set_status(f"{cfg['name']} prefix sıfırlandı")
            else:
                self._log(f"{cfg['name']} prefix zaten boş.\n")

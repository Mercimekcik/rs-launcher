"""
RS Launcher – Ana pencere (yeniden tasarlanmış).
GTK4 / libadwaita modern UI: ToastOverlay, ActionRow, PreferencesGroup, Clamp, CSS.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GLib

from core.paths import GAMES, exe_exists, proton_exists, find_proton_executable
from core.downloader import DownloadManager, download_exe, download_proton_ge
from core.proton_runner import run_game, kill_game, reset_prefix, open_winecfg, open_resourcepacks

# ── CSS ──────────────────────────────────────────────────────────────────────
_CSS = b"""
.game-card {
    background-color: alpha(@card_bg_color, 0.55);
    border-radius: 16px;
    border: 1px solid alpha(@borders, 0.35);
    padding: 16px 14px;
}
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="RS Launcher")
        self.set_default_size(500, 720)
        self.set_resizable(True)

        # CSS yükle
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self._dm = DownloadManager()
        self._running_proc = None
        self._running_game: str | None = None

        # ── Kök kutu ──────────────────────────────────────────
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        # ── Header Bar ────────────────────────────────────────
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="RS Launcher"))
        root.append(header)

        # ── Toast Overlay ─────────────────────────────────────
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_vexpand(True)
        root.append(self._toast_overlay)

        # ── ScrolledWindow ────────────────────────────────────
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self._toast_overlay.set_child(scrolled)

        # ── Adw.Clamp – içerik genişliğini sınırlar ───────────
        clamp = Adw.Clamp()
        clamp.set_maximum_size(520)
        clamp.set_tightening_threshold(480)
        scrolled.set_child(clamp)

        # ── Ana içerik kutusu ─────────────────────────────────
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=16,
            margin_bottom=24,
            margin_start=16,
            margin_end=16,
        )
        clamp.set_child(content)

        # ── Oyun kartları (Oyna / Durdur) ─────────────────────
        games_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            homogeneous=True,
        )
        content.append(games_box)

        self._buttons: dict[str, Gtk.Button] = {}
        self._stop_buttons: dict[str, Gtk.Button] = {}

        for game_id, cfg in GAMES.items():
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            card.add_css_class("game-card")
            card.set_hexpand(True)

            lbl = Gtk.Label(label=cfg["name"])
            lbl.add_css_class("title-2")
            card.append(lbl)

            btn = Gtk.Button(label="Oyna")
            btn.add_css_class("suggested-action")
            btn.add_css_class("pill")
            btn.set_hexpand(True)
            btn.connect("clicked", self._on_play_clicked, game_id)
            card.append(btn)

            stop_btn = Gtk.Button(label="Durdur")
            stop_btn.add_css_class("destructive-action")
            stop_btn.add_css_class("pill")
            stop_btn.set_hexpand(True)
            stop_btn.set_visible(False)
            stop_btn.connect("clicked", self._on_stop_clicked, game_id)
            card.append(stop_btn)

            self._buttons[game_id] = btn
            self._stop_buttons[game_id] = stop_btn
            games_box.append(card)

        # ── Durum etiketi + Progress bar ──────────────────────
        self._status_label = Gtk.Label(label="Hazır")
        self._status_label.add_css_class("dim-label")
        self._status_label.set_halign(Gtk.Align.START)
        content.append(self._status_label)

        self._progress = Gtk.ProgressBar()
        self._progress.set_show_text(True)
        self._progress.set_visible(False)
        content.append(self._progress)

        # ── Araç grupları (PreferencesGroup + ActionRow) ──────
        for game_id, cfg in GAMES.items():
            group = Adw.PreferencesGroup(title=f"{cfg['name']} Araçları")
            content.append(group)

            # WineCFG
            winecfg_row = Adw.ActionRow(
                title="WineCFG",
                subtitle="Wine ayarlarını yapılandır",
            )
            winecfg_btn = Gtk.Button(label="Aç")
            winecfg_btn.add_css_class("flat")
            winecfg_btn.set_valign(Gtk.Align.CENTER)
            winecfg_btn.connect("clicked", self._on_winecfg_clicked, game_id)
            winecfg_row.add_suffix(winecfg_btn)
            winecfg_row.set_activatable_widget(winecfg_btn)
            group.add(winecfg_row)

            # Kaynak Paketleri
            rp_row = Adw.ActionRow(
                title="Kaynak Paketleri",
                subtitle="Klasörü sistem dosya yöneticisinde aç",
            )
            rp_btn = Gtk.Button(label="Aç")
            rp_btn.add_css_class("flat")
            rp_btn.set_valign(Gtk.Align.CENTER)
            rp_btn.connect("clicked", self._on_resourcepacks_clicked, game_id)
            rp_row.add_suffix(rp_btn)
            rp_row.set_activatable_widget(rp_btn)
            group.add(rp_row)

            # Prefix Sıfırla
            reset_row = Adw.ActionRow(
                title="Prefix Sıfırla",
                subtitle="Wine ortamını sıfırdan oluştur",
            )
            reset_btn = Gtk.Button(label="Sıfırla")
            reset_btn.add_css_class("flat")
            reset_btn.add_css_class("destructive-action")
            reset_btn.set_valign(Gtk.Align.CENTER)
            reset_btn.connect("clicked", self._on_reset_clicked, game_id)
            reset_row.add_suffix(reset_btn)
            reset_row.set_activatable_widget(reset_btn)
            group.add(reset_row)

        # ── Log alanı ─────────────────────────────────────────
        log_header = Gtk.Label(label="Log")
        log_header.add_css_class("heading")
        log_header.set_halign(Gtk.Align.START)
        log_header.set_margin_top(4)
        content.append(log_header)

        scroll_log = Gtk.ScrolledWindow()
        scroll_log.set_min_content_height(180)
        scroll_log.add_css_class("card")
        content.append(scroll_log)

        self._log_view = Gtk.TextView()
        self._log_view.set_editable(False)
        self._log_view.set_cursor_visible(False)
        self._log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_view.set_monospace(True)
        self._log_view.set_top_margin(8)
        self._log_view.set_bottom_margin(8)
        self._log_view.set_left_margin(8)
        self._log_view.set_right_margin(8)
        scroll_log.set_child(self._log_view)

        self._log_buf = self._log_view.get_buffer()
        self._scroll_log = scroll_log

    # ── Toast ──────────────────────────────────────────────────
    def _toast(self, message: str) -> None:
        GLib.idle_add(self._toast_ui, message)

    def _toast_ui(self, message: str) -> bool:
        toast = Adw.Toast(title=message)
        self._toast_overlay.add_toast(toast)
        return False

    # ── Log yardımcıları ───────────────────────────────────────
    def _log(self, text: str) -> None:
        GLib.idle_add(self._log_append_ui, text)

    def _log_append_ui(self, text: str) -> bool:
        end_iter = self._log_buf.get_end_iter()
        self._log_buf.insert(end_iter, text)
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
            if not exe_exists(game_id):
                self._log(f"{cfg['name']} EXE indiriliyor…\n")
                download_exe(game_id, progress=self._progress_cb)
                self._hide_progress()

            if not proton_exists():
                self._log("GE-Proton indiriliyor…\n")
                download_proton_ge(progress=self._progress_cb)
                self._hide_progress()

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
            pass

        def _on_error(exc: Exception):
            self._log(f"[HATA] {exc}\n")
            self._set_status("Hata oluştu")
            self._hide_progress()
            self._set_buttons_sensitive(True)
            self._toast(f"Hata: {exc}")

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
        self._toast(f"{cfg['name']} kapandı")

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

    # ── Prefix sıfırlama ──────────────────────────────────────
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
                self._toast(f"{cfg['name']} prefix sıfırlandı")
            else:
                self._log(f"{cfg['name']} prefix zaten boş.\n")
                self._toast(f"{cfg['name']} prefix zaten boş")

    # ── WineCFG ───────────────────────────────────────────────
    def _on_winecfg_clicked(self, button: Gtk.Button, game_id: str) -> None:
        cfg = GAMES[game_id]
        if not proton_exists():
            self._log("[HATA] Proton GE bulunamadı. Önce oyunu indirin.\n")
            self._toast("Proton GE bulunamadı!")
            return
        self._log(f"{cfg['name']} için WineCFG açılıyor…\n")
        open_winecfg(game_id, on_output=self._log)
        self._toast(f"{cfg['name']} WineCFG başlatıldı")

    # ── Kaynak Paketleri ──────────────────────────────────────
    def _on_resourcepacks_clicked(self, button: Gtk.Button, game_id: str) -> None:
        cfg = GAMES[game_id]
        self._log(f"{cfg['name']} kaynak paketi klasörü açılıyor…\n")
        open_resourcepacks(game_id, on_output=self._log)
        self._toast(f"{cfg['name']} kaynak paketi klasörü açıldı")

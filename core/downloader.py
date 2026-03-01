"""
RS Launcher – EXE ve Proton GE indirme modülü.
Thread-safe indirme, progress callback ile UI güncelleme.
"""

import json
import os
import shutil
import tarfile
import tempfile
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable

from core.paths import (
    GAMES,
    PROTON_GE_API,
    get_exe_path,
    get_proton_dir,
)

# Callback tipleri
ProgressCB = Callable[[float, str], None]   # (yüzde 0-100, mesaj)


def _download_file(url: str, dest: Path, progress: ProgressCB | None = None) -> None:
    """Bir URL'yi diske indirir, progress callback çağırır."""
    req = urllib.request.Request(url, headers={"User-Agent": "RS-Launcher/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 256 * 1024  # 256 KB

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fp:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                fp.write(chunk)
                downloaded += len(chunk)
                if progress and total > 0:
                    pct = downloaded / total * 100
                    progress(pct, f"İndiriliyor: {downloaded // 1024} / {total // 1024} KB")
                elif progress:
                    progress(-1, f"İndiriliyor: {downloaded // 1024} KB")

    if progress:
        progress(100, "İndirme tamamlandı.")


def download_exe(game_id: str, progress: ProgressCB | None = None) -> Path:
    """
    Oyun EXE'sini indir.
    Zaten mevcutsa doğrudan yolu döner.
    """
    cfg = GAMES[game_id]
    dest = get_exe_path(game_id)

    if dest.is_file():
        if progress:
            progress(100, f"{cfg['name']} zaten mevcut.")
        return dest

    if progress:
        progress(0, f"{cfg['name']} indiriliyor…")

    _download_file(cfg["exe_url"], dest, progress)
    return dest


def _fetch_latest_proton_url() -> tuple[str, str]:
    """GitHub API'den GE-Proton latest release tar.gz URL ve tag_name döner."""
    req = urllib.request.Request(
        PROTON_GE_API,
        headers={"User-Agent": "RS-Launcher/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    tag = data["tag_name"]
    for asset in data["assets"]:
        name = asset["name"]
        if name.endswith(".tar.gz"):
            return asset["browser_download_url"], tag

    raise RuntimeError("GE-Proton .tar.gz release bulunamadı.")


def download_proton_ge(progress: ProgressCB | None = None) -> Path:
    """
    GE-Proton'u indir ve aç.
    Zaten mevcutsa doğrudan path döner.
    """
    proton_dir = get_proton_dir()

    # Mevcut kurulumu kontrol et
    for child in proton_dir.iterdir():
        candidate = child / "proton"
        if candidate.is_file():
            if progress:
                progress(100, f"Proton GE zaten mevcut: {child.name}")
            return candidate

    if progress:
        progress(0, "GE-Proton sürümü sorgulanıyor…")

    url, tag = _fetch_latest_proton_url()

    if progress:
        progress(5, f"{tag} indiriliyor…")

    # Geçici dosyaya indir
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        _download_file(url, tmp_path, progress)

        if progress:
            progress(95, "Arşiv açılıyor…")

        with tarfile.open(tmp_path, "r:gz") as tar:
            tar.extractall(path=proton_dir)

    finally:
        tmp_path.unlink(missing_ok=True)

    # Doğrula
    for child in sorted(proton_dir.iterdir(), reverse=True):
        candidate = child / "proton"
        if candidate.is_file():
            if progress:
                progress(100, f"{child.name} hazır.")
            return candidate

    raise RuntimeError("Proton GE çıkarıldı ama proton çalıştırılabilir dosyası bulunamadı.")


class DownloadManager:
    """
    Aynı anda yalnızca bir indirme işlemi yapılmasını sağlar.
    Thread-safe kilit mekanizması ile çalışır.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._busy = False
        self._current_task: str | None = None

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def current_task(self) -> str | None:
        return self._current_task

    def run_in_thread(
        self,
        task_name: str,
        target: Callable,
        args: tuple = (),
        on_done: Callable | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> bool:
        """
        Verilen fonksiyonu ayrı bir thread'de çalıştırır.
        Eğer zaten bir iş çalışıyorsa False döner.
        """
        if not self._lock.acquire(blocking=False):
            return False

        self._busy = True
        self._current_task = task_name

        def _worker():
            try:
                target(*args)
                if on_done:
                    on_done()
            except Exception as exc:
                if on_error:
                    on_error(exc)
            finally:
                self._busy = False
                self._current_task = None
                self._lock.release()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return True

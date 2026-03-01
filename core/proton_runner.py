"""
RS Launcher – Proton GE ile EXE çalıştırma modülü.
Her oyun için ayrı prefix kullanılır.
"""

import os
import signal
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

from core.paths import (
    find_proton_executable,
    get_exe_path,
    get_prefix_dir,
    get_proton_dir,
    exe_exists,
)

OutputCB = Callable[[str], None]


def _build_env(game_id: str, proton_path: Path) -> dict[str, str]:
    """Proton çalıştırma için gerekli ortam değişkenlerini döner."""
    env = os.environ.copy()
    prefix = get_prefix_dir(game_id)

    env["STEAM_COMPAT_DATA_PATH"] = str(prefix)
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(prefix)
    # Proton'un steam shim'e ihtiyaç duymaması için
    env["STEAM_COMPAT_TOOL_PATHS"] = str(proton_path.parent)
    # DXVK / VKD3D uyumluluk
    env["WINEESYNC"] = "1"
    env["WINEFSYNC"] = "1"
    env["PROTON_NO_ESYNC"] = "0"
    env["PROTON_NO_FSYNC"] = "0"

    return env


def run_game(
    game_id: str,
    on_output: OutputCB | None = None,
    on_exit: Callable[[int], None] | None = None,
) -> subprocess.Popen | None:
    """
    Oyun EXE'sini Proton GE ile çalıştırır.
    Subprocess döner, veya hata varsa None.
    """
    proton = find_proton_executable()
    if proton is None:
        if on_output:
            on_output("[HATA] Proton GE bulunamadı. Önce indirin.\n")
        return None

    exe = get_exe_path(game_id)
    if not exe.is_file():
        if on_output:
            on_output(f"[HATA] {exe.name} bulunamadı. Önce indirin.\n")
        return None

    env = _build_env(game_id, proton)
    cmd = [str(proton), "run", str(exe)]

    if on_output:
        on_output(f"Çalıştırılıyor: {' '.join(cmd)}\n")
        on_output(f"Prefix: {get_prefix_dir(game_id)}\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(exe.parent),
        start_new_session=True,  # yeni process group oluştur
    )

    def _reader():
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, b""):
            text = line.decode("utf-8", errors="replace")
            if on_output:
                on_output(text)
        proc.wait()
        if on_output:
            on_output(f"\n[Çıkış kodu: {proc.returncode}]\n")
        if on_exit:
            on_exit(proc.returncode)

    threading.Thread(target=_reader, daemon=True).start()
    return proc


def kill_game(proc: subprocess.Popen, game_id: str) -> None:
    """
    Proton ile başlatılmış tüm process'leri öldürür.
    wineserver --kill ile o prefix'teki tüm Wine process'lerini kapatır.
    """
    # 1. wineserver --kill (en güvenilir yol)
    proton = find_proton_executable()
    if proton is not None:
        # GE-Proton/files/bin/wineserver
        wineserver = proton.parent / "files" / "bin" / "wineserver"
        if wineserver.is_file():
            prefix = get_prefix_dir(game_id) / "pfx"
            env = os.environ.copy()
            env["WINEPREFIX"] = str(prefix)
            try:
                subprocess.run(
                    [str(wineserver), "--kill"],
                    env=env,
                    timeout=10,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    # 2. Fallback: process group kill
    if proc.poll() is None:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    # 3. Son çare: doğrudan kill
    if proc.poll() is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def reset_prefix(game_id: str) -> bool:
    """Oyunun prefix klasörünü siler. Başarılıysa True döner."""
    prefix = get_prefix_dir(game_id)
    if prefix.exists():
        shutil.rmtree(prefix)
        return True
    return False

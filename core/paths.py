"""
RS Launcher – Path yönetimi ve oyun konfigürasyonu.
Tüm veri ~/.local/share/rs-launcher/ altında tutulur.
"""

import os
from pathlib import Path

# ── Veri dizini ───────────────────────────────────────────────
DATA_DIR = Path(os.environ.get(
    "RS_LAUNCHER_DATA",
    Path.home() / ".local" / "share" / "rs-launcher",
))

# ── Oyun tanımları ────────────────────────────────────────────
GAMES = {
    "craftrise": {
        "name": "CraftRise",
        "exe_url": "https://www.craftrise.com.tr/launcher/CraftRise.exe",
        "exe_name": "CraftRise.exe",
        # C:\users\steamuser\AppData\Roaming\.craftrise\resourcepacks
        "resourcepacks_win_path": ["users", "steamuser", "AppData", "Roaming", ".craftrise", "resourcepacks"],
    },
    "sonoyuncu": {
        "name": "SonOyuncu",
        "exe_url": "https://launcher.sonoyuncu.network/launcher/indir/x32/SonOyuncu%20Client.exe",
        "exe_name": "SonOyuncu Client.exe",
        # C:\users\steamuser\AppData\Roaming\.sonoyuncu\resourcepacks
        "resourcepacks_win_path": ["users", "steamuser", "AppData", "Roaming", ".sonoyuncu", "resourcepacks"],
    },
}

# ── GE-Proton ─────────────────────────────────────────────────
PROTON_GE_API = (
    "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
)


# ── Yardımcı fonksiyonlar ─────────────────────────────────────
def get_data_dir() -> Path:
    """Ana veri dizinini döndürür, yoksa oluşturur."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_game_dir(game_id: str) -> Path:
    """Oyun dizinini döndürür (prefix + exe burada)."""
    d = get_data_dir() / game_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_prefix_dir(game_id: str) -> Path:
    """Oyun için Wine/Proton prefix dizini."""
    d = get_game_dir(game_id) / "prefix"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_exe_path(game_id: str) -> Path:
    """Oyun EXE dosyasının tam yolu."""
    cfg = GAMES[game_id]
    return get_game_dir(game_id) / cfg["exe_name"]


def get_proton_dir() -> Path:
    """Proton GE'nin tutulduğu dizin."""
    d = get_data_dir() / "proton-ge"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_proton_executable() -> Path | None:
    """
    proton-ge/ altındaki ilk GE-Proton*/proton dosyasını bulur.
    Bulamazsa None döner.
    """
    proton_dir = get_proton_dir()
    for child in sorted(proton_dir.iterdir(), reverse=True):
        candidate = child / "proton"
        if candidate.is_file():
            return candidate
    return None


def exe_exists(game_id: str) -> bool:
    return get_exe_path(game_id).is_file()


def proton_exists() -> bool:
    return find_proton_executable() is not None


def get_resourcepacks_path(game_id: str) -> Path:
    """Oyunun Wine prefix'indeki kaynak paketi klasörünün Linux yolunu döner."""
    cfg = GAMES[game_id]
    base = get_prefix_dir(game_id) / "pfx" / "drive_c"
    for part in cfg["resourcepacks_win_path"]:
        base = base / part
    return base

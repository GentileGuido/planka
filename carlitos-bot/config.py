"""Configuration — loads environment variables."""

import os


TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "")
PLANKA_URL: str = os.environ.get("PLANKA_URL", "http://localhost:1337").rstrip("/")
PLANKA_EMAIL: str = os.environ.get("PLANKA_EMAIL", "")
PLANKA_PASSWORD: str = os.environ.get("PLANKA_PASSWORD", "")
ALLOWED_USER_ID: int = int(os.environ.get("ALLOWED_USER_ID", "0"))

# Project name → expected column names (in display order)
PROJECT_COLUMNS: dict[str, list[str]] = {
    "NUDO - Tareas": ["Por hacer", "En progreso", "Listo"],
    "Personal": ["Por hacer", "En progreso", "Listo"],
    "Sesiones de Dibujo": ["Por hacer", "En progreso", "Listo"],
    "G-VIBE-C Ideas (Backlog)": ["Idea", "Investigando", "Validada", "Descartada"],
}

# Short labels for inline keyboard buttons  (callback_data → project name)
PROJECT_BUTTONS: list[tuple[str, str]] = [
    ("NUDO", "NUDO - Tareas"),
    ("Personal", "Personal"),
    ("Dibujo", "Sesiones de Dibujo"),
    ("G-VIBE-C", "G-VIBE-C Ideas (Backlog)"),
]

# Column display emoji
COLUMN_EMOJI: dict[str, str] = {
    "Por hacer": "📋",
    "En progreso": "🔨",
    "Listo": "✅",
    "Idea": "💡",
    "Investigando": "🔍",
    "Validada": "✅",
    "Descartada": "❌",
}

# Hashtag → project name  (kept for /tarea quick syntax)
TAG_TO_PROJECT: dict[str, str] = {
    "#nudo": "NUDO - Tareas",
    "#personal": "Personal",
    "#dibujo": "Sesiones de Dibujo",
    "#gvibe": "G-VIBE-C Ideas (Backlog)",
}

# Shorthand column aliases for /mover
COLUMN_ALIASES: dict[str, str] = {
    "hacer": "Por hacer",
    "progreso": "En progreso",
    "listo": "Listo",
    "idea": "Idea",
    "investigando": "Investigando",
    "validada": "Validada",
    "descartada": "Descartada",
}

# Priority tags
PRIORITIES: dict[str, str] = {
    "!baja": "🟢 Baja",
    "!media": "🟡 Media",
    "!alta": "🟠 Alta",
    "!urgente": "🔴 Urgente",
}

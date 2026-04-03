"""CarlitosAsist — Telegram bot for managing Planka tasks."""

from __future__ import annotations

import logging

from telegram.ext import Application, CommandHandler

from config import TELEGRAM_TOKEN
from handlers import (
    cmd_start,
    cmd_tarea,
    cmd_idea,
    cmd_hoy,
    cmd_nudo,
    cmd_personal,
    cmd_dibujo,
    cmd_log,
    cmd_mover,
    cmd_done,
    cmd_resumen,
)

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN no configurado.")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("idea", cmd_idea))
    app.add_handler(CommandHandler("hoy", cmd_hoy))
    app.add_handler(CommandHandler("nudo", cmd_nudo))
    app.add_handler(CommandHandler("personal", cmd_personal))
    app.add_handler(CommandHandler("dibujo", cmd_dibujo))
    app.add_handler(CommandHandler("log", cmd_log))
    app.add_handler(CommandHandler("mover", cmd_mover))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("resumen", cmd_resumen))

    logger.info("CarlitosAsist conectado 🤖")
    app.run_polling()


if __name__ == "__main__":
    main()

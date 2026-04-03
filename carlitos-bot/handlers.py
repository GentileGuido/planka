"""Telegram command + conversation handlers for CarlitosAsist."""

from __future__ import annotations

import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import (
    ALLOWED_USER_ID,
    TAG_TO_PROJECT,
    COLUMN_ALIASES,
    COLUMN_EMOJI,
    PRIORITIES,
    PROJECT_BUTTONS,
    PROJECT_COLUMNS,
)
from planka_client import PlankaClient, PlankaError

logger = logging.getLogger(__name__)

planka = PlankaClient()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _authorised(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == ALLOWED_USER_ID


async def _deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Este bot es privado.")


def _short_id(card_id: Any) -> str:
    return str(card_id)[-6:]


def _parse_tags(text: str) -> tuple[str, str | None, str | None]:
    words = text.split()
    name_parts: list[str] = []
    project: str | None = None
    priority: str | None = None
    for w in words:
        low = w.lower()
        if low in TAG_TO_PROJECT:
            project = TAG_TO_PROJECT[low]
        elif low in PRIORITIES:
            priority = PRIORITIES[low]
        else:
            name_parts.append(w)
    return " ".join(name_parts), project, priority


def _format_card_line(card: dict[str, Any], show_project: bool = False) -> str:
    cid = _short_id(card["id"])
    name = card.get("name", "Sin nombre")
    list_name = card.get("_listName", "?")
    col_emoji = COLUMN_EMOJI.get(list_name, "📌")
    line = f"  {col_emoji} `{cid}` — *{name}*  _{list_name}_"
    if show_project:
        proj = card.get("_project", "")
        line += f" ({proj})"
    return line


def _resolve_column(alias: str) -> str | None:
    alias_low = alias.lower().strip()
    if alias_low in COLUMN_ALIASES:
        return COLUMN_ALIASES[alias_low]
    for key, full in COLUMN_ALIASES.items():
        if key.startswith(alias_low):
            return full
    return None


# ------------------------------------------------------------------
# Conversational flow: plain text → pick project → pick status → done
# ------------------------------------------------------------------


async def msg_new_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any plain text message as a new task name."""
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None
    task_name = (msg.text or "").strip()
    if not task_name:
        return

    # Store the task name for the callback flow
    context.user_data["pending_task"] = task_name  # type: ignore[index]

    # Build project picker keyboard
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"proj:{proj_name}")]
        for label, proj_name in PROJECT_BUTTONS
    ]
    await msg.reply_text(
        f"*{task_name}*\n\nEn que carpeta va?",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def cb_pick_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked a project from the inline keyboard."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    proj_name = (query.data or "").removeprefix("proj:")
    task_name = context.user_data.get("pending_task")  # type: ignore[union-attr]

    if not task_name:
        await query.edit_message_text("La tarea expiro. Manda el nombre de nuevo.")
        return

    # Store chosen project
    context.user_data["pending_project"] = proj_name  # type: ignore[index]

    # Build status picker — columns for that project
    columns = PROJECT_COLUMNS.get(proj_name, ["Por hacer"])
    buttons = [
        [
            InlineKeyboardButton(
                f"{COLUMN_EMOJI.get(col, '📌')} {col}",
                callback_data=f"status:{col}",
            )
        ]
        for col in columns
    ]
    short_proj = next(
        (label for label, full in PROJECT_BUTTONS if full == proj_name), proj_name
    )
    await query.edit_message_text(
        f"*{task_name}* → _{short_proj}_\n\nQue estado?",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def cb_pick_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked a status/column — create the card."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    col_name = (query.data or "").removeprefix("status:")
    task_name = context.user_data.pop("pending_task", None)  # type: ignore[union-attr]
    proj_name = context.user_data.pop("pending_project", None)  # type: ignore[union-attr]

    if not task_name or not proj_name:
        await query.edit_message_text("La tarea expiro. Manda el nombre de nuevo.")
        return

    try:
        planka.refresh_cache()
        list_id = planka.find_list_id(proj_name, col_name)
        if not list_id:
            await query.edit_message_text(
                f"No encontre la columna *{col_name}* en *{proj_name}*.",
                parse_mode="Markdown",
            )
            return

        card = planka.create_card(list_id, task_name)
        cid = _short_id(card["id"])
        col_emoji = COLUMN_EMOJI.get(col_name, "📌")
        short_proj = next(
            (label for label, full in PROJECT_BUTTONS if full == proj_name), proj_name
        )
        await query.edit_message_text(
            f"Tarea creada {col_emoji}\n\n"
            f"📌 `{cid}` — *{task_name}*\n"
            f"📂 {short_proj} → _{col_name}_",
            parse_mode="Markdown",
        )
    except PlankaError as e:
        logger.exception("Error creando tarea")
        await query.edit_message_text(f"Error de Planka: {e}")


# ------------------------------------------------------------------
# Classic command handlers (still work)
# ------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorised(update):
        return await _deny(update)

    text = (
        "*CarlitosAsist* — tu asistente de tareas\n\n"
        "Escribi el nombre de una tarea y te pregunto donde ponerla.\n\n"
        "*Comandos rapidos:*\n"
        "/tarea `Nombre #proyecto !prioridad`\n"
        "/idea `Nombre` — idea al backlog\n"
        "/hoy — tareas activas\n"
        "/nudo /personal /dibujo — ver proyecto\n"
        "/log `ID mensaje` — comentar\n"
        "/mover `ID columna` — mover tarjeta\n"
        "/done `ID` — marcar terminada\n"
        "/resumen — resumen general\n\n"
        "Proyectos: #nudo #personal #dibujo #gvibe\n"
        "Prioridades: !baja !media !alta !urgente"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")  # type: ignore[union-attr]


async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None
    raw = msg.text or ""
    args_text = raw.split(None, 1)[1] if len(raw.split(None, 1)) > 1 else ""

    if not args_text.strip():
        await msg.reply_text("Usa: /tarea Nombre #proyecto !prioridad")
        return

    name, project, priority = _parse_tags(args_text)

    if not name.strip():
        await msg.reply_text("Falta el nombre de la tarea.")
        return

    # If no project tag, start the conversational flow instead
    if not project:
        context.user_data["pending_task"] = name  # type: ignore[index]
        buttons = [
            [InlineKeyboardButton(label, callback_data=f"proj:{proj_name}")]
            for label, proj_name in PROJECT_BUTTONS
        ]
        await msg.reply_text(
            f"*{name}*\n\nEn que carpeta va?",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )
        return

    if project == "G-VIBE-C Ideas (Backlog)":
        target_list = "Idea"
    else:
        target_list = "Por hacer"

    description = f"Prioridad: {priority}" if priority else ""

    try:
        planka.refresh_cache()
        list_id = planka.find_list_id(project, target_list)
        if not list_id:
            await msg.reply_text(
                f"No encontre la lista *{target_list}* en *{project}*.",
                parse_mode="Markdown",
            )
            return

        card = planka.create_card(list_id, name, description)
        cid = _short_id(card["id"])
        pri_text = f"\n⚡ {priority}" if priority else ""
        short_proj = next(
            (label for label, full in PROJECT_BUTTONS if full == project), project
        )
        await msg.reply_text(
            f"Tarea creada en *{short_proj}* → _{target_list}_\n"
            f"📌 `{cid}` — *{name}*{pri_text}",
            parse_mode="Markdown",
        )
    except PlankaError as e:
        logger.exception("Error creando tarea")
        await msg.reply_text(f"Error de Planka: {e}")


async def cmd_idea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None
    raw = msg.text or ""
    name = raw.split(None, 1)[1] if len(raw.split(None, 1)) > 1 else ""

    if not name.strip():
        await msg.reply_text("Usa: /idea Nombre de la idea")
        return

    project = "G-VIBE-C Ideas (Backlog)"
    try:
        planka.refresh_cache()
        list_id = planka.find_list_id(project, "Idea")
        if not list_id:
            await msg.reply_text("No encontre la lista *Idea* en el backlog.", parse_mode="Markdown")
            return

        card = planka.create_card(list_id, name)
        cid = _short_id(card["id"])
        await msg.reply_text(
            f"💡 Idea guardada en backlog\n📌 `{cid}` — *{name}*",
            parse_mode="Markdown",
        )
    except PlankaError as e:
        logger.exception("Error creando idea")
        await msg.reply_text(f"Error de Planka: {e}")


async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None

    try:
        cards = planka.get_all_active_cards()
    except PlankaError as e:
        await msg.reply_text(f"Error de Planka: {e}")
        return

    if not cards:
        await msg.reply_text("No hay tareas activas. Disfruta el dia.")
        return

    lines = ["*Tareas activas*\n"]
    by_project: dict[str, list[dict[str, Any]]] = {}
    for c in cards:
        by_project.setdefault(c["_project"], []).append(c)

    for proj, proj_cards in by_project.items():
        lines.append(f"\n📂 *{proj}*")
        for c in proj_cards:
            lines.append(_format_card_line(c))

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


async def _cmd_list_project(
    update: Update, context: ContextTypes.DEFAULT_TYPE, project_name: str
) -> None:
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None

    try:
        planka.refresh_cache()
        cards = planka.get_cards_for_project(project_name)
    except PlankaError as e:
        await msg.reply_text(f"Error de Planka: {e}")
        return

    if not cards:
        await msg.reply_text(f"No hay tarjetas en *{project_name}*.", parse_mode="Markdown")
        return

    lines = [f"📂 *{project_name}*\n"]
    by_list: dict[str, list[dict[str, Any]]] = {}
    for c in cards:
        by_list.setdefault(c["_listName"], []).append(c)

    expected_cols = PROJECT_COLUMNS.get(project_name, [])
    for col in expected_cols:
        col_cards = by_list.get(col, [])
        if col_cards:
            lines.append(f"\n*{col}*")
            for c in col_cards:
                lines.append(_format_card_line(c))

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_nudo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cmd_list_project(update, context, "NUDO - Tareas")


async def cmd_personal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cmd_list_project(update, context, "Personal")


async def cmd_dibujo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cmd_list_project(update, context, "Sesiones de Dibujo")


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None
    raw = msg.text or ""
    parts = raw.split(None, 2)

    if len(parts) < 3:
        await msg.reply_text("Usa: /log ID mensaje")
        return

    card_id = parts[1]
    comment_text = parts[2]

    try:
        planka.add_comment(card_id, comment_text)
        await msg.reply_text(f"💬 Comentario agregado a `{_short_id(card_id)}`.", parse_mode="Markdown")
    except PlankaError as e:
        logger.exception("Error agregando comentario")
        await msg.reply_text(f"Error: {e}")


async def cmd_mover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None
    raw = msg.text or ""
    parts = raw.split(None, 2)

    if len(parts) < 3:
        await msg.reply_text(
            "Usa: /mover ID columna\n"
            "Columnas: hacer, progreso, listo, idea, investigando, validada, descartada"
        )
        return

    card_id = parts[1]
    col_alias = parts[2]

    target_col = _resolve_column(col_alias)
    if not target_col:
        await msg.reply_text(
            f"Columna desconocida: *{col_alias}*\n"
            "Usa: hacer, progreso, listo, idea, investigando, validada, descartada",
            parse_mode="Markdown",
        )
        return

    try:
        planka.refresh_cache()
        card, proj_name = planka.find_card_by_id(card_id)
        if not card or not proj_name:
            await msg.reply_text(f"No encontre la tarjeta `{_short_id(card_id)}`.", parse_mode="Markdown")
            return

        list_id = planka.find_list_id(proj_name, target_col)
        if not list_id:
            await msg.reply_text(
                f"La columna *{target_col}* no existe en *{proj_name}*.",
                parse_mode="Markdown",
            )
            return

        planka.update_card(card_id, listId=list_id, position=65535)
        await msg.reply_text(
            f"Tarjeta `{_short_id(card_id)}` movida a *{target_col}* en _{proj_name}_.",
            parse_mode="Markdown",
        )
    except PlankaError as e:
        logger.exception("Error moviendo tarjeta")
        await msg.reply_text(f"Error: {e}")


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None
    raw = msg.text or ""
    parts = raw.split(None, 1)

    if len(parts) < 2:
        await msg.reply_text("Usa: /done ID")
        return

    card_id = parts[1].strip()

    try:
        planka.refresh_cache()
        card, proj_name = planka.find_card_by_id(card_id)
        if not card or not proj_name:
            await msg.reply_text(f"No encontre la tarjeta `{_short_id(card_id)}`.", parse_mode="Markdown")
            return

        done_col = "Validada" if proj_name == "G-VIBE-C Ideas (Backlog)" else "Listo"

        list_id = planka.find_list_id(proj_name, done_col)
        if not list_id:
            await msg.reply_text(f"No encontre la columna *{done_col}* en *{proj_name}*.", parse_mode="Markdown")
            return

        planka.update_card(card_id, listId=list_id, position=65535)
        await msg.reply_text(
            f"Tarjeta `{_short_id(card_id)}` marcada como *{done_col}* en _{proj_name}_.",
            parse_mode="Markdown",
        )
    except PlankaError as e:
        logger.exception("Error completando tarjeta")
        await msg.reply_text(f"Error: {e}")


async def cmd_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorised(update):
        return await _deny(update)

    msg = update.effective_message
    assert msg is not None

    try:
        planka.refresh_cache()
    except PlankaError as e:
        await msg.reply_text(f"Error de Planka: {e}")
        return

    lines = ["*Resumen general*\n"]

    for proj_name in PROJECT_COLUMNS:
        cards = planka.get_cards_for_project(proj_name)
        total = len(cards)
        if total == 0:
            lines.append(f"📂 *{proj_name}* — sin tarjetas")
            continue

        by_col: dict[str, int] = {}
        for c in cards:
            col = c.get("_listName", "?")
            by_col[col] = by_col.get(col, 0) + 1

        col_parts = " | ".join(f"{col}: {n}" for col, n in by_col.items())
        lines.append(f"📂 *{proj_name}* ({total})\n  {col_parts}")

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")

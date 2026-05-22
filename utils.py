import os
import sqlite3
import logging
import asyncio
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from telegram.ext import ContextTypes
from PIL import Image
import hashlib

# الإعدادات الأساسية
DB_FILE = "bot_stats.db"
MAX_FILE_SIZE = 70 * 1024 * 1024
DEFAULT_AUDIO_QUALITY = "192k"
COVER_CACHE = "channel_cover_cached.jpg"
CHANNEL_USERNAME = "BEXO50"

# ايدي المالك - غير هذا الرقم إلى معرفك
OWNER_ID = 8460454874  # ⚠️ غير هذا الرقم

# وضع الصيانة
MAINTENANCE_MODE = False

# إعدادات متقدمة جديدة
MAX_CONCURRENT_TASKS = 3  # عدد المعالجات المتزامنة
MAX_USER_FILES = 100  # الحد الأقصى لكل مستخدم
COVER_MAX_SIZE = (500, 500)  # أقصى حجم للصورة
CACHE_CLEANUP_INTERVAL = 600  # 10 دقائق
BACKUP_RETENTION_DAYS = 7  # الاحتفاظ بالنسخ الاحتياطية 7 أيام

# سجل العمليات للمستخدمين (للتراجع)
USER_HISTORY = {}  # {user_id: deque}
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    """تهيئة قاعدة البيانات مع جداول محسنة"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # جدول المستخدمين المحسن
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, 
                  first_name TEXT,
                  username TEXT,
                  joined_date TEXT,
                  last_active TEXT,
                  total_operations INTEGER DEFAULT 0)''')
    
    # جدول الملفات المحسن
    c.execute('''CREATE TABLE IF NOT EXISTS files 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER, 
                  title TEXT, 
                  artist TEXT, 
                  file_size INTEGER DEFAULT 0,
                  duration INTEGER DEFAULT 0,
                  date TEXT)''')
    
    # جدول جديد لسجل العمليات
    c.execute('''CREATE TABLE IF NOT EXISTS operations_log 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  operation_type TEXT,
                  status TEXT,
                  timestamp TEXT)''')
    
    # جدول جديد للإذاعات
    c.execute('''CREATE TABLE IF NOT EXISTS broadcast_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  message TEXT,
                  recipients INTEGER,
                  sent_date TEXT)''')
    
    # إضافة أعمدة جديدة إذا لم تكن موجودة
    try:
        c.execute("ALTER TABLE users ADD COLUMN total_operations INTEGER DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE files ADD COLUMN file_size INTEGER DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE files ADD COLUMN duration INTEGER DEFAULT 0")
    except: pass
    
    # إنشاء فهارس لتحسين الأداء
    c.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON files(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_date ON files(date)")
    
    conn.commit()
    conn.close()
    logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")

# تنفيذ إنشاء الجداول تلقائياً
init_db()

async def is_maintenance(update, context):
    """التحقق من وضع الصيانة مع تحسين"""
    if MAINTENANCE_MODE:
        if update.effective_user.id == OWNER_ID:
            return False
        
        await update.effective_message.reply_text(
            "⚠️ **عذراً، البوت في وضع الصيانة حالياً!**\n\n"
            "نحن نقوم ببعض التحديثات، سنعود للعمل قريباً. 🛠️"
        )
        return True
    return False

async def auto_clear_cache():
    """تنظيف الملفات المؤقتة بشكل متقدم"""
    deleted_count = 0
    now = datetime.now().timestamp()
    
    for file in os.listdir():
        # تنظيف الملفات المؤقتة
        if any(file.endswith(ext) for ext in [".mp3", ".mp4", ".jpg", ".png"]) or \
           any(file.startswith(prefix) for prefix in ["input_", "output_", "custom_", "final_", "audio_", "video_", "cover_", "extracted_"]):
            try:
                file_path = os.path.join(os.getcwd(), file)
                # حذف الملفات الأقدم من ساعة
                if os.path.getmtime(file_path) < (now - 3600):
                    os.remove(file_path)
                    deleted_count += 1
            except:
                pass
    
    # تنظيف مجلد الصور المؤقتة إذا وجد
    temp_dirs = ["temp_images", "temp_audio", "backups"]
    for temp_dir in temp_dirs:
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                try:
                    file_path = os.path.join(temp_dir, file)
                    if os.path.getmtime(file_path) < (now - 3600):
                        os.remove(file_path)
                        deleted_count += 1
                except:
                    pass
    
    if deleted_count:
        logger.info(f"🧹 تم تنظيف {deleted_count} ملف مؤقت")

async def check_subscription(user_id, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من الاشتراك في القناة مع تخزين مؤقت"""
    # تخزين مؤقت لنتائج الفحص
    if not hasattr(check_subscription, 'cache'):
        check_subscription.cache = {}
    
    # تنظيف الكاش القديم (أكبر من 5 دقائق)
    now = datetime.now().timestamp()
    check_subscription.cache = {k: v for k, v in check_subscription.cache.items() 
                                if now - v[1] < 300}
    
    # التحقق من الكاش
    if user_id in check_subscription.cache:
        return check_subscription.cache[user_id][0]
    
    try:
        member = await context.bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        is_member = member.status not in ["left", "kicked"]
        check_subscription.cache[user_id] = (is_member, now)
        return is_member
    except Exception as e:
        logger.error(f"خطأ في فحص الاشتراك: {e}")
        return False

async def get_channel_cover(context: ContextTypes.DEFAULT_TYPE):
    """جلب صورة القناة مع تحسين"""
    if os.path.exists(COVER_CACHE):
        # التحقق من أن الصورة ليست قديمة (أكثر من يوم)
        if os.path.getmtime(COVER_CACHE) > (datetime.now().timestamp() - 86400):
            return COVER_CACHE
    
    try:
        chat = await context.bot.get_chat(f"@{CHANNEL_USERNAME}")
        if chat.photo:
            photo_file = await context.bot.get_file(chat.photo.big_file_id)
            await photo_file.download_to_drive(COVER_CACHE)
            
            # تحسين الصورة
            try:
                from PIL import Image
                with Image.open(COVER_CACHE) as img:
                    if img.size[0] > 500 or img.size[1] > 500:
                        img.thumbnail((500, 500), Image.Resampling.LANCZOS)
                        img.save(COVER_CACHE, quality=85)
            except:
                pass
            
            return COVER_CACHE
    except Exception as e:
        logger.error(f"خطأ جلب صورة القناة: {e}")
    return None

# دوال جديدة للتحسينات

async def add_to_history(user_id: int, file_path: str, operation_type: str):
    """إضافة عملية لسجل المستخدم (للتراجع)"""
    if user_id not in USER_HISTORY:
        USER_HISTORY[user_id] = deque(maxlen=5)
    USER_HISTORY[user_id].append({
        'path': file_path,
        'type': operation_type,
        'timestamp': datetime.now()
    })

async def undo_last_operation(user_id: int, context) -> tuple:
    """التراجع عن آخر عملية"""
    if user_id not in USER_HISTORY or not USER_HISTORY[user_id]:
        return False, "❌ لا توجد عمليات للتراجع عنها"
    
    last_op = USER_HISTORY[user_id].pop()
    if os.path.exists(last_op['path']):
        os.remove(last_op['path'])
        return True, f"✅ تم التراجع عن عملية {last_op['type']}"
    return False, "❌ الملف غير موجود"

async def auto_backup_db():
    """نسخ احتياطي تلقائي لقاعدة البيانات"""
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/bot_stats_{timestamp}.db"
    
    try:
        shutil.copy2(DB_FILE, backup_file)
        
        # حذف النسخ القديمة
        for file in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, file)
            if os.path.getmtime(file_path) < (datetime.now().timestamp() - BACKUP_RETENTION_DAYS * 86400):
                os.remove(file_path)
        
        logger.info(f"✅ تم عمل نسخة احتياطية: {backup_file}")
        return True
    except Exception as e:
        logger.error(f"فشل النسخ الاحتياطي: {e}")
        return False

def update_user_stats(user_id: int):
    """تحديث إحصائيات المستخدم في قاعدة البيانات"""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE users SET total_operations = total_operations + 1, last_active = ? WHERE user_id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

def log_operation(user_id: int, operation_type: str, status: str):
    """تسجيل عملية في السجل"""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO operations_log (user_id, operation_type, status, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, operation_type, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

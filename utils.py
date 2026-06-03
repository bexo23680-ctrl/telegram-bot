import os
import sqlite3
import logging
import subprocess
from datetime import datetime, timedelta
from telegram.ext import ContextTypes

# الإعدادات الأساسية
DB_FILE = "bot_stats.db"
MAX_FILE_SIZE = 70 * 1024 * 1024  # 70MB
DEFAULT_AUDIO_QUALITY = "192k"
COVER_CACHE = "channel_cover_cached.jpg"
CHANNEL_USERNAME = "BEXO50"

# ايدي المالك - غير هذا الرقم إلى معرفك
OWNER_ID = 8798182716  # ⚠️ غير هذا الرقم

# وضع الصيانة
MAINTENANCE_MODE = False

def init_db():
    """تهيئة قاعدة البيانات عند التشغيل"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # إنشاء جدول المستخدمين
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INTEGER PRIMARY KEY, 
                      first_name TEXT, 
                      join_date TEXT)''')
        
        # إنشاء جدول الملفات
        c.execute('''CREATE TABLE IF NOT EXISTS files 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      title TEXT, 
                      artist TEXT, 
                      date TEXT)''')
        
        # إضافة فهارس لتحسين الأداء
        c.execute('''CREATE INDEX IF NOT EXISTS idx_files_user_id 
                     ON files(user_id)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_files_date 
                     ON files(date)''')
        
        conn.commit()
        logging.info("✅ تم تهيئة قاعدة البيانات بنجاح")
        
    except Exception as e:
        logging.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
    finally:
        if conn:
            conn.close()

# تنفيذ إنشاء الجداول تلقائياً
init_db()

async def is_maintenance(update, context):
    """التحقق من وضع الصيانة"""
    if MAINTENANCE_MODE:
        # المالك يمكنه استخدام البوت حتى في وضع الصيانة
        if update.effective_user.id == OWNER_ID:
            return False
        
        # إرسال رسالة صيانة للمستخدمين العاديين
        if update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ **عذراً، البوت في وضع الصيانة حالياً!**\n\n"
                "نحن نقوم ببعض التحديثات، سنعود للعمل قريباً. 🛠️"
            )
        return True
    return False

async def auto_clear_cache():
    """تنظيف الملفات المؤقتة من السيرفر"""
    deleted = 0
    temp_patterns = [
        ".mp3", "input_", "output_", "custom_", 
        "final_", "cover_", "video_", "extracted_", "audio_"
    ]
    
    try:
        current_time = datetime.now().timestamp()
        one_hour_ago = current_time - 3600  # ساعة واحدة
        
        for file in os.listdir():
            # التحقق من أن الملف مؤقت
            is_temp = any(file.endswith(pattern) or file.startswith(pattern) 
                         for pattern in temp_patterns)
            
            if is_temp:
                try:
                    # حذف الملفات الأقدم من ساعة واحدة فقط
                    file_path = os.path.join(os.getcwd(), file)
                    if os.path.isfile(file_path):
                        if os.path.getmtime(file_path) < one_hour_ago:
                            os.remove(file_path)
                            deleted += 1
                except Exception as e:
                    logging.warning(f"⚠️ فشل حذف الملف {file}: {e}")
        
        if deleted > 0:
            logging.info(f"🧹 تم تنظيف {deleted} ملفات مؤقتة")
            
    except Exception as e:
        logging.error(f"❌ خطأ في تنظيف الملفات المؤقتة: {e}")

async def check_subscription(user_id, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من الاشتراك في القناة"""
    try:
        member = await context.bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.error(f"خطأ في فحص الاشتراك للمستخدم {user_id}: {e}")
        # في حالة حدوث خطأ، نسمح للمستخدم بالاستمرار (يمكن تغيير هذا السلوك)
        return True  # أو False حسب رغبتك

async def get_channel_cover(context: ContextTypes.DEFAULT_TYPE):
    """جلب صورة القناة لاستخدامها كغلاف للأغاني"""
    try:
        # التحقق من وجود الكاش وأنه صالح
        if os.path.exists(COVER_CACHE):
            if os.path.getsize(COVER_CACHE) > 0:
                # التحقق من أن الملف ليس قديماً (أكثر من 24 ساعة)
                file_age = datetime.now().timestamp() - os.path.getmtime(COVER_CACHE)
                if file_age < 86400:  # 24 ساعة
                    return COVER_CACHE
                else:
                    # حذف الكاش القديم
                    os.remove(COVER_CACHE)
                    logging.info("🗑️ تم حذف كاش صورة القناة القديم")
        
        # جلب الصورة من تيليجرام
        chat = await context.bot.get_chat(f"@{CHANNEL_USERNAME}")
        if chat.photo:
            photo_file = await context.bot.get_file(chat.photo.big_file_id)
            await photo_file.download_to_drive(COVER_CACHE)
            
            # التحقق من نجاح التحميل
            if os.path.exists(COVER_CACHE) and os.path.getsize(COVER_CACHE) > 0:
                logging.info("✅ تم تحديث صورة القناة")
                return COVER_CACHE
            else:
                logging.error("❌ فشل تحميل صورة القناة - الملف فارغ")
                return None
        else:
            logging.warning("⚠️ القناة لا تحتوي على صورة")
            return None
            
    except Exception as e:
        logging.error(f"❌ خطأ جلب صورة القناة: {e}")
        # إذا فشل الجلب وكان هناك كاش قديم، نستخدمه
        if os.path.exists(COVER_CACHE) and os.path.getsize(COVER_CACHE) > 0:
            logging.info("📦 استخدام الكاش القديم لصورة القناة")
            return COVER_CACHE
        return None

def add_user(user_id, first_name):
    """إضافة مستخدم جديد إلى قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "INSERT OR IGNORE INTO users(user_id, first_name, join_date) VALUES (?, ?, ?)",
            (user_id, first_name, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()
        logging.info(f"✅ تم تسجيل/تحديث المستخدم {user_id}")
    except Exception as e:
        logging.error(f"❌ خطأ في إضافة المستخدم {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def add_file_record(user_id, title, artist):
    """تسجيل عملية ناجحة في قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "INSERT INTO files (user_id, title, artist, date) VALUES (?, ?, ?, ?)",
            (user_id, title, artist, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()
        logging.info(f"✅ تم تسجيل ملف جديد: {title} - {artist}")
        return True
    except Exception as e:
        logging.error(f"❌ خطأ في تسجيل الملف: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_user_stats(user_id):
    """الحصول على إحصائيات المستخدم"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # عدد الملفات
        files_count = cursor.execute(
            "SELECT COUNT(*) FROM files WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        
        # آخر نشاط
        last_activity = cursor.execute(
            "SELECT MAX(date) FROM files WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        
        return {
            "files_count": files_count,
            "last_activity": last_activity or "لا يوجد"
        }
    except Exception as e:
        logging.error(f"❌ خطأ في جلب إحصائيات المستخدم {user_id}: {e}")
        return {"files_count": 0, "last_activity": "خطأ"}
    finally:
        if conn:
            conn.close()

def get_total_stats():
    """الحصول على إحصائيات البوت الكلية"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_files = cursor.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        
        # المستخدمين النشطين اليوم
        today = datetime.now().strftime("%Y-%m-%d")
        active_today = cursor.execute(
            "SELECT COUNT(DISTINCT user_id) FROM files WHERE date LIKE ?", 
            (f"{today}%",)
        ).fetchone()[0]
        
        return {
            "total_users": total_users,
            "total_files": total_files,
            "active_today": active_today
        }
    except Exception as e:
        logging.error(f"❌ خطأ في جلب الإحصائيات الكلية: {e}")
        return {"total_users": 0, "total_files": 0, "active_today": 0}
    finally:
        if conn:
            conn.close()

# ============================================
# دالة إصلاح الملفات الصوتية (المضافة حديثاً)
# ============================================
def fix_audio_file(input_path: str, output_path: str, quality: str = "192k"):
    """
    معالجة الملف الصوتي بشكل آمن وتحويله إلى MP3
    تعيد (مسار_الملف, رسالة_الخطأ) - إذا كان الأول None يعني فشل
    """
    try:
        # أولاً: تحليل الملف للتأكد من وجود صوت باستخدام ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error", 
            "-show_entries", "stream=codec_type", 
            "-of", "default=noprint_wrappers=1", 
            input_path
        ]
        
        try:
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            if "audio" not in result.stdout:
                return None, "الملف لا يحتوي على مسار صوتي"
        except subprocess.TimeoutExpired:
            return None, "انتهى وقت التحليل"
        except Exception as e:
            logging.warning(f"تحذير في ffprobe: {e}")
        
        # ثانياً: التحويل مع إعادة ترميز كامل ومحسن
        # استخدام -map_metadata -1 لإزالة أي بيانات تالفة قد تسبب مشاكل
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vn",                           # إزالة الفيديو
            "-acodec", "libmp3lame",         # ترميز MP3
            "-ac", "2",                      # ستيريو
            "-ar", "44100",                  # تردد 44.1kHz (قياسي لـ MP3)
            "-b:a", quality,                 # الجودة المختارة
            "-af", "volume=1.0,aresample=44100",  # تصحيح مستوى الصوت وإعادة العينة
            "-write_xing", "1",              # إضافة Xing header للـ MP3 (للتشغيل السليم)
            "-map_metadata", "-1",           # إزالة metadata تالفة
            "-y",                            # الكتابة فوق الملف الموجود
            output_path
        ]
        
        # تنفيذ الأمر مع timeout أطول للملفات الكبيرة
        process = subprocess.run(cmd, capture_output=True, timeout=120)
        
        if process.returncode != 0:
            error_msg = process.stderr.decode()[:200] if process.stderr else "خطأ غير معروف"
            return None, f"ffmpeg error: {error_msg}"
        
        # ثالثاً: التحقق من أن الملف الناتج يحتوي على صوت
        if not os.path.exists(output_path):
            return None, "الملف الناتج غير موجود"
        
        if os.path.getsize(output_path) < 2048:  # أقل من 2KB يعتبر تالف
            return None, "الملف الناتج صغير جداً (احتمال تالف)"
        
        # فحص إضافي باستخدام mutagen للتأكد
        try:
            from mutagen.mp3 import MP3
            audio = MP3(output_path)
            if audio.info.length <= 0:
                return None, "مدة الملف الصوتي صفرية"
            if audio.info.bitrate <= 0:
                logging.warning(f"تحذير: معدل البت غير طبيعي للملف {output_path}")
        except ImportError:
            pass  # mutagen غير متوفر، نتخطى الفحص
        except Exception as e:
            logging.warning(f"تحذير في فحص mutagen: {e}")
        
        return output_path, "success"
        
    except subprocess.TimeoutExpired:
        return None, "انتهى وقت معالجة الملف (الملف كبير جداً)"
    except Exception as e:
        return None, f"خطأ غير متوقع: {str(e)[:100]}"

import os
import subprocess
import sqlite3
import asyncio
import shutil
from datetime import datetime
from collections import deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from mutagen.id3 import ID3, TIT2, TPE1, APIC, error as MutagenError
from PIL import Image

from utils import (check_subscription, is_maintenance, DB_FILE, OWNER_ID, 
                   MAX_FILE_SIZE, get_channel_cover, add_to_history, 
                   undo_last_operation, update_user_stats, log_operation,
                   auto_backup_db, logger)

# متغيرات الطابور
processing_tasks = {}
task_queue = deque()
MAX_CONCURRENT = 3

# ============================================
# دالة البداية
# ============================================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_maintenance(update, context): return
    from keyboards import main_menu_keyboard
    
    user = update.effective_user
    if not await check_subscription(user.id, context):
        await update.message.reply_text("⚠️ اشترك بالقناة أولاً: @THTOMI")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT OR IGNORE INTO users(user_id, first_name, username, joined_date, last_active) VALUES (?, ?, ?, ?, ?)",
                (user.id, user.first_name, user.username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.execute("UPDATE users SET last_active = ? WHERE user_id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user.id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🚀 أهلاً بك {user.first_name} في بوت الخدمات الصوتية.\n\nإختر ماذا تريد أن تفعل الآن:",
        reply_markup=main_menu_keyboard()
    )

def get_user_files_count(user_id: int) -> int:
    """الحصول على عدد ملفات المستخدم"""
    conn = sqlite3.connect(DB_FILE)
    count = conn.execute("SELECT COUNT(*) FROM files WHERE user_id = ?", (user_id,)).fetchone()[0]
    conn.close()
    return count

# ============================================
# معالج الكولباك (الأزرار)
# ============================================
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # ===== زر التراجع =====
    if data == "undo_last":
        success, message = await undo_last_operation(user_id, context)
        await query.answer(message, show_alert=True)
        if success:
            await query.edit_message_text(
                f"✅ {message}\n\nيمكنك متابعة استخدام البوت."
            )
        return
    
    # ===== أزرار أغنيتي =====
    if data == "mysong_edit":
        context.user_data.clear()
        context.user_data['mysong_mode'] = 'edit'
        context.user_data['step'] = 'waiting_for_audio'
        await query.edit_message_text(
            "🎵 **تعديل أغنية موجودة**\n\n"
            "أرسل لي الآن الملف الصوتي (MP3) الذي تريد تعديله."
        )
    
    elif data == "mysong_extract":
        context.user_data.clear()
        context.user_data['mysong_mode'] = 'extract'
        context.user_data['step'] = 'waiting_for_video'
        await query.edit_message_text(
            "🎬 **استخراج صوت من فيديو + إضافة صورة**\n\n"
            "أرسل لي الآن ملف الفيديو لاستخراج الصوت منه."
        )
    
    elif data == "mysong_new":
        context.user_data.clear()
        context.user_data['mysong_mode'] = 'new'
        context.user_data['step'] = 'waiting_for_audio'
        await query.edit_message_text(
            "🆕 **رفع ملف صوتي + صورة جديدة**\n\n"
            "أرسل لي الآن الملف الصوتي (MP3)."
        )
    
    elif data == "my_stats":
        stats = await get_user_full_stats(user_id)
        await query.edit_message_text(stats)
        return
    
    # ===== أزرار الجودة =====
    elif data.startswith("q_"):
        parts = data.split("_")
        quality = parts[1] + "k"
        action = parts[2]
        context.user_data['selected_quality'] = quality
        context.user_data['action_type'] = action
        
        msg = f"✅ تم اختيار جودة {quality}\n\n"
        if action == "edit":
            msg += "🎵 أرسل الآن الملف الصوتي (MP3) لتعديله:"
        else:
            msg += "🎬 أرسل الآن ملف الفيديو لاستخراج الصوت منه:"
        
        await query.edit_message_text(msg)
    
    elif data == "cancel_action":
        await query.edit_message_text("❌ تم إلغاء العملية.")
        context.user_data.clear()
    
    elif data == "back_to_main":
        from keyboards import main_menu_keyboard
        await query.edit_message_text(
            "🏠 **القائمة الرئيسية**\n\nاختر ما تريد فعله:",
            reply_markup=main_menu_keyboard()
        )
    
    elif data == "check_subscription":
        from channels_manager import check_user_subscription, clear_subscription_cache
        is_subscribed, not_subscribed = await check_user_subscription(user_id, context)
        
        if is_subscribed:
            clear_subscription_cache(user_id)
            await query.answer("✅ تم التحقق! مرحباً بك", show_alert=True)
            await start_handler(update, context)
        else:
            channels_text = "\n".join([f"• @{ch['username']}" for ch in not_subscribed])
            await query.answer("⚠️ لا زلت غير مشترك!", show_alert=True)
            
            keyboard = []
            for ch in not_subscribed:
                keyboard.append([InlineKeyboardButton(f"📢 اشترك في القناة", url=f"https://t.me/{ch['username']}")])
            keyboard.append([InlineKeyboardButton("🔄 تأكد مرة أخرى", callback_data="check_subscription")])
            
            await query.edit_message_text(
                f"⚠️ **عذراً، يجب عليك الاشتراك في القنوات التالية:**\n\n{channels_text}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

#async def get_user_full_stats(user_id: int) -> str:
    #"""إحصائيات مفصلة للمستخدم"""
    #conn = sqlite3.connect(DB_FILE)
    
  #  files_count = conn.execute("SELECT COUNT(*) FROM files WHERE user_id = ?", (user_id,)).fetchone()[0]
    
   # last_files = conn.execute(
     #   "SELECT title, artist, date FROM files WHERE user_id = ? ORDER BY id DESC LIMIT 5",
     #   (user_id,)
#    ).fetchall()
    
   # total_size = conn.execute("SELECT SUM(file_size) FROM files WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
    
   # conn.close()
    #
   # msg = f"📊 **إحصائياتك الشخصية**\n\n"
   # msg += f"📁 عدد العمليات الناجحة: {files_count}\n"
   # msg += f"💾 إجمالي حجم الملفات: {total_size // (1024*1024)} MB\n\n"
    
   # if last_files:
    #    msg += "**🎵 آخر أعمالك:**\n"
      #  for title, artist, date in last_files:
      #      msg += f"• {title} - {artist}\n"
   # else:
    #    msg += "📭 لا توجد عمليات سابقة بعد\n"
    
    #return msg

# ============================================
# معالج الملفات (الصوت والفيديو) - MEDIA_HANDLER
# ============================================
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الملفات الصوتية والمرئية"""
    if await is_maintenance(update, context): return
    
    user_id = update.effective_user.id
    
    # ===== معالج وضع أغنيتي =====
    if context.user_data.get('mysong_mode'):
        await mysong_media_handler(update, context, user_id)
        return
    
    # ===== المعالج العادي =====
    action = context.user_data.get('action_type')
    quality = context.user_data.get('selected_quality', "192k")

    if not action:
        await update.message.reply_text("❌ من فضلك اختر نوع العملية أولاً من القائمة.")
        return

    # التحقق من نوع الملف
    file_obj = None
    if action == "edit" and (update.message.audio or (update.message.document and update.message.document.mime_type == 'audio/mpeg')):
        file_obj = update.message.audio or update.message.document
    elif action == "extract" and update.message.video:
        file_obj = update.message.video
    elif update.message.document:
        file_obj = update.message.document

    if not file_obj:
        await update.message.reply_text("❌ الملف المرسل لا يتوافق مع العملية المختارة.")
        return

    if file_obj.file_size > MAX_FILE_SIZE:
        await update.message.reply_text("❌ حجم الملف كبير جداً (الحد الأقصى 70MB).")
        return

    wait_msg = await update.message.reply_text("⏳ جاري التحميل والمعالجة...")
    
    tg_file = await file_obj.get_file()
    input_path = f"input_{user_id}_{file_obj.file_id[:5]}"
    output_path = f"output_{user_id}_{file_obj.file_id[:5]}.mp3"
    
    await tg_file.download_to_drive(input_path)

    # تشغيل FFmpeg
    cmd = [
        "ffmpeg", "-i", input_path, "-vn", "-acodec", "libmp3lame",
        "-ac", "2", "-b:a", quality, output_path, "-y"
    ]
    
    process = subprocess.run(cmd, capture_output=True)

    if os.path.exists(input_path): 
        os.remove(input_path)

    if process.returncode != 0:
        await wait_msg.edit_text("❌ حدث خطأ أثناء المعالجة.")
        return

    context.user_data["file_path"] = output_path
    context.user_data["step"] = "title"
    await wait_msg.edit_text("📝 تمت المعالجة! الآن أرسل (اسم الأغنية) الجديد:")

async def mysong_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """معالج ملفات وضع أغنيتي"""
    mysong_mode = context.user_data.get('mysong_mode')
    step = context.user_data.get('step')
    
    # استقبال الملف الصوتي
    if step == 'waiting_for_audio' and mysong_mode in ['edit', 'new']:
        file_obj = None
        if update.message.audio:
            file_obj = update.message.audio
        elif update.message.document and update.message.document.mime_type and 'audio' in update.message.document.mime_type:
            file_obj = update.message.document
        elif update.message.document and update.message.document.file_name and update.message.document.file_name.endswith('.mp3'):
            file_obj = update.message.document
        
        if not file_obj:
            await update.message.reply_text("❌ من فضلك أرسل ملف صوتي بصيغة MP3")
            return
        
        if file_obj.file_size > MAX_FILE_SIZE:
            await update.message.reply_text("❌ حجم الملف كبير جداً (الحد الأقصى 70MB).")
            return
        
        wait_msg = await update.message.reply_text("⏳ جاري تحميل الملف الصوتي...")
        tg_file = await file_obj.get_file()
        audio_path = f"audio_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
        await tg_file.download_to_drive(audio_path)
        
        context.user_data['audio_path'] = audio_path
        context.user_data['step'] = 'waiting_for_title'
        await wait_msg.edit_text("📝 أرسل الآن **اسم الأغنية**:")
        return
    
    # استقبال ملف الفيديو
    elif step == 'waiting_for_video' and mysong_mode == 'extract':
        if not update.message.video:
            await update.message.reply_text("❌ من فضلك أرسل ملف فيديو")
            return
        
        file_obj = update.message.video
        if file_obj.file_size > MAX_FILE_SIZE:
            await update.message.reply_text("❌ حجم الملف كبير جداً (الحد الأقصى 70MB).")
            return
        
        wait_msg = await update.message.reply_text("⏳ جاري تحميل الفيديو واستخراج الصوت...")
        tg_file = await file_obj.get_file()
        video_path = f"video_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
        await tg_file.download_to_drive(video_path)
        
        audio_path = f"extracted_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
        quality = context.user_data.get('selected_quality', '192k')
        
        cmd = [
            "ffmpeg", "-i", video_path, "-vn", "-acodec", "libmp3lame",
            "-ac", "2", "-b:a", quality, audio_path, "-y"
        ]
        
        process = subprocess.run(cmd, capture_output=True)
        
        if os.path.exists(video_path):
            os.remove(video_path)
        
        if process.returncode != 0:
            await wait_msg.edit_text("❌ حدث خطأ أثناء استخراج الصوت.")
            return
        
        context.user_data['audio_path'] = audio_path
        context.user_data['step'] = 'waiting_for_title'
        await wait_msg.edit_text("📝 تم استخراج الصوت بنجاح!\nأرسل الآن **اسم الأغنية**:")
        return

# ============================================
# معالج الصور
# ============================================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الصور المرسلة"""
    if await is_maintenance(update, context): return
    
    user_id = update.effective_user.id
    
    if context.user_data.get('mysong_mode') and context.user_data.get('step') == 'waiting_for_cover':
        
        wait_msg = await update.message.reply_text("⏳ جاري معالجة الصورة...")
        
        cover_path = await save_image(update, user_id)
        
        if not cover_path:
            await wait_msg.edit_text("❌ فشل في معالجة الصورة")
            return
        
        await process_song_with_cover(update, context, user_id, cover_path, wait_msg)
        return
    
    else:
        await update.message.reply_text("❌ لست في وضع إضافة صورة حالياً. اختر '🖼️ أغنيتي' أولاً.")

async def save_image(update: Update, user_id: int) -> str:
    """حفظ الصورة المرسلة"""
    os.makedirs("temp_images", exist_ok=True)
    cover_path = f"temp_images/cover_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    if update.message.photo:
        photo = update.message.photo[-1]
        tg_photo = await photo.get_file()
        cover_path += ".jpg"
        await tg_photo.download_to_drive(cover_path)
        return cover_path
    
    elif update.message.document:
        document = update.message.document
        file_name = document.file_name or ""
        
        if not (file_name.lower().endswith(('.jpg', '.jpeg', '.png'))):
            return None
        
        tg_doc = await document.get_file()
        
        if file_name.lower().endswith('.png'):
            cover_path += ".png"
        else:
            cover_path += ".jpg"
        
        await tg_doc.download_to_drive(cover_path)
        return cover_path
    
    return None

async def process_song_with_cover(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                   user_id: int, cover_path: str, wait_msg):
    """معالجة الأغنية مع الصورة"""
    audio_path = context.user_data.get('audio_path')
    title = context.user_data.get('title', 'غير معروف')
    artist = context.user_data.get('artist', 'غير معروف')
    
    if not audio_path or not os.path.exists(audio_path):
        await wait_msg.edit_text("❌ حدث خطأ: الملف الصوتي غير موجود")
        return
    
    try:
        audio = ID3(audio_path) if os.path.exists(audio_path) else ID3()
        
        audio["TIT2"] = TIT2(encoding=3, text=title)
        audio["TPE1"] = TPE1(encoding=3, text=artist)
        
        if cover_path and os.path.exists(cover_path):
            with open(cover_path, "rb") as img:
                if "APIC" in audio:
                    del audio["APIC"]
                
                mime_type = "image/jpeg" if cover_path.endswith('.jpg') else "image/png"
                audio["APIC"] = APIC(encoding=3, mime=mime_type, type=3, desc="Cover", data=img.read())
        
        audio.save(audio_path, v2_version=3)
        
        file_size = os.path.getsize(audio_path)
        
        with open(audio_path, "rb") as f:
            await update.message.reply_audio(
                audio=f,
                title=title,
                performer=artist
            )
        
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "INSERT INTO files (user_id, title, artist, file_size, date) VALUES (?, ?, ?, ?, ?)",
            (user_id, title, artist, file_size, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()
        conn.close()
        
        await add_to_history(user_id, audio_path, f"تعديل {title}")
        await wait_msg.delete()
        
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
    
    finally:
        for file in [audio_path, cover_path]:
            if file and os.path.exists(file):
                try:
                    os.remove(file)
                except:
                    pass
        
        context.user_data.clear()

# ============================================
# معالج النصوص
# ============================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id

    # ===== الإذاعة =====
    if context.user_data.get('admin_step') == 'broadcasting':
        if user_id != OWNER_ID:
            context.user_data['admin_step'] = None
            return
        
        await send_broadcast(update, context, user_text)
        return

    # ===== أزرار القائمة الرئيسية =====
    if user_text == "🎵 تعديل الأغاني":
        from keyboards import quality_keyboard
        await update.message.reply_text("اختر الجودة المطلوبة:", reply_markup=quality_keyboard("edit"))
        return
    
    elif user_text == "🎬 استخراج من الفيديو":
        from keyboards import quality_keyboard
        await update.message.reply_text("اختر الجودة المطلوبة:", reply_markup=quality_keyboard("extract"))
        return
    
    elif user_text == "🖼️ أغنيتي (القائمة المتكاملة)":
        from keyboards import my_song_menu_keyboard
        await update.message.reply_text(
            "🖼️ **قائمة أغنيتي المتكاملة**\n\nاختر ما تريد:",
            reply_markup=my_song_menu_keyboard()
        )
        return
    
    elif user_text == "📊 إحصائياتي":
        stats = await get_user_full_stats(user_id)
        await update.message.reply_text(stats)
        return
    
    elif user_text == "↩️ التراجع عن آخر عملية":
        success, message = await undo_last_operation(user_id, context)
        await update.message.reply_text(message)
        return
    
    elif user_text == "▶️ تشغيل البوت" or user_text == "🔙 الرجوع إلى البداية":
        await start_handler(update, context)
        return

    # ===== معالج وضع أغنيتي =====
    if context.user_data.get('mysong_mode'):
        step = context.user_data.get('step')
        
        if step == 'waiting_for_title':
            context.user_data['title'] = user_text
            context.user_data['step'] = 'waiting_for_artist'
            await update.message.reply_text("🎤 أرسل الآن **اسم الفنان**:")
            return
        
        elif step == 'waiting_for_artist':
            context.user_data['artist'] = user_text
            context.user_data['step'] = 'waiting_for_cover'
            await update.message.reply_text(
                "🖼️ **أرسل الصورة** (JPG أو PNG)\nأو اكتب 'تخطي' لاستخدام صورة افتراضية"
            )
            return
        
        elif step == 'waiting_for_cover':
            if user_text.lower() in ['تخطي', 'skip']:
                cover_path = await get_channel_cover(context)
                wait_msg = await update.message.reply_text("⏳ جاري المعالجة...")
                await process_song_with_cover(update, context, user_id, cover_path, wait_msg)
            else:
                await update.message.reply_text("❌ أرسل صورة أو اكتب 'تخطي'")
            return
        
        return

    # ===== إكمال العملية القديمة =====
    if "file_path" in context.user_data:
        await process_legacy_workflow(update, context, user_id)

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    """إرسال إذاعة لجميع المستخدمين"""
    conn = sqlite3.connect(DB_FILE)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    
    success_count = 0
    status_msg = await update.message.reply_text("⏳ جاري إرسال الإذاعة...")
    
    for u in users:
        try:
            await context.bot.send_message(chat_id=u[0], text=message)
            success_count += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    context.user_data['admin_step'] = None
    await status_msg.edit_text(f"✅ تمت الإذاعة بنجاح لـ {success_count} مستخدم.")

async def process_legacy_workflow(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """معالجة سير العمل القديم"""
    step = context.user_data.get("step")
    file_path = context.user_data["file_path"]

    if step == "title":
        context.user_data["title"] = update.message.text
        context.user_data["step"] = "artist"
        await update.message.reply_text("🎤 الآن أرسل (اسم الفنان):")
    
    elif step == "artist":
        title = context.user_data["title"]
        artist = update.message.text
        
        try:
            audio = ID3(file_path)
        except:
            audio = ID3()
        
        audio["TIT2"] = TIT2(encoding=3, text=title)
        audio["TPE1"] = TPE1(encoding=3, text=artist)
        
        cover = await get_channel_cover(context)
        if cover:
            with open(cover, "rb") as img:
                if "APIC" in audio:
                    del audio["APIC"]
                audio["APIC"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img.read())
        audio.save(file_path)

        with open(file_path, "rb") as f:
            await update.message.reply_audio(audio=f, title=title, performer=artist)

        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "INSERT INTO files (user_id, title, artist, date) VALUES (?, ?, ?, ?)",
            (user_id, title, artist, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()
        conn.close()

        if os.path.exists(file_path):
            os.remove(file_path)
        context.user_data.clear()

# ============================================
# أوامر إضافية
# ============================================
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء العملية الحالية"""
    if 'audio_path' in context.user_data:
        path = context.user_data['audio_path']
        if os.path.exists(path):
            os.remove(path)
    
    context.user_data.clear()
    await update.message.reply_text("❌ تم إلغاء العملية.")

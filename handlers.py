import os
import subprocess
import asyncio
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from mutagen.id3 import ID3, TIT2, TPE1, APIC, error as MutagenError

from utils import (
    check_subscription, is_maintenance, DB_FILE, OWNER_ID, 
    MAX_FILE_SIZE, get_channel_cover, add_user, add_file_record
)

# ============================================
# دالة البداية
# ============================================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_maintenance(update, context): 
        return
    
    from keyboards import main_menu_keyboard
    
    user = update.effective_user
    if not await check_subscription(user.id, context):
        await update.message.reply_text(
            "⚠️ أنت غير مشترك في القناة!\n\n"
            "يجب الاشتراك أولاً في القناة التالية:\n"
            f"👉 @BEXO50\n\n"
            "بعد الاشتراك، ارسل /start مرة أخرى."
        )
        return

    add_user(user.id, user.first_name)

    await update.message.reply_text(
        f"🚀 أهلاً بك {user.first_name} في بوت الخدمات الصوتية!\n\n"
        "إختر ما تريد فعله من الأزرار أدناه:",
        reply_markup=main_menu_keyboard()
    )

# ============================================
# دالة تحويل أي ملف صوتي إلى MP3 (محسنة)
# ============================================
async def convert_to_mp3(input_path: str, output_path: str, quality: str = "192k") -> tuple:
    """
    تحويل أي ملف صوتي إلى MP3 مع ضمان عدم فقدان الصوت
    تعيد (النجاح, رسالة_الخطأ)
    """
    try:
        # أولاً: التحقق من وجود الصوت في الملف الأصلي
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1",
            input_path
        ]
        
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        if "audio" not in probe_result.stdout:
            return False, "الملف لا يحتوي على مسار صوتي"
        
        # محاولة التحويل الأولى (الأمر المحسن)
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vn",                           # إزالة الفيديو إن وجد
            "-acodec", "libmp3lame",         # ترميز MP3
            "-ac", "2",                      # ستيريو
            "-ar", "44100",                  # تردد 44.1kHz
            "-b:a", quality,                 # الجودة المختارة
            "-af", "volume=1.0,aresample=44100",  # تصحيح مستوى الصوت
            "-write_xing", "1",              # إضافة Xing header
            "-map_metadata", "-1",           # إزالة metadata التالفة
            "-y",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        # إذا فشلت المحاولة الأولى، جرب أمراً أبسط
        if process.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
            # المحاولة الثانية (أمر بسيط)
            cmd2 = [
                "ffmpeg", "-i", input_path,
                "-b:a", quality,
                "-y",
                output_path
            ]
            
            process2 = await asyncio.create_subprocess_exec(
                *cmd2,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process2.communicate()
            
            if process2.returncode != 0:
                return False, "فشل تحويل الملف إلى MP3"
        
        # التحقق من نجاح التحويل
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            # فحص إضافي للتأكد من وجود صوت
            if await verify_audio_has_sound(output_path):
                return True, "success"
            else:
                return False, "الملف الناتج لا يحتوي على صوت"
        
        return False, "فشل تحويل الملف"
        
    except asyncio.TimeoutError:
        return False, "انتهى وقت التحويل"
    except Exception as e:
        return False, f"خطأ: {str(e)[:100]}"

async def verify_audio_has_sound(file_path: str) -> bool:
    """التحقق من أن الملف يحتوي على صوت فعلي"""
    try:
        if not os.path.exists(file_path) or os.path.getsize(file_path) < 1000:
            return False
        
        # استخدام ffprobe للتحقق
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        try:
            duration = float(result.stdout.strip())
            if duration > 0.5:
                return True
        except:
            pass
        
        # فحص بديل باستخدام mutagen
        try:
            from mutagen.mp3 import MP3
            audio = MP3(file_path)
            if audio.info.length > 0:
                return True
        except:
            pass
        
        return False
        
    except Exception:
        return True  # نفترض أنه سليم إذا فشل الفحص

# ============================================
# دالة استخراج الصوت من الفيديو (محسنة)
# ============================================
async def extract_audio_from_video(video_path: str, output_path: str, quality: str = "192k") -> tuple:
    """استخراج الصوت من الفيديو مع ضمان الجودة"""
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ac", "2",
            "-ar", "44100",
            "-b:a", quality,
            "-af", "volume=1.0",
            "-y",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.wait()
        
        if process.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return True, "success"
        else:
            return False, "فشل استخراج الصوت"
            
    except Exception as e:
        return False, str(e)

# ============================================
# معالج الكولباك (الأزرار)
# ============================================
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    await query.answer()
    
    # ===== أزرار وضع "أغنيتي" المتكاملة =====
    if data == "mysong_edit":
        context.user_data.clear()
        context.user_data['mode'] = 'mysong_edit'
        context.user_data['step'] = 'waiting_for_audio'
        await query.edit_message_text(
            "🎵 تعديل أغنية موجودة\n\n"
            "📤 أرسل لي الآن الملف الصوتي الذي تريد تعديله.\n\n"
            "⚠️ الحد الأقصى للحجم: 70MB"
        )
    
    elif data == "mysong_extract":
        context.user_data.clear()
        context.user_data['mode'] = 'mysong_extract'
        context.user_data['step'] = 'waiting_for_video'
        await query.edit_message_text(
            "🎬 استخراج صوت من فيديو + إضافة صورة\n\n"
            "📤 أرسل لي الآن ملف الفيديو لاستخراج الصوت منه.\n\n"
            "⚠️ الحد الأقصى للحجم: 70MB"
        )
    
    elif data == "mysong_new":
        context.user_data.clear()
        context.user_data['mode'] = 'mysong_new'
        context.user_data['step'] = 'waiting_for_audio'
        await query.edit_message_text(
            "🆕 رفع ملف صوتي جديد + صورة\n\n"
            "📤 أرسل لي الآن الملف الصوتي .\n\n"
            "⚠️ الحد الأقصى للحجم: 70MB"
        )
    
    # ===== أزرار اختيار الجودة =====
    elif data.startswith("q_"):
        parts = data.split("_")
        quality = parts[1] + "k"
        action = parts[2]
        context.user_data['selected_quality'] = quality
        context.user_data['action_type'] = action
        
        if action == "edit":
            msg = "🎵 أرسل الآن الملف الصوتي لتعديله:"
        else:
            msg = "🎬 أرسل الآن ملف الفيديو لاستخراج الصوت منه:"
        
        await query.edit_message_text(f"✅ تم اختيار جودة {quality}.\n\n{msg}")
    
    elif data == "cancel_action":
        context.user_data.clear()
        await query.edit_message_text("❌ تم إلغاء العملية.")
    
    # ===== أزرار الإحصائيات =====
    elif data == "my_stats":
        conn = sqlite3.connect(DB_FILE)
        files_count = conn.execute(
            "SELECT COUNT(*) FROM files WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        
        await query.edit_message_text(
            f"📊 إحصائياتك الشخصية\n\n"
            f"✅ عدد الأغاني التي قمت بمعالجتها: {files_count}"
        )

# ============================================
# معالج الملفات (الصوت والفيديو) - النسخة المحسنة
# ============================================
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_maintenance(update, context): 
        return
    
    user_id = update.effective_user.id
    mode = context.user_data.get('mode')
    step = context.user_data.get('step')
    
    # ===== وضع mysong =====
    if mode and step:
        # استقبال الملف الصوتي (جميع الصيغ)
        if step == 'waiting_for_audio' and mode in ['mysong_edit', 'mysong_new']:
            file_obj = None
            
            if update.message.audio:
                file_obj = update.message.audio
            elif update.message.document:
                doc = update.message.document
                # دعم جميع الصيغ الصوتية
                audio_extensions = ('.mp3', '.m4a', '.aac', '.ogg', '.wav', '.flac', '.opus', '.wma')
                if doc.file_name and doc.file_name.lower().endswith(audio_extensions):
                    file_obj = doc
            
            if not file_obj:
                await update.message.reply_text("❌ من فضلك أرسل ملف صوتي صالح")
                return
            
            if file_obj.file_size > MAX_FILE_SIZE:
                await update.message.reply_text(f"❌ حجم الملف كبير جداً (الحد الأقصى 70MB)")
                return
            
            wait_msg = await update.message.reply_text("⏳ جاري تحميل الملف الصوتي...")
            tg_file = await file_obj.get_file()
            original_path = f"original_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            await tg_file.download_to_drive(original_path)
            
            # تحويل إلى MP3 إذا لم يكن كذلك
            audio_path = f"audio_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
            
            await wait_msg.edit_text("⏳ جاري معالجة وتحويل الملف الصوتي...")
            
            success, error_msg = await convert_to_mp3(original_path, audio_path, "192k")
            
            # حذف الملف الأصلي
            if os.path.exists(original_path):
                os.remove(original_path)
            
            if not success:
                await wait_msg.edit_text(f"❌ {error_msg}")
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                context.user_data.clear()
                return
            
            context.user_data['audio_path'] = audio_path
            context.user_data['step'] = 'waiting_for_title'
            await wait_msg.edit_text("✅ تم معالجة الملف بنجاح!\n\n📝 أرسل الآن اسم الأغنية:")
            return
        
        # استقبال ملف الفيديو
        elif step == 'waiting_for_video' and mode == 'mysong_extract':
            if not update.message.video:
                await update.message.reply_text("❌ من فضلك أرسل ملف فيديو")
                return
            
            file_obj = update.message.video
            if file_obj.file_size > MAX_FILE_SIZE:
                await update.message.reply_text(f"❌ حجم الملف كبير جداً (الحد الأقصى 70MB)")
                return
            
            wait_msg = await update.message.reply_text("⏳ جاري تحميل الفيديو واستخراج الصوت...")
            tg_file = await file_obj.get_file()
            video_path = f"video_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            await tg_file.download_to_drive(video_path)
            
            audio_path = f"extracted_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
            
            await wait_msg.edit_text("⏳ جاري استخراج الصوت من الفيديو...")
            
            success, error_msg = await extract_audio_from_video(video_path, audio_path, "192k")
            
            # تنظيف ملف الفيديو
            if os.path.exists(video_path):
                os.remove(video_path)
            
            if not success:
                await wait_msg.edit_text(f"❌ {error_msg}")
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                context.user_data.clear()
                return
            
            context.user_data['audio_path'] = audio_path
            context.user_data['step'] = 'waiting_for_title'
            await wait_msg.edit_text("✅ تم استخراج الصوت بنجاح!\n\n📝 أرسل الآن اسم الأغنية:")
            return
        
        else:
            if mode == 'mysong_extract':
                await update.message.reply_text("❌ الرجاء إرسال ملف فيديو")
            elif mode in ['mysong_edit', 'mysong_new']:
                await update.message.reply_text("❌ الرجاء إرسال ملف صوتي ")
            return
    
    # ===== الوضع العادي =====
    action_type = context.user_data.get('action_type')
    quality = context.user_data.get('selected_quality', '192k')
    
    if not action_type:
        return
    
    file_obj = None
    if action_type == "edit":
        if update.message.audio:
            file_obj = update.message.audio
        elif update.message.document:
            doc = update.message.document
            audio_extensions = ('.mp3', '.m4a', '.aac', '.ogg', '.wav', '.flac', '.opus')
            if doc.file_name and doc.file_name.lower().endswith(audio_extensions):
                file_obj = doc
        
        if not file_obj:
            await update.message.reply_text("❌ الرجاء إرسال ملف صوتي")
            context.user_data.clear()
            return
            
    elif action_type == "extract":
        if update.message.video:
            file_obj = update.message.video
        
        if not file_obj:
            await update.message.reply_text("❌ الرجاء إرسال ملف فيديو ")
            context.user_data.clear()
            return
    
    if file_obj.file_size > MAX_FILE_SIZE:
        await update.message.reply_text("❌ حجم الملف كبير جداً (الحد الأقصى 70MB).")
        context.user_data.clear()
        return
    
    wait_msg = await update.message.reply_text("⏳ جاري التحميل والمعالجة...")
    
    try:
        tg_file = await file_obj.get_file()
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        original_path = f"original_{user_id}_{timestamp}"
        output_path = f"output_{user_id}_{timestamp}.mp3"
        
        await tg_file.download_to_drive(original_path)
        
        success, error_msg = await convert_to_mp3(original_path, output_path, quality)
        
        # تنظيف ملف الإدخال
        if os.path.exists(original_path):
            os.remove(original_path)
        
        if not success:
            await wait_msg.edit_text(f"❌ {error_msg}")
            if os.path.exists(output_path):
                os.remove(output_path)
            context.user_data.clear()
            return
        
        context.user_data["file_path"] = output_path
        context.user_data["step"] = "title"
        await wait_msg.edit_text("📝 تمت المعالجة! الآن أرسل اسم الأغنية:")
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ حدث خطأ: {str(e)}")
        for path in [original_path, output_path]:
            if 'path' in locals() and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
        context.user_data.clear()

# ============================================
# معالج الصور
# ============================================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_maintenance(update, context): 
        return
    
    user_id = update.effective_user.id
    
    if context.user_data.get('mode') and context.user_data.get('step') == 'waiting_for_cover':
        
        wait_msg = await update.message.reply_text("🖼️ جاري معالجة الصورة ودمجها مع الأغنية...")
        
        cover_path = f"cover_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        audio_path = context.user_data.get('audio_path')
        
        try:
            if update.message.photo:
                photo = update.message.photo[-1]
                tg_photo = await photo.get_file()
                cover_path += ".jpg"
                await tg_photo.download_to_drive(cover_path)
            
            elif update.message.document:
                document = update.message.document
                mime_type = document.mime_type or ""
                file_name = document.file_name or ""
                
                if not (mime_type.startswith('image/') or file_name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))):
                    await wait_msg.edit_text("❌ الملف المرسل ليس صورة.")
                    return
                
                tg_doc = await document.get_file()
                
                if file_name.lower().endswith('.png') or 'png' in mime_type:
                    cover_path += ".png"
                elif file_name.lower().endswith('.webp') or 'webp' in mime_type:
                    cover_path += ".webp"
                else:
                    cover_path += ".jpg"
                
                await tg_doc.download_to_drive(cover_path)
            
            else:
                await wait_msg.edit_text("❌ لم ترسل صورة.")
                return
            
            title = context.user_data.get('title', 'غير معروف')
            artist = context.user_data.get('artist', 'غير معروف')
            
            if not audio_path or not os.path.exists(audio_path):
                await wait_msg.edit_text("❌ حدث خطأ: الملف الصوتي غير موجود")
                if os.path.exists(cover_path):
                    os.remove(cover_path)
                context.user_data.clear()
                return
            
            try:
                audio = ID3(audio_path)
            except MutagenError:
                audio = ID3()
            
            audio["TIT2"] = TIT2(encoding=3, text=title)
            audio["TPE1"] = TPE1(encoding=3, text=artist)
            
            if cover_path.endswith('.png'):
                mime_type = "image/png"
            elif cover_path.endswith('.webp'):
                mime_type = "image/webp"
            else:
                mime_type = "image/jpeg"
            
            with open(cover_path, "rb") as img:
                if "APIC" in audio:
                    del audio["APIC"]
                audio["APIC"] = APIC(
                    encoding=3, 
                    mime=mime_type, 
                    type=3, 
                    desc="Cover", 
                    data=img.read()
                )
            
            audio.save(audio_path, v2_version=3)
            
            with open(audio_path, "rb") as f:
                await update.message.reply_audio(
                    audio=f,
                    title=title,
                    performer=artist,
                    caption="✅ تم إنشاء الأغنية بنجاح!"
                )
            
            add_file_record(user_id, title, artist)
            await wait_msg.delete()
            
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
        
        finally:
            if cover_path and os.path.exists(cover_path):
                try:
                    os.remove(cover_path)
                except:
                    pass
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except:
                    pass
            
            context.user_data.clear()
        return
    
    else:
        await update.message.reply_text("❌ لست في وضع إضافة صورة حالياً.\nالرجاء استخدام الأزرار لبدء عملية جديدة.")

# ============================================
# معالج النصوص
# ============================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id

    # ===== الإذاعة للأدمن =====
    if context.user_data.get('admin_step') == 'broadcasting':
        if user_id != OWNER_ID:
            context.user_data['admin_step'] = None
            return
        
        conn = sqlite3.connect(DB_FILE)
        users = conn.execute("SELECT user_id FROM users").fetchall()
        conn.close()
        
        success_count = 0
        for u in users:
            try: 
                await context.bot.send_message(chat_id=u[0], text=user_text)
                success_count += 1
            except: 
                pass
        
        context.user_data['admin_step'] = None
        await update.message.reply_text(f"✅ تمت الإذاعة بنجاح لـ {success_count} مستخدم.")
        return

    # ===== أزرار القائمة الرئيسية =====
    if user_text == "▶️ تشغيل البوت":
        await start_handler(update, context)
        return
    
    elif user_text == "🎵 تعديل الأغنية":
        from keyboards import quality_keyboard
        await update.message.reply_text(
            "🎵 تعديل أغنية\n\nاختر جودة الصوت المطلوبة:",
            reply_markup=quality_keyboard("edit")
        )
        return
    
    elif user_text == "🎬 استخراج صوت من فيديو":
        from keyboards import quality_keyboard
        await update.message.reply_text(
            "🎬 استخراج صوت من فيديو\n\nاختر جودة الصوت المطلوبة:",
            reply_markup=quality_keyboard("extract")
        )
        return
    
    elif user_text == "🖼️ إنشاء أغنية كاملة (اسم + صورة + صوت)":
        from keyboards import my_song_menu_keyboard
        await update.message.reply_text(
            "🖼️ إنشاء أغنية كاملة\n\nاختر ما تريد فعله:",
            reply_markup=my_song_menu_keyboard()
        )
        return
    
    elif user_text == "📊 إحصائياتي":
        conn = sqlite3.connect(DB_FILE)
        files_count = conn.execute(
            "SELECT COUNT(*) FROM files WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        
        await update.message.reply_text(
            f"📊 إحصائياتك الشخصية\n\n"
            f"✅ عدد الأغاني التي تمت معالجتها: {files_count}"
        )
        return
    
    elif user_text == "🛠 لوحة التحكم":
        if user_id == OWNER_ID:
            from admin_panel import panel_handler
            await panel_handler(update, context)
        else:
            await update.message.reply_text("❌ هذه الخاصية متاحة للمطور فقط.")
        return

    # ===== وضع mysong - استقبال النصوص =====
    if context.user_data.get('mode'):
        step = context.user_data.get('step')
        
        if step == 'waiting_for_title':
            if len(user_text) > 100:
                await update.message.reply_text("❌ اسم الأغنية طويل جداً (الحد الأقصى 100 حرف).")
                return
            context.user_data['title'] = user_text
            context.user_data['step'] = 'waiting_for_artist'
            await update.message.reply_text("🎤 أرسل الآن اسم الفنان:")
            return
        
        elif step == 'waiting_for_artist':
            if len(user_text) > 100:
                await update.message.reply_text("❌ اسم الفنان طويل جداً (الحد الأقصى 100 حرف).")
                return
            context.user_data['artist'] = user_text
            context.user_data['step'] = 'waiting_for_cover'
            await update.message.reply_text(
                "🖼️ أرسل الآن الصورة التي تريد استخدامها كغلاف للأغنية\n"
                "(JPG أو PNG)"
            )
            return
        
        elif step == 'waiting_for_cover':
            await update.message.reply_text("❌ أنا في انتظار صورة وليس نص. أرسل صورة من فضلك.")
            return

    # ===== إكمال عملية التعديل العادي =====
    if "file_path" in context.user_data:
        step = context.user_data.get("step")
        file_path = context.user_data["file_path"]

        if step == "title":
            context.user_data["title"] = user_text
            context.user_data["step"] = "artist"
            await update.message.reply_text("🎤 الآن أرسل (اسم الفنان):")
        
        elif step == "artist":
            title = context.user_data["title"]
            artist = user_text
            
            try:
                try:
                    audio = ID3(file_path)
                except:
                    audio = ID3()
                
                audio["TIT2"] = TIT2(encoding=3, text=title)
                audio["TPE1"] = TPE1(encoding=3, text=artist)
                
                cover = await get_channel_cover(context)
                if cover:
                    with open(cover, "rb") as img:
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
                
            except Exception as e:
                await update.message.reply_text(f"❌ حدث خطأ أثناء حفظ البيانات: {str(e)}")
            
            finally:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                
                context.user_data.clear()
        
        return
    
    await update.message.reply_text(
        "❓ عذراً، لم أفهم طلبك.\n"
        "الرجاء استخدام الأزرار المتاحة في القائمة."
    )

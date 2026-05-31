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
            "📤 أرسل لي الآن الملف الصوتي (MP3) الذي تريد تعديل اسمه وإضافة صورة له.\n\n"
            "⚠️ الحد الأقصى للحجم: 70MB"
        )
    
    elif data == "mysong_extract":
        context.user_data.clear()
        context.user_data['mode'] = 'mysong_extract'
        context.user_data['step'] = 'waiting_for_video'
        await query.edit_message_text(
            "🎬 استخراج صوت من فيديو + إضافة صورة\n\n"
            "📤 أرسل لي الآن ملف الفيديو (MP4) لاستخراج الصوت منه، ثم سنضيف الاسم والصورة.\n\n"
            "⚠️ الحد الأقصى للحجم: 70MB"
        )
    
    elif data == "mysong_new":
        context.user_data.clear()
        context.user_data['mode'] = 'mysong_new'
        context.user_data['step'] = 'waiting_for_audio'
        await query.edit_message_text(
            "🆕 رفع ملف صوتي جديد + صورة\n\n"
            "📤 أرسل لي الآن الملف الصوتي (MP3) وسأطلب منك الاسم والفنان والصورة.\n\n"
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
            msg = "🎵 أرسل الآن الملف الصوتي (MP3) لتعديله:"
        else:
            msg = "🎬 أرسل الآن ملف الفيديو (MP4) لاستخراج الصوت منه:"
        
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
# معالج الملفات (الصوت والفيديو)
# ============================================
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_maintenance(update, context): 
        return
    
    user_id = update.effective_user.id
    mode = context.user_data.get('mode')
    step = context.user_data.get('step')
    
    # ===== وضع mysong =====
    if mode and step:
        # استقبال الملف الصوتي
        if step == 'waiting_for_audio' and mode in ['mysong_edit', 'mysong_new']:
            file_obj = None
            if update.message.audio:
                file_obj = update.message.audio
            elif update.message.document:
                doc = update.message.document
                if doc.mime_type == 'audio/mpeg' or (doc.file_name and doc.file_name.endswith('.mp3')):
                    file_obj = doc
            
            if not file_obj:
                await update.message.reply_text("❌ من فضلك أرسل ملف صوتي بصيغة MP3")
                return
            
            if file_obj.file_size > MAX_FILE_SIZE:
                await update.message.reply_text(f"❌ حجم الملف كبير جداً (الحد الأقصى 70MB)")
                return
            
            wait_msg = await update.message.reply_text("⏳ جاري تحميل الملف الصوتي...")
            tg_file = await file_obj.get_file()
            audio_path = f"audio_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
            await tg_file.download_to_drive(audio_path)
            
            context.user_data['audio_path'] = audio_path
            context.user_data['step'] = 'waiting_for_title'
            await wait_msg.edit_text("📝 أرسل الآن اسم الأغنية:")
            return
        
        # استقبال ملف الفيديو
        elif step == 'waiting_for_video' and mode == 'mysong_extract':
            if not update.message.video:
                await update.message.reply_text("❌ من فضلك أرسل ملف فيديو (MP4)")
                return
            
            file_obj = update.message.video
            if file_obj.file_size > MAX_FILE_SIZE:
                await update.message.reply_text(f"❌ حجم الملف كبير جداً (الحد الأقصى 70MB)")
                return
            
            wait_msg = await update.message.reply_text("⏳ جاري تحميل الفيديو واستخراج الصوت...")
            tg_file = await file_obj.get_file()
            video_path = f"video_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
            await tg_file.download_to_drive(video_path)
            
            audio_path = f"extracted_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
            
            cmd = [
                "ffmpeg", "-i", video_path, "-vn", "-acodec", "libmp3lame",
                "-ac", "2", "-b:a", "192k", audio_path, "-y"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.wait()
            
            # تنظيف ملف الفيديو
            if os.path.exists(video_path):
                os.remove(video_path)
            
            if process.returncode != 0:
                await wait_msg.edit_text("❌ حدث خطأ أثناء استخراج الصوت.")
                # تنظيف ملف الصوت في حالة الفشل
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                return
            
            context.user_data['audio_path'] = audio_path
            context.user_data['step'] = 'waiting_for_title'
            await wait_msg.edit_text("✅ تم استخراج الصوت بنجاح!\n\n📝 أرسل الآن **اسم الأغنية**:")
            return
        
        # إذا كان المستخدم في وضع mysong لكنه أرسل ملف غير مناسب
        else:
            if mode == 'mysong_extract':
                await update.message.reply_text("❌ الرجاء إرسال ملف فيديو MP4")
            elif mode in ['mysong_edit', 'mysong_new']:
                await update.message.reply_text("❌ الرجاء إرسال ملف صوتي MP3")
            return
    
    # ===== الوضع العادي =====
    action_type = context.user_data.get('action_type')
    quality = context.user_data.get('selected_quality', '192k')
    
    if not action_type:
        # إذا لم يتم تحديد نوع العملية، تجاهل الملف
        return
    
    file_obj = None
    if action_type == "edit":
        if update.message.audio:
            file_obj = update.message.audio
        elif update.message.document:
            doc = update.message.document
            if doc.mime_type == 'audio/mpeg' or (doc.file_name and doc.file_name.endswith('.mp3')):
                file_obj = doc
        
        if not file_obj:
            await update.message.reply_text("❌ الرجاء إرسال ملف صوتي MP3 للتعديل")
            context.user_data.clear()
            return
            
    elif action_type == "extract":
        if update.message.video:
            file_obj = update.message.video
        
        if not file_obj:
            await update.message.reply_text("❌ الرجاء إرسال ملف فيديو MP4 لاستخراج الصوت")
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
        input_path = f"input_{user_id}_{timestamp}"
        output_path = f"output_{user_id}_{timestamp}.mp3"
        
        await tg_file.download_to_drive(input_path)
        
        cmd = [
            "ffmpeg", "-i", input_path, "-vn", "-acodec", "libmp3lame",
            "-ac", "2", "-b:a", quality, output_path, "-y"
        ]
        
        process = subprocess.run(cmd, capture_output=True)
        
        # تنظيف ملف الإدخال
        if os.path.exists(input_path):
            os.remove(input_path)
        
        if process.returncode != 0:
            await wait_msg.edit_text("❌ حدث خطأ أثناء المعالجة.")
            # تنظيف ملف الإخراج
            if os.path.exists(output_path):
                os.remove(output_path)
            context.user_data.clear()
            return
        
        context.user_data["file_path"] = output_path
        context.user_data["step"] = "title"
        await wait_msg.edit_text("📝 تمت المعالجة! الآن أرسل اسم الأغنية:")
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ حدث خطأ: {str(e)}")
        # تنظيف الملفات في حالة الخطأ
        for path in [input_path, output_path]:
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
            
            # تعديل الملف الصوتي
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
            # تنظيف الملفات المؤقتة دائماً
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
        # إذا أرسل صورة خارج السياق
        await update.message.reply_text("❌ لست في وضع إضافة صورة حالياً.\nالرجاء استخدام الأزرار لبدء عملية جديدة.")

# ============================================
# معالج النصوص (مع زر تشغيل البوت)
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
    
    # ▶️ زر تشغيل البوت (الأول)
    if user_text == "▶️ تشغيل البوت":
        await start_handler(update, context)
        return
    
    # 🎵 زر تعديل الأغنية
    elif user_text == "🎵 تعديل الأغنية":
        from keyboards import quality_keyboard
        await update.message.reply_text(
            "🎵 تعديل أغنية\n\nاختر جودة الصوت المطلوبة:",
            reply_markup=quality_keyboard("edit")
        )
        return
    
    # 🎬 زر استخراج صوت من فيديو
    elif user_text == "🎬 استخراج صوت من فيديو":
        from keyboards import quality_keyboard
        await update.message.reply_text(
            "🎬 استخراج صوت من فيديو\n\nاختر جودة الصوت المطلوبة:",
            reply_markup=quality_keyboard("extract")
        )
        return
    
    # 🖼️ زر إنشاء أغنية كاملة
    elif user_text == "🖼️ إنشاء أغنية كاملة (اسم + صورة + صوت)":
        from keyboards import my_song_menu_keyboard
        await update.message.reply_text(
            "🖼️ إنشاء أغنية كاملة\n\nاختر ما تريد فعله:",
            reply_markup=my_song_menu_keyboard()
        )
        return
    
    # 📊 زر إحصائياتي
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
    
    # 🛠 زر لوحة التحكم
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
                
                # إضافة غلاف القناة إذا كان متاحاً
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
                # تنظيف الملفات
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                
                context.user_data.clear()
        
        return
    
    # رسالة افتراضية للنصوص غير المعروفة
    await update.message.reply_text(
        "❓ عذراً، لم أفهم طلبك.\n"
        "الرجاء استخدام الأزرار المتاحة في القائمة."
    )

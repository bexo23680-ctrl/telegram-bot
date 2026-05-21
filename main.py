import os
import asyncio
import logging
from datetime import datetime
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from handlers import (start_handler, media_handler, text_handler, 
                      callback_query_handler, photo_handler)
from admin_panel import panel_handler, admin_callback_handler
from utils import auto_clear_cache, auto_backup_db, logger

# إعدادات الـ Logging المتقدمة
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get("BOT_TOKEN")

# إحصائيات البوت
bot_start_time = datetime.now()

async def stats_handler(update, context):
    """أمر عرض إحصائيات البوت (للمالك فقط)"""
    from utils import OWNER_ID
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ غير مصرح لك!")
        return
    
    uptime = datetime.now() - bot_start_time
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    
    await update.message.reply_text(
        f"🤖 **إحصائيات البوت**\n\n"
        f"⏱️ وقت التشغيل: {hours} ساعة {minutes} دقيقة\n"
        f"📅 تاريخ التشغيل: {bot_start_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"🔧 الحالة: ✅ يعمل بكفاءة"
    )

async def backup_handler(update, context):
    """أمر عمل نسخة احتياطية يدوياً"""
    from utils import OWNER_ID, auto_backup_db
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ غير مصرح لك!")
        return
    
    await update.message.reply_text("⏳ جاري عمل نسخة احتياطية...")
    success = await auto_backup_db()
    if success:
        await update.message.reply_text("✅ تم عمل نسخة احتياطية بنجاح!")
    else:
        await update.message.reply_text("❌ فشل في عمل نسخة احتياطية")

async def cancel_handler(update, context):
    """إلغاء العملية الحالية"""
    user_id = update.effective_user.id
    
    # تنظيف الملفات المؤقتة
    if 'audio_path' in context.user_data:
        path = context.user_data['audio_path']
        if os.path.exists(path):
            os.remove(path)
    
    context.user_data.clear()
    
    await update.message.reply_text(
        "❌ **تم إلغاء العملية**\n\n"
        "يمكنك بدء عملية جديدة من القائمة الرئيسية."
    )

def main():
    if not TOKEN:
        print("❌ خطأ: لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")
        return

    # بناء تطبيق البوت
    app = Application.builder().token(TOKEN).build()

    # إعداد المهام الدورية
    if app.job_queue:
        # تنظيف الملفات المؤقتة كل 10 دقائق
        app.job_queue.run_repeating(
            lambda _: asyncio.create_task(auto_clear_cache()), 
            interval=600, 
            first=10
        )
        
        # نسخ احتياطي كل 24 ساعة
        app.job_queue.run_repeating(
            lambda _: asyncio.create_task(auto_backup_db()),
            interval=86400,
            first=60
        )

    # --- المعالجات (Handlers) ---

    # الأوامر الأساسية
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("panel", panel_handler))
    app.add_handler(CommandHandler("stats", stats_handler))
    app.add_handler(CommandHandler("backup", backup_handler))
    app.add_handler(CommandHandler("cancel", cancel_handler))

    # معالجة الأزرار
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^(admin_|toggle_|close_admin)"))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # معالجة الصور
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    # معالجة الوسائط
    app.add_handler(MessageHandler(filters.AUDIO | filters.VIDEO | filters.Document.ALL, media_handler))

    # معالجة النصوص
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # تشغيل البوت
    print("🤖 البوت يعمل الآن بنجاح مع جميع التحسينات...")
    print(f"📊 تم تشغيل البوت في: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    app.run_polling()

if __name__ == "__main__":
    main()

import os
import asyncio
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# استيراد المعالجات من الملفات المختلفة
from handlers import start_handler, media_handler, text_handler, callback_query_handler, photo_handler
from admin_panel import panel_handler, admin_callback_handler
from utils import auto_clear_cache

# إعدادات الـ Logging لمراقبة عمل البوت
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get("BOT_TOKEN")

def main():
    if not TOKEN:
        print("❌ خطأ: لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")
        return

    # بناء تطبيق البوت
    app = Application.builder().token(TOKEN).build()

    # إعداد المهام الدورية (تنظيف الملفات المؤقتة كل 10 دقائق)
    if app.job_queue:
        app.job_queue.run_repeating(
            lambda _: asyncio.create_task(auto_clear_cache()), 
            interval=600, 
            first=10
        )

    # --- ترتيب المعالجات (Handlers) - المهم الترتيب من الأخص إلى الأعم ---

    # 1. الأوامر الأساسية (Commands)
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("panel", panel_handler))

    # 2. معالجة الأزرار التفاعلية (Callback Queries)
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^(admin_|toggle_|close_admin)"))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # 3. ✅ معالج الصور (الأخص) - هذا كان مفقوداً!
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    # 4. معالج الوسائط (الصوت والفيديو)
    app.add_handler(MessageHandler(filters.AUDIO | filters.VIDEO | filters.Document.ALL, media_handler))

    # 5. معالج النصوص (الأعم - يأتي أخيراً)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # تشغيل البوت
    print("🤖 البوت يعمل الآن بنجاح مع دعم الصور...")
    app.run_polling()

if __name__ == "__main__":
    main()

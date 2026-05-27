import sqlite3
from telegram import Update
from telegram.ext import ContextTypes
from utils import DB_FILE, OWNER_ID
import utils

# هذه هي الدالة التي كانت مفقودة وتسببت في الخطأ
async def panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح لوحة تحكم المالك"""
    if update.effective_user.id != OWNER_ID:
        return # تجاهل إذا لم يكن المالك

    from keyboards import admin_panel_keyboard
    
    await update.message.reply_text(
        "🛠 **لوحة تحكم المطور**\n\nيمكنك التحكم في وضع الصيانة، رؤية الإحصائيات، أو عمل إذاعة للمستخدمين من هنا:",
        reply_markup=admin_panel_keyboard(utils.MAINTENANCE_MODE)
    )

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المعالجة الخاصة بأزرار لوحة التحكم"""
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("🚫 غير مصرح لك!", show_alert=True)
        return

    from keyboards import admin_panel_keyboard

    if query.data == "admin_stats":
        conn = sqlite3.connect(DB_FILE)
        users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        conn.close()
        
        await query.edit_message_text(
            f"📊 **إحصائيات البوت الشاملة:**\n\n"
            f"👤 عدد المشتركين: {users_count}\n"
            f"📁 العمليات الناجحة: {files_count}",
            reply_markup=admin_panel_keyboard(utils.MAINTENANCE_MODE)
        )

    elif query.data == "toggle_maintenance":
        # تغيير حالة الصيانة في ملف utils
        utils.MAINTENANCE_MODE = not utils.MAINTENANCE_MODE
        status_text = "تفعيل" if utils.MAINTENANCE_MODE else "إيقاف"
        
        await query.answer(f"✅ تم {status_text} وضع الصيانة")
        await query.edit_message_reply_markup(reply_markup=admin_panel_keyboard(utils.MAINTENANCE_MODE))

    elif query.data == "admin_broadcast":
        context.user_data['admin_step'] = 'broadcasting'
        await query.edit_message_text("📢 أرسل الآن الرسالة (نص فقط) ليتم عمل إذاعة لجميع المستخدمين:")

    elif query.data == "close_admin":
        await query.message.delete()

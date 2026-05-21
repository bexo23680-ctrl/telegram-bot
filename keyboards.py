from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# القائمة الرئيسية المحسنة
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("▶️ تشغيل البوت")],
        [KeyboardButton("🎵 تعديل الأغاني"), KeyboardButton("🎬 استخراج من الفيديو")],
        [KeyboardButton("🖼️ أغنيتي (القائمة المتكاملة)")],
        [KeyboardButton("📊 إحصائياتي"), KeyboardButton("↩️ التراجع عن آخر عملية")],
        [KeyboardButton("🔙 الرجوع إلى البداية")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# قائمة أغنيتي الداخلية المحسنة
def my_song_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎵 تعديل أغنية (اسم + صورة)", callback_data="mysong_edit")],
        [InlineKeyboardButton("🎬 استخراج من فيديو + صورة", callback_data="mysong_extract")],
        [InlineKeyboardButton("✨ أغنية جديدة + صورة", callback_data="mysong_new")],
        [InlineKeyboardButton("📊 إحصائياتي", callback_data="my_stats")],
        [InlineKeyboardButton("↩️ التراجع عن آخر عملية", callback_data="undo_last")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")]
    ]
    return InlineKeyboardMarkup(keyboard)

# قائمة اختيار الجودة المحسنة
def quality_keyboard(action_type):
    keyboard = [
        [
            InlineKeyboardButton("🎵 128k", callback_data=f"q_128_{action_type}"),
            InlineKeyboardButton("🎵 192k (موصى)", callback_data=f"q_192_{action_type}"),
        ],
        [
            InlineKeyboardButton("🎵 256k", callback_data=f"q_256_{action_type}"),
            InlineKeyboardButton("🎵 320k (أعلى جودة)", callback_data=f"q_320_{action_type}"),
        ],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")]
    ]
    return InlineKeyboardMarkup(keyboard)

# لوحة تحكم الإدارة المحسنة
def admin_panel_keyboard(maintenance_status):
    m_text = "🔴 إيقاف الصيانة" if maintenance_status else "🟢 تفعيل الصيانة"
    keyboard = [
        [InlineKeyboardButton("📊 إحصائيات البوت الشاملة", callback_data="admin_stats")],
        [InlineKeyboardButton("📈 إحصائيات متقدمة", callback_data="admin_advanced_stats")],
        [InlineKeyboardButton(m_text, callback_data="toggle_maintenance")],
        [InlineKeyboardButton("📢 إذاعة (Broadcast)", callback_data="admin_broadcast")],
        [InlineKeyboardButton("💾 نسخ احتياطي للقاعدة", callback_data="admin_backup")],
        [InlineKeyboardButton("🗑️ تنظيف الملفات المؤقتة", callback_data="admin_cleanup")],
        [InlineKeyboardButton("❌ إغلاق اللوحة", callback_data="close_admin")]
    ]
    return InlineKeyboardMarkup(keyboard)

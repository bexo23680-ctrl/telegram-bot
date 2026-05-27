from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# القائمة الرئيسية (مع زر تشغيل البوت)
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("▶️ تشغيل البوت")],
        [KeyboardButton("🎵 تعديل الأغنية"), KeyboardButton("🎬 استخراج صوت من فيديو")],
        [KeyboardButton("🖼️ إنشاء أغنية كاملة (اسم + صورة + صوت)")],
        [KeyboardButton("📊 إحصائياتي"), KeyboardButton("🛠 لوحة التحكم")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# قائمة أغنيتي الداخلية
def my_song_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 تعديل اسم وصورة أغنية", callback_data="mysong_edit")],
        [InlineKeyboardButton("🎬 استخراج صوت من فيديو + إضافة صورة", callback_data="mysong_extract")],
        [InlineKeyboardButton("🆕 رفع ملف صوتي جديد + صورة", callback_data="mysong_new")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")]
    ]
    return InlineKeyboardMarkup(keyboard)

# قائمة اختيار الجودة
def quality_keyboard(action_type):
    keyboard = [
        [
            InlineKeyboardButton("🎵 128kbps", callback_data=f"q_128_{action_type}"),
            InlineKeyboardButton("🎵 192kbps", callback_data=f"q_192_{action_type}"),
        ],
        [
            InlineKeyboardButton("🎵 256kbps", callback_data=f"q_256_{action_type}"),
            InlineKeyboardButton("🎵 320kbps", callback_data=f"q_320_{action_type}"),
        ],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")]
    ]
    return InlineKeyboardMarkup(keyboard)

# لوحة تحكم الإدارة
def admin_panel_keyboard(maintenance_status):
    m_text = "🔴 إيقاف الصيانة" if maintenance_status else "🟢 تفعيل الصيانة"
    keyboard = [
        [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats")],
        [InlineKeyboardButton(m_text, callback_data="toggle_maintenance")],
        [InlineKeyboardButton("📢 إذاعة (Broadcast)", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🗑 تنظيف الملفات المؤقتة", callback_data="admin_clean")],
        [InlineKeyboardButton("❌ إغلاق اللوحة", callback_data="close_admin")]
    ]
    return InlineKeyboardMarkup(keyboard)

# زر إلغاء العملية
def cancel_keyboard():
    keyboard = [[InlineKeyboardButton("❌ إلغاء العملية", callback_data="cancel_action")]]
    return InlineKeyboardMarkup(keyboard)

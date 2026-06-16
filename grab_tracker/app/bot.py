from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, MessageHandler, CommandHandler, CallbackQueryHandler,
    filters, ContextTypes,
)
import re
import asyncio
import logging

_LOGGER = logging.getLogger(__name__)
GRAB_URL_RE = re.compile(r'https://app\.grab\.com/s/\S+')

# Registered with Telegram (setMyCommands) so typing "/" shows the menu.
COMMANDS = [
    ("list", "Senarai pesanan aktif (muat semula / henti)"),
    ("poll", "Semak status serta-merta sekarang"),
    ("config", "Tetapan (mesej nyahpepijat, pin lokasi)"),
    ("restart", "Hentikan semua penjejakan & kosongkan cache"),
    ("help", "Tunjukkan arahan tersedia"),
]

# Settings exposed as on/off toggles in /config (label, settings key).
TOGGLE_SETTINGS = [
    ("Mesej nyahpepijat", "debug_messages"),
    ("Pin lokasi pemandu", "send_driver_location"),
]

class TelegramBot:
    def __init__(self, token: str, notify_chat_id: str = None, version: str = "unknown",
                 allowed_chat_ids: str = None):
        self.app = Application.builder().token(token).build()
        self.tracker = None
        self.notify_chat_id = notify_chat_id or None
        self.version = version
        # Allowlist: empty => open to all. If set, notify_chat_id is implicitly allowed.
        self.allowed = {c.strip() for c in str(allowed_chat_ids or "").split(",") if c.strip()}
        if self.allowed and self.notify_chat_id:
            self.allowed.add(str(self.notify_chat_id))

    def _authorized(self, update: Update) -> bool:
        if not self.allowed:
            return True
        chat = update.effective_chat
        return chat is not None and str(chat.id) in self.allowed

    def set_tracker(self, tracker):
        self.tracker = tracker
        self.app.add_handler(CommandHandler("poll", self._cmd_poll))
        self.app.add_handler(CommandHandler("restart", self._cmd_restart))
        self.app.add_handler(CommandHandler("config", self._cmd_config))
        self.app.add_handler(CommandHandler("list", self._cmd_list))
        self.app.add_handler(CommandHandler(["help", "start"], self._cmd_help))
        self.app.add_handler(CallbackQueryHandler(self._on_config_toggle, pattern=r"^toggle:"))
        self.app.add_handler(CallbackQueryHandler(self._on_order_action, pattern=r"^[rk]:"))
        # URL handler last so commands take precedence.
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle))

    async def _handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorized(update):
            return  # silently ignore messages from non-allowlisted chats
        text = update.message.text or ""
        chat_id = str(update.effective_chat.id)
        match = GRAB_URL_RE.search(text)
        if match and self.tracker:
            await self.tracker.start_tracking(match.group(), chat_id)

    async def _cmd_poll(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorized(update):
            await update.message.reply_text("⛔ Tiada kebenaran untuk menggunakan bot ini.")
            return
        chat_id = str(update.effective_chat.id)
        n = self.tracker.force_poll(chat_id) if self.tracker else 0
        if n:
            await update.message.reply_text(f"🔄 Memaksa semakan segera untuk {n} pesanan aktif…")
        else:
            await update.message.reply_text("Tiada pesanan aktif untuk disemak sekarang.")

    async def _cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorized(update):
            await update.message.reply_text("⛔ Tiada kebenaran untuk menggunakan bot ini.")
            return
        n = await self.tracker.restart_all() if self.tracker else 0
        await update.message.reply_text(
            f"♻️ Penjejakan ditetapkan semula — {n} pesanan aktif dan cache dikosongkan.\n"
            "_(Menetapkan semula keadaan bot, bukan kontena add-on.)_",
            parse_mode="Markdown",
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorized(update):
            await update.message.reply_text("⛔ Tiada kebenaran untuk menggunakan bot ini.")
            return
        lines = [f"🛵 *Penjejak Grab v{self.version}*", "",
                 "Hantar pautan kongsi Grab untuk mula menjejak.", "", "*Arahan:*"]
        lines += [f"/{name} — {desc}" for name, desc in COMMANDS]
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._authorized(update):
            await update.message.reply_text("⛔ Tiada kebenaran untuk menggunakan bot ini.")
            return
        chat_id = str(update.effective_chat.id)
        items = [i for i in self.tracker.list_active() if i["chat_id"] == chat_id]
        if not items:
            await update.message.reply_text("Tiada pesanan aktif sedang dijejak.")
            return
        for i in items:
            text = f"🛵 *Slot {i['slot']}* — {i.get('status') or '—'}"
            if i.get("booking_code"):
                text += f"\nTempahan: `{i['booking_code']}`"
            if i.get("dropoff"):
                text += f"\nKe: {i['dropoff']}"
            text += f"\n_Semakan #{i.get('poll_count', 0)}_"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Muat semula", callback_data=f"r:{i['slot']}"),
                InlineKeyboardButton("🛑 Henti", callback_data=f"k:{i['slot']}"),
            ]])
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    async def _on_order_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not self._authorized(update):
            await query.answer("Tiada kebenaran")
            return
        await query.answer()
        action, _, raw = (query.data or "").partition(":")
        try:
            slot = int(raw)
        except ValueError:
            return
        token = self.tracker.slots.token(slot)
        if not token or token not in self.tracker.active:
            await query.edit_message_text("Pesanan ini tidak lagi aktif.")
            return
        base = query.message.text or ""
        if action == "r":
            self.tracker.force_poll_token(token)
            await query.edit_message_text(base + "\n\n🔄 Permintaan muat semula dihantar.")
        elif action == "k":
            await self.tracker.kill(token)
            await query.edit_message_text(base + "\n\n🛑 Penjejakan dihentikan.")

    async def _cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = await self.tracker.db.get_settings()
        await update.message.reply_text(
            "⚙️ *Tetapan* — ketik untuk togol:", parse_mode="Markdown",
            reply_markup=self._config_keyboard(settings),
        )

    async def _on_config_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not self._authorized(update):
            await query.answer("Tiada kebenaran")
            return
        await query.answer()
        key = (query.data or "").split(":", 1)[-1]
        if key in {k for _, k in TOGGLE_SETTINGS}:
            settings = await self.tracker.db.get_settings()
            new_value = "0" if settings.get(key) == "1" else "1"
            await self.tracker.update_setting(key, new_value)  # syncs DB + MQTT config entity
            settings = await self.tracker.db.get_settings()
            await query.edit_message_reply_markup(reply_markup=self._config_keyboard(settings))

    def _config_keyboard(self, settings) -> InlineKeyboardMarkup:
        rows = []
        for label, key in TOGGLE_SETTINGS:
            state = "HIDUP ✅" if settings.get(key) == "1" else "MATI ❌"
            rows.append([InlineKeyboardButton(f"{label}: {state}", callback_data=f"toggle:{key}")])
        return InlineKeyboardMarkup(rows)

    async def send_text(self, chat_id: str, text: str, **kwargs):
        if not chat_id:
            return  # web-initiated tracking with no notify_chat_id configured
        await self.app.bot.send_message(chat_id=int(chat_id), text=text, **kwargs)

    async def send_location(self, chat_id: str, lat: float, lng: float):
        if not chat_id:
            return
        await self.app.bot.send_location(chat_id=int(chat_id), latitude=lat, longitude=lng)

    async def _retry(self, coro_factory, what, attempts=6):
        """Retry a network-sensitive startup step so a transient Telegram outage at boot
        doesn't crash the add-on into a restart loop."""
        for i in range(1, attempts + 1):
            try:
                return await coro_factory()
            except Exception as e:
                if i == attempts:
                    raise
                delay = min(5 * i, 30)
                _LOGGER.warning(f"{what} failed ({i}/{attempts}): {e}; retrying in {delay}s")
                await asyncio.sleep(delay)

    async def start(self):
        await self._retry(self.app.initialize, "bot initialize")
        await self.app.start()
        try:
            # Register commands so the Telegram client shows them when "/" is typed.
            await self.app.bot.set_my_commands([BotCommand(n, d) for n, d in COMMANDS])
        except Exception as e:
            _LOGGER.warning(f"Could not set bot commands: {e}")
        await self._retry(self.app.updater.start_polling, "start polling")
        # Startup notice is sent by main.py (so it can include restart-stopped count).

    async def stop(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

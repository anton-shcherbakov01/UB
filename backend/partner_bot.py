import os
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.future import select

from database import AsyncSessionLocal, Partner, Lead, User, PayoutRequest, Payment

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PartnerBot")

# Конфигурация
PARTNER_BOT_TOKEN = os.getenv("PARTNER_BOT_TOKEN")
ADMIN_ID = 901378787 # Ваш ID
MIN_PAYOUT = 2000

if not PARTNER_BOT_TOKEN:
    logger.error("PARTNER_BOT_TOKEN not found in env vars!")
    exit(1)

bot = Bot(token=PARTNER_BOT_TOKEN)
dp = Dispatcher()

# --- КЛАВИАТУРЫ ---

def get_main_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔗 Моя ссылка"), KeyboardButton(text="🔍 Проверить лида")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="💳 Вывод средств")],
        [KeyboardButton(text="📚 Обучение"), KeyboardButton(text="🆘 Поддержка")]
    ], resize_keyboard=True)

# --- UTILS ---

async def get_or_create_partner(session, user_id, username):
    result = await session.execute(select(Partner).where(Partner.user_id == user_id))
    partner = result.scalars().first()
    if not partner:
        partner = Partner(user_id=user_id, username=username)
        session.add(partner)
        await session.commit()
    return partner

def clean_username(text):
    if not text: return None
    return text.replace("@", "").replace("https://t.me/", "").strip().lower()

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    async with AsyncSessionLocal() as session:
        await get_or_create_partner(session, message.from_user.id, message.from_user.username)
    
    text = (
        "👋 <b>Привет, будущий миллионер!</b>\n\n"
        "Это партнерский бот <b>JuicyStat</b>. Мы платим <b>500₽</b> за каждого селлера, которого ты приведешь.\n\n"
        "🔻 <b>Твои инструменты:</b>\n"
        "1. Персональная ссылка (ведет сразу в приложение).\n"
        "2. Система проверки лидов (чтобы не пересекаться с другими).\n"
        "3. Статистика и вывод денег.\n\n"
        "👇 Жми кнопку, чтобы начать."
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@dp.message(F.text == "🔗 Моя ссылка")
async def btn_link(message: types.Message):
    user_id = message.from_user.id
    # Глубокая ссылка на Mini App
    link = f"https://t.me/juicystat_bot/juicystat?startapp=agent_{user_id}"
    
    text = (
        "🎯 <b>Твоя боевая ссылка:</b>\n"
        f"<code>{link}</code>\n\n"
        "<b>Твой оффер для клиентов (Продавай пользу!):</b>\n"
        "«Держи ссылку на бесплатный доступ к JuicyStat. <b>3 дня тарифа PRO (Analyst) в подарок!</b>»\n\n"
        "<b>Как ты заработаешь:</b>\n"
        "1. Человек переходит, видит халявный PRO тариф.\n"
        "2. Пользуется 3 дня, видит свои цифры и подсаживается.\n"
        "3. Покупает продление.\n"
        "4. Тебе прилетает <b>500₽</b> с первой оплаты."
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔍 Проверить лида")
async def btn_check_lead_prompt(message: types.Message):
    await message.answer(
        "Пришли мне <b>@username</b> (или ссылку) селлера, которому хочешь написать.\n"
        "Я проверю, не занят ли он.",
        parse_mode="HTML"
    )

@dp.message(F.text.startswith("@") | F.text.contains("t.me/"))
async def check_lead_logic(message: types.Message):
    target_username = clean_username(message.text)
    if not target_username:
        await message.answer("Некорректный юзернейм.")
        return

    agent_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        # 1. Проверяем, не клиент ли он уже
        u_stmt = select(User).where(User.username.ilike(target_username))
        u_res = await session.execute(u_stmt)
        existing_user = u_res.scalars().first()

        if existing_user:
            await message.answer(
                "❌ <b>Лид недоступен.</b>\n"
                f"Пользователь @{target_username} уже пользуется сервисом.",
                parse_mode="HTML"
            )
            return

        # 2. Проверяем таблицу Leads
        l_stmt = select(Lead).where(Lead.username == target_username)
        l_res = await session.execute(l_stmt)
        lead = l_res.scalars().first()
        
        now = datetime.utcnow()

        if lead:
            if lead.reserved_by_partner_id != agent_id and lead.expires_at > now:
                await message.answer(
                    "⛔️ <b>Лид занят.</b>\n"
                    "С этим человеком уже работает другой партнер. Не пиши ему, это будет спам.\n"
                    f"Освободится через: {lead.expires_at - now}",
                    parse_mode="HTML"
                )
                return
            
            if lead.status == 'converted':
                await message.answer("❌ Лид уже стал клиентом.")
                return

        # 3. Бронируем!
        expires = now + timedelta(hours=24)
        if lead:
            lead.reserved_by_partner_id = agent_id
            lead.reserved_at = now
            lead.expires_at = expires
            lead.status = 'reserved'
        else:
            lead = Lead(
                username=target_username,
                reserved_by_partner_id=agent_id,
                reserved_at=now,
                expires_at=expires,
                status='reserved'
            )
            session.add(lead)
        
        await session.commit()

        await message.answer(
            "✅ <b>Лид свободен и забронирован!</b>\n\n"
            f"Пользователь @{target_username} закреплен за тобой на <b>24 часа</b>.\n"
            "Действуй! Скидывай ему свою ссылку в ЛС.",
            parse_mode="HTML"
        )

@dp.message(F.text == "📊 Статистика")
async def btn_stats(message: types.Message):
    user_id = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        partner = await get_or_create_partner(session, user_id, message.from_user.username)
        
        q_refs = select(User).where(User.referrer_id == user_id)
        res_refs = await session.execute(q_refs)
        refs = res_refs.scalars().all()
        
        ref_ids = [u.id for u in refs]
        paid_count = 0
        if ref_ids:
            q_pays = select(Payment).where(
                Payment.user_id.in_(ref_ids),
                Payment.status == 'succeeded'
            )
            res_pays = await session.execute(q_pays)
            paid_count = len(res_pays.scalars().all())

    reg_count = len(refs)
    conversion = round((paid_count / reg_count * 100), 1) if reg_count > 0 else 0
    
    text = (
        "💼 <b>Твой кабинет:</b>\n\n"
        f"👣 Переходов/Регистраций: <b>{reg_count}</b>\n"
        f"💰 Оплат (Завершенных): <b>{paid_count}</b> (Конверсия {conversion}%)\n"
        f"💵 Баланс: <b>{partner.balance}₽</b>\n"
        f"🏆 Всего заработано: <b>{partner.total_earned}₽</b>\n\n"
        "Минимальная сумма для вывода: 2000₽"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "💳 Вывод средств")
async def btn_payout(message: types.Message):
    user_id = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        partner = await get_or_create_partner(session, user_id, message.from_user.username)
        
        if partner.balance < MIN_PAYOUT:
            diff = MIN_PAYOUT - partner.balance
            await message.answer(
                f"⚠️ Недостаточно средств.\n"
                f"Твой баланс: {partner.balance}₽\n"
                f"Минимум для вывода: {MIN_PAYOUT}₽\n"
                f"Осталось заработать: {diff}₽"
            )
            return

        await message.answer(
            "💰 <b>Заявка на вывод</b>\n\n"
            "Напиши одним сообщением:\n"
            "1. Банк\n"
            "2. Номер карты (или телефона СБП)\n"
            "3. ФИО получателя\n\n"
            "<i>Начни сообщение со слова 'Реквизиты'</i>",
            parse_mode="HTML"
        )

@dp.message(F.text.lower().startswith("реквизиты"))
async def process_payout(message: types.Message):
    user_id = message.from_user.id
    details = message.text
    
    async with AsyncSessionLocal() as session:
        partner = await get_or_create_partner(session, user_id, message.from_user.username)
        
        if partner.balance < MIN_PAYOUT:
            await message.answer("Ошибка: Баланс изменился и стал меньше минимума.")
            return

        amount = partner.balance
        req = PayoutRequest(
            partner_id=user_id,
            amount=amount,
            details=details,
            status='pending'
        )
        session.add(req)
        
        partner.balance = 0
        session.add(partner)
        
        await session.commit()
        
        admin_text = (
            f"🔔 <b>ЗАЯВКА НА ВЫВОД!</b>\n"
            f"Агент: @{message.from_user.username} (ID {user_id})\n"
            f"Сумма: {amount}₽\n"
            f"Данные: {details}"
        )
        try:
            await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
        except:
            logger.error("Failed to notify admin")

    await message.answer("✅ Заявка принята! Выплата будет произведена в течение 24 часов.")

@dp.message(F.text == "📚 Обучение")
async def btn_training(message: types.Message):
    await message.answer(
        "Все скрипты, видео, баннеры и правила лежат в нашем закрытом канале.\n"
        "Обязательно подпишись, там мы постим новости и топы лучших агентов.\n\n"
        "👉 https://t.me/+er6o69YWTDw2ODBi"
    )

@dp.message(F.text == "🆘 Поддержка")
async def btn_support(message: types.Message):
    await message.answer(
        f"По всем вопросам пиши главному: @AAntonShch"
    )

async def main():
    logger.info("Starting Partner Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
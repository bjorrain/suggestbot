import telebot as tb
import yaml
from types import SimpleNamespace
import logging
from os import listdir as ls
from os import remove as rm
import datetime

logging.basicConfig(level=logging.INFO)
with open("config.yaml") as f:
    config = SimpleNamespace(**yaml.safe_load(f))
    bot = tb.TeleBot(config.token, parse_mode="HTML")


def get_last() -> int:
    with open("last") as F:
        return int(F.read())


def set_last(last: int):
    with open("last", "w") as F:
        F.write(str(last))


def gen_approve_keyboard(approved: int, rejected: int) -> tb.types.InlineKeyboardMarkup:
    """Генерирует клавиатуру для голосования"""
    keyboard = tb.types.InlineKeyboardMarkup()
    keyboard.row(
        tb.types.InlineKeyboardButton(f"Постим ({approved})", callback_data="approve"),
        tb.types.InlineKeyboardButton(
            f"Не постим ({rejected})", callback_data="reject"
        ),
    )
    keyboard.add(
        tb.types.InlineKeyboardButton("Кто автор?", callback_data="get_author")
    )
    return keyboard


@bot.message_handler(commands=["start"])
def start(message: tb.types.Message):
    with open(f"chats/{message.chat.id}.yaml", "w") as F:
        pass
    bot.reply_to(
        message,
        tb.formatting.escape_html(
            "Привет! Я - предложка. Отправь мне то, что хочешь увидеть в канале. На данный момент я не умею корректно обрабатывать группы файлов, поэтому, пожалуйста, отправляй их по одному (админы поймут)"
        ),
    )
    bot.register_next_step_handler(message, suggest)


@bot.message_handler(func=lambda msg: msg.text.startswith("/broadcast"))
def broadcast(msg: tb.types.Message):
    if msg.from_user.id in config.admins:
        text = msg.text[10::]
        for i in ls("chats"):
            i = int(i[:-5:])
            try:
                bot.send_message(i, text, reply_markup=None)
            except Exception as e:
                bot.send_message(config.admin_chat, str(e))


def autosend_no_id(chat_id: int, message: tb.types.Message, reply_markup=None):
    content_type = message.content_type
    content_mapping = {
        "text": lambda chat_id, *args, **kwargs: bot.send_message(
            chat_id=chat_id,
            text=message.text,
            entities=message.entities,
            *args,
            **kwargs,
        ),
        "photo": lambda chat_id, *args, **kwargs: bot.send_photo(
            chat_id,
            message.photo[-1].file_id,
            caption=f"{message.caption}",
            caption_entities=message.caption_entities,
            *args,
            **kwargs,
        ),
        "document": lambda chat_id, *args, **kwargs: bot.send_document(
            chat_id,
            message.document.file_id,
            caption=f"{message.caption}",
            caption_entities=message.caption_entities,
            *args,
            **kwargs,
        ),
        "video": lambda chat_id, *args, **kwargs: bot.send_video(
            chat_id,
            message.video.file_id,
            caption=f"#{message.id} {message.caption}",
            caption_entities=message.caption_entities,
            *args,
            **kwargs,
        ),
        "sticker": lambda chat_id, *args, **kwargs: bot.send_sticker(
            chat_id, message.sticker.file_id, *args, **kwargs
        ),
        "animation": lambda chat_id, *args, **kwargs: bot.send_animation(
            chat_id, message.animation.file_id, *args, **kwargs
        ),
    }

    if content_type not in content_mapping:
        raise ValueError(f"Unsupported content type: {content_type}")

    return content_mapping[content_type](chat_id, reply_markup=reply_markup)


def autosend_with_id(chat_id: int, message: tb.types.Message, reply_markup=None):
    content_type = message.content_type
    last = get_last() + 1
    set_last(last)
    content_mapping = {
        "text": lambda chat_id, *args, **kwargs: bot.send_message(
            chat_id=chat_id,
            text=f"#{last}\n{message.text}",
            *args,
            **kwargs,
        ),
        "photo": lambda chat_id, *args, **kwargs: bot.send_photo(
            chat_id,
            message.photo[-1].file_id,
            caption=f"#{last}\n{message.caption}",
            caption_entities=message.caption_entities,
            *args,
            **kwargs,
        ),
        "document": lambda chat_id, *args, **kwargs: bot.send_document(
            chat_id,
            message.document.file_id,
            caption=f"#{last}\n{message.caption}",
            caption_entities=message.caption_entities,
            *args,
            **kwargs,
        ),
        "video": lambda chat_id, *args, **kwargs: bot.send_video(
            chat_id,
            message.video.file_id,
            caption=f"#{last}\n{message.caption}",
            caption_entities=message.caption_entities,
            *args,
            **kwargs,
        ),
        "sticker": lambda chat_id, *args, **kwargs: bot.send_sticker(
            chat_id, message.sticker.file_id, *args, **kwargs
        ),
        "animation": lambda chat_id, *args, **kwargs: bot.send_animation(
            chat_id, message.animation.file_id, *args, **kwargs
        ),
    }
    if content_type not in content_mapping:
        raise ValueError(f"Unsupported content type: {content_type}")

    return content_mapping[content_type](chat_id, reply_markup=reply_markup)


def suggest(message: tb.types.Message):
    logging.info(message.content_type)
    try:
        with open(
            f"""messages/{autosend_no_id(config.admin_chat, message, reply_markup=gen_approve_keyboard(0, 0)).message_id}""",
            "w",
        ) as F:
            yaml.safe_dump(
                {"approved": [], "rejected": [], "author": message.from_user.id}, F
            )
    except ValueError:
        bot.reply_to(message, tb.formatting.escape_html("Неподдерживаемое вложение."))
        logging.warn(message.content_type)
        return
    rk = tb.types.InlineKeyboardMarkup()
    rk.add(tb.types.InlineKeyboardButton("отправить еще", callback_data="send_more"))
    bot.reply_to(message, "Принято.", reply_markup=rk)
    return


@bot.callback_query_handler(func=lambda call: call.data in ["approve", "reject"])
def callback_inline(call):
    with open(f"messages/{call.message.message_id}", "r+") as F:
        data = yaml.safe_load(F)
        data["approved"] = set(data.get("approved"))
        data["rejected"] = set(data.get("rejected"))
        logging.info(f"{call.from_user.id}: {call.data}", data)
        threshold = (
            1
            if config.mode == "one"
            else bot.get_chat_member_count(config.admin_chat) - 1
        )
        if call.data == "approve":
            data["approved"].add(call.from_user.id)
            if call.from_user.id in data["rejected"]:
                data["rejected"].remove(call.from_user.id)
            call.message
            if len(data["approved"]) >= threshold:
                autosend_with_id(config.channel, call.message)

        else:
            data["rejected"].add(call.from_user.id)
            if call.from_user.id in data["approved"]:
                data["approved"].remove(call.from_user.id)
        yaml.dump(data, F)
        try:
            bot.edit_message_reply_markup(
                config.admin_chat,
                call.message.message_id,
                reply_markup=gen_approve_keyboard(
                    len(data["approved"]), len(data["rejected"])
                ),
            )
        except Exception as E:
            bot.send_message(config.admin_chat, str(E))


@bot.callback_query_handler(func=lambda call: call.data == "send_more")
def getsuggest(call):
    bot.reply_to(
        call.message,
        tb.formatting.escape_html("Отправляй."),
    )
    bot.register_next_step_handler(call.message, suggest)


@bot.callback_query_handler(func=lambda call: call.data == "get_author")
def get_author(call):
    if call.from_user.id in config.admins:
        with open(f"messages/{call.message.message_id}", "r+") as F:
            f: dict = yaml.safe_load(F)
            try:
                user = bot.get_chat_member(config.channel, f.get("author")).user
                bot.reply_to(
                    call.message,
                    f"автор: {'@' + user.username if user.username else 'tg://user?id=' + str(user.id)}",
                )
            except Exception as E:
                bot.send_message(config.admin_chat, str(E))


def ban(uid: int, reason: str):
    if str(uid) not in ls("banned_users"):
        with open("banned_users/" + str(uid), "w") as F:
            yaml.safe_dump(
                {"date": datetime.date.today, "reason": reason, "unban_votes": []}
            )
            return 0
    return 1


def unban(uid: int):
    if str(uid) in ls("banned_users"):
        rm("banned_users/" + str(uid))
        return 0
    return 1


def generate_unban_markup(uid):
    with open("banned_users/" + str(uid), "r") as F:
        ub = yaml.safe_load(F).get("unban_votes")
    return tb.util.quick_markup({f"за разбан ({len(ub)})": {"callback_data": "unban"}})


@bot.callback_query_handler(func=lambda call: call.data.startswith("voteunban_"))
def unban_vote(call):
    uid = call.data.split("_")[1]
    with open("banned_users/" + str(uid), "r") as F:
        ub = yaml.safe_load(F).get("unban_votes")


@bot.callback_query_handler(func=lambda call: call.data.startswith("unban_"))
def unban_handler(call):
    uid = call.data.split("_")[1]
    with open("banned_users/" + str(uid), "r") as F:
        ub = yaml.safe_load(F).get("unban_votes")


@bot.message_handler(commands=["get_banned"])
def get_banned(msg: tb.types.Message):
    if msg.from_user.id in config.admins:
        for i in ls("banned_users"):
            with open("banned_users/" + i) as F:
                kb = tb.types.InlineKeyboardMarkup()
                kb.add(
                    tb.types.InlineKeyboardButton(
                        f"постим ({approved})", callback_data="approve"
                    )
                )
                bot.reply_to(msg, f"""- id: {i} \n """ + F.read())


bot.infinity_polling()

import json
import logging
import os
import signal
import typing
import urllib.parse
from functools import wraps

import boto3
import requests
from google.cloud import translate
from requests.exceptions import ReadTimeout, ConnectTimeout, HTTPError
from telegram import Update, ChatAction, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Updater,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
GOOGLE_API_TOKEN = os.getenv("GOOGLE_API_TOKEN")
GOOGLE_SEARCH_CONTEXT = os.getenv("GOOGLE_SEARCH_CONTEXT")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
SEARCH_CATEGORY = os.getenv("SEARCH_CATEGORY")
GOOGLE_CREDENTIALS_SECRET_NAME = os.getenv("GOOGLE_CREDENTIALS_SECRET_NAME")
ALLOWED_USERS = [int(u) for u in filter(None, (os.getenv("ALLOWED_USERS") or "").split(","))]


def handle_sigterm(*args):
    raise KeyboardInterrupt()


def restricted(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if ALLOWED_USERS and user_id not in ALLOWED_USERS:
            print("Unauthorized access denied for {}.".format(user_id))
            update.message.reply_text("Тебе не разрешено пользоваться этим ботом. Спроси владельца :)")
            return
        return func(update, context, *args, **kwargs)

    return wrapped


def get_secret(name) -> typing.Dict:
    logger.info(f"Getting secret {name}")
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=name)
    if "SecretString" in response:
        return json.loads(response["SecretString"])


def find_pics(query: str, start_from=1) -> typing.List[str]:
    query = urllib.parse.quote_plus(f"{SEARCH_CATEGORY} {query}".strip())
    url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_TOKEN}&cx={GOOGLE_SEARCH_CONTEXT}&q={query}&imgType=animated&searchType=image&start={start_from}&fields=items(link,mime)"
    response = requests.request("GET", url, headers={}, data={})
    response.raise_for_status()
    result = response.json()
    ret = []
    if "items" in result:
        for item in result["items"]:
            link = item["link"]
            if item["mime"] != "image/gif":
                continue
            try:
                response = requests.request("HEAD", link, timeout=1)
                if response.status_code <= 299:
                    ret.append(link)
                else:
                    logger.warning(f"Error {response.status_code} checking url {link}")
            except (ReadTimeout, ConnectTimeout):
                logger.warning(f"Timeout waiting for {link}")
            except Exception as e:
                logger.warning(f"Unknown error while fetching the pic {link}. Error: {e}")

    return ret


GOOGLE_CREDENTIALS = {}


def translate_query(query) -> str:
    global GOOGLE_CREDENTIALS
    if GOOGLE_CREDENTIALS_SECRET_NAME and not GOOGLE_CREDENTIALS:
        GOOGLE_CREDENTIALS = get_secret(GOOGLE_CREDENTIALS_SECRET_NAME)

    if not GOOGLE_CREDENTIALS:
        return query

    client = translate.TranslationServiceClient.from_service_account_info(GOOGLE_CREDENTIALS)
    try:
        response = client.translate_text(
            parent=f"projects/{GOOGLE_PROJECT_ID}",
            contents=[query],
            mime_type="text/plain",
            target_language_code="en",
        )
        for translation in response.translations:
            return translation.translated_text

    except Exception as e:
        logger.error(f"Unable to translate text: {query}. Error:", exc_info=e)

    # by default return original text
    return query


@restricted
def start(update: Update, _: CallbackContext):
    logger.info(f"User {update.effective_user.name} joined")
    update.message.reply_text("Привет :) Просто напиши что хочешь найти, и я найду. Например: сосать")


@restricted
def new_search(update: Update, context: CallbackContext) -> None:
    query = update.message.text
    logger.info(f"User {update.effective_user.name} ({update.effective_user.id}) searched for {query}")
    query = translate_query(query)
    logger.info(f"Translated to: {query}")

    find(update, context, 1, query)


def find(update: Update, context: CallbackContext, start_from, query) -> None:
    total_sent = 0
    message = update.message or update.callback_query.message
    while total_sent < 10:
        context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)
        try:
            urls = find_pics(query, start_from=start_from)
        except HTTPError as ex:
            if ex.response.status_code == 429:
                message.reply_text(f"Слишком много поисков :(")
            raise

        if urls:
            total_sent += len(urls)
            start_from += 10
            for url in urls:
                try:
                    message.reply_animation(url, disable_notification=True)
                except BadRequest as e:
                    logger.warning(f"Error replying with url {url}", exc_info=e)
        else:
            message.reply_text(f"Ничего не нашел :(")
            logger.warning(f"Nothing found for query: {query}")
            break

    if total_sent > 0:
        context.user_data["start_from"] = start_from
        context.user_data["query"] = query
        button = [[InlineKeyboardButton("Ещё!", callback_data="/more")]]
        message.reply_text("Поискать ещё?", reply_markup=InlineKeyboardMarkup(button))
    logger.info(f"Total {total_sent} pics sent for query {query}")


def handle_error(_: object, context: CallbackContext):
    # TODO: send message to dev chat:
    # https://github.com/python-telegram-bot/python-telegram-bot/blob/9949b44560b43da6c4ceee4f7387a61feb3bb2d0/examples/errorhandlerbot.py
    logger.error(f"Error handling request: ", exc_info=context.error)


@restricted
def callback_query_handler(update: Update, context: CallbackContext):
    command = update.callback_query.data

    # invoke handler
    if command == "/more":
        if "start_from" in context.user_data and "query" in context.user_data:
            query = context.user_data["query"]
            start_from = int(context.user_data["start_from"])
            logger.info(f"Searching more pics for query '{query}' from offset {start_from}")
            find(update, context, start_from, query)
        else:
            update.callback_query.message.reply_text("А что хотела найти? :)")


def main():
    logger.info("Starting bot...")
    signal.signal(signal.SIGTERM, handle_sigterm)  # to gracefully shutdown in docker

    updater = Updater(token=TELEGRAM_API_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text, new_search))
    dispatcher.add_handler(CallbackQueryHandler(callback_query_handler))

    dispatcher.add_error_handler(handle_error)

    updater.start_polling()
    logger.info("Bot started")
    updater.idle()
    logger.info("Bot stopped")


if __name__ == "__main__":
    main()

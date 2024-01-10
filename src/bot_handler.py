from __future__ import annotations

import asyncio
import base64
import collections
import logging
import os
import random

import openai

from aiogram import F
from aiogram import Bot, Dispatcher, Router, html, types
from aiogram.filters import Command

from config import Config
from chat_completions import TextResponse, ImageResponse


API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, parse_mode='HTML')
router = Router()

config = Config.read_yaml(path=os.getenv('BOT_CONFIG_YAML'))


def extract_message_chain(last_message_in_thread: types.Message, bot_id: int):
    payload = collections.deque()
    cur = last_message_in_thread
    while cur is not None:
        try:
            tmp = cur.reply_to_message
            if tmp is not None:
                role = 'assistant' if tmp.from_user.id == bot_id else 'user'
                if tmp.text:
                    payload.appendleft((role, tmp.text))
                elif tmp.caption:
                    payload.appendleft(
                        (role, f'представь картинку с комментарием {tmp.caption}')
                    )
                cur = tmp
            else:
                break
        except AttributeError:
            break
    payload.append(('user', last_message_in_thread.text))
    return [(role, text) for role, text in payload]


async def react(success, message):
    yes = [
        '👍',
        '❤',
        '🔥',
        '🥰',
        '🎉',
        '🤩',
        '👌',
        '🐳',
        '🌭',
        '🍌',
        '🍓',
        '🍾',
        '💋',
        '🤓',
        '👻',
        '🤗',
        '💅',
        '🆒',
        '💘',
        '🦄',
        '😎',
        '👾',
    ]
    nope = [
        '👎',
        '🤔',
        '🤯',
        '😱',
        '🤬',
        '😢',
        '🥴',
        '🌚',
        '💔',
        '🤨',
        '😐',
        '😴',
        '😭',
        '🙈',
        '😨',
        '🤪',
        '🗿',
        '🙉',
        '💊',
        '🙊',
        '🤷',
        '😡',
    ]
    react = random.choice(yes) if success else random.choice(nope)
    react = types.reaction_type_emoji.ReactionTypeEmoji(type='emoji', emoji=react)
    await message.react(reaction=[react])


@router.message(Command(commands=['blerb'], ignore_mention=True))
async def dump_message_info(message: types.Message):
    logging.info(f'incoming blerb from {message.chat.id}')
    await message.reply(f'chat id: {html.code(message.chat.id)}')


@router.message(Command(commands=['mode_claude'], ignore_mention=True))
async def switch_to_claude(message: types.Message):
    config.override_provider_for_chat_id(message.chat.id, config.PROVIDER_ANTHROPIC)
    await message.reply(f'🤖теперь я на мозгах {config.PROVIDER_ANTHROPIC}!')


@router.message(Command(commands=['mode_chatgpt'], ignore_mention=True))
async def switch_to_chatgpt(message: types.Message):
    config.override_provider_for_chat_id(message.chat.id, config.PROVIDER_OPENAI)
    await message.reply(f'🤖теперь я на мозгах {config.PROVIDER_OPENAI}!')


@router.message(Command(commands=['mode_yandex'], ignore_mention=True))
async def switch_to_yandexgpt(message: types.Message):
    config.override_provider_for_chat_id(message.chat.id, config.PROVIDER_YANDEXGPT)
    await message.reply(f'🤖теперь я на мозгах {config.PROVIDER_YANDEXGPT}!')


@router.message(config.filter_chat_allowed, Command(commands=['prompt']))
async def dump_set_prompt(message: types.Message, command: types.CommandObject):
    new_prompt = command.args
    if not new_prompt:
        await message.reply(config.rich_info(message.chat.id))
        return

    success = config.override_prompt_for_chat(message.chat.id, new_prompt)
    if success:
        await message.answer(
            'okie-dokie 👌 prompt изменён но нет никаких гарантий что это надолго'
        )
    else:
        await message.answer('nope 🙅')


@router.message(config.filter_chat_allowed, Command(commands=['pic']))
async def gimme_pic(message: types.Message, command: types.CommandObject):
    prompt = command.args
    await message.chat.do('upload_photo')
    try:
        response = await ImageResponse.generate(prompt, mode='dall-e')
    except openai.BadRequestError:
        messages_to_send = [config.prompt_message_for_user(message.chat.id)]
        messages_to_send.append(
            (
                'user',
                f'объясни трагикомичной шуткой почему OpenAI не может сгенерировать картинку по запросу "{prompt}"',  # noqa
            )
        )
        await message.chat.do('typing')
        llm_reply = await TextResponse.generate(
            config=config,
            chat_id=message.chat.id,
            messages=messages_to_send,
        )
        await message.answer(llm_reply.text)
        await react(success=False, message=message)
    else:
        await message.chat.do('upload_photo')
        image_from_url = types.URLInputFile(response.b64_or_url)
        caption = f'DALL-E2 prompt: {prompt}'
        await message.answer_photo(image_from_url, caption=caption)
        await react(success=True, message=message)


@router.message(config.filter_chat_allowed, Command(commands=['pik']))
async def gimme_pikk(message: types.Message, command: types.CommandObject):
    prompt = command.args
    await message.chat.do('upload_photo')
    try:
        response = await ImageResponse.generate(prompt, mode='kandinski')
    except openai.BadRequestError:
        messages_to_send = [config.prompt_message_for_user(message.chat.id)]
        messages_to_send.append(
            (
                'user',
                f'объясни шуткой почему нельзя сгенерировать картинку по запросу "{prompt}"',  # noqa
            )
        )
        await message.chat.do('typing')
        llm_reply = await TextResponse.generate(
            config=config,
            chat_id=message.chat.id,
            messages=messages_to_send,
        )
        await message.answer(llm_reply.text)
        await react(success=False, message=message)
    else:
        await message.chat.do('upload_photo')
        if response.censored:
            messages_to_send = [config.prompt_message_for_user(message.chat.id)]
            messages_to_send.append(
                (
                    'user',
                    f'объясни шуткой почему нельзя сгенерировать картинку по запросу "{prompt}"',  # noqa
                )
            )
            await message.chat.do('typing')
            llm_reply = await TextResponse.generate(
                config=config,
                chat_id=message.chat.id,
                messages=messages_to_send,
            )
            await message.answer(llm_reply.text)
            await react(success=False, message=message)
        else:
            # await message.reply(json.dumps(response, indent=4))
            caption = f'Kandinksi-3 prompt: {prompt}'

            im_b64 = response.b64_or_url.encode()
            im_f = base64.decodebytes(im_b64)
            image = types.BufferedInputFile(
                im_f,
                'kandinski.png',
            )

            await message.answer_photo(
                photo=image,
                caption=caption,
            )
            await react(success=True, message=message)


@router.message(config.filter_chat_allowed, Command(commands=['ru', 'en']))
async def translate_ruen(message: types.Message, command: types.CommandObject):
    prompt_tuple = config.fetch_translation_prompt_message(command.command)
    messages_to_send = [prompt_tuple, ('user', command.args)]
    await message.chat.do('typing')
    llm_reply = await TextResponse.generate(
        config=config,
        chat_id=message.chat.id,
        messages=messages_to_send,
    )
    func = message.reply if llm_reply.success else message.answer
    await func(llm_reply.text)
    await react(llm_reply.success, message)


@router.message(F.text, config.filter_chat_allowed)
async def send_llm_response(message: types.Message):
    # if last message is a single word, ignore it
    args = message.text
    args = args.split()
    if len(args) == 1:
        return

    message_chain = extract_message_chain(message, bot.id)
    # print(message_chain)
    if not any(role == 'assistant' for role, _ in message_chain):
        if len(message_chain) > 1 and random.random() < 0.95:
            logging.info('podpizdnut mode fired')
            return

    if len(message_chain) == 1 and message.chat.id < 0:
        if not any(config.me in x for x in args):
            # nobody mentioned me, so I shut up
            return
    else:
        # we are either in private messages,
        # or there's a continuation of a thread
        pass

    messages_to_send = [
        config.prompt_message_for_user(message.chat.id),
        *message_chain,
    ]

    # print('chain of', len(message_chain))
    # print('in chat', message.chat.id)

    await message.chat.do('typing')

    llm_reply = await TextResponse.generate(
        config=config,
        chat_id=message.chat.id,
        messages=messages_to_send,
    )
    func = message.reply if llm_reply.success else message.answer
    await func(llm_reply.text)

    await react(llm_reply.success, message)


async def main():
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

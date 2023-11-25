from __future__ import annotations

import asyncio
import collections
import logging
import os
import random

import openai
from openai import AsyncOpenAI

from aiogram import F
from aiogram import Bot, Dispatcher, Router, html, types
from aiogram.filters import Command

from config import Config
from chat_completions import TextResponse


client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

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
                    payload.appendleft((role, f'представь картинку с комментарием {tmp.caption}'))
                cur = tmp
            else:
                break
        except AttributeError:
            break
    payload.append(('user', last_message_in_thread.text))
    return [
        {'role': role, 'content': text}
        for role, text in payload
    ]


@router.message(Command(commands=['blerb'], ignore_mention=True))
async def dump_message_info(message: types.Message):
    logging.info(f'incoming blerb from {message.chat.id}')
    await message.reply(f'chat id: {html.code(message.chat.id)}')


@router.message(config.filter_chat_allowed, Command(commands=['prompt']))
async def dump_set_prompt(message: types.Message, command: types.CommandObject):
    new_prompt = command.args
    if not new_prompt:
        await message.reply(config.rich_info(message.chat.id))
        return

    success = config.override_prompt_for_chat(message.chat.id, new_prompt)
    if success:
        await message.answer('okie-dokie 👌 prompt изменён но нет никаких гарантий что это надолго')
    else:
        await message.answer('nope 🙅')


@router.message(config.filter_chat_allowed, Command(commands=['pic']))
async def gimme_pic(message: types.Message, command: types.CommandObject):
    prompt = command.args
    await message.chat.do('upload_photo')
    try:
        response = await client.images.generate(
            prompt=prompt,
            n=1,
            size='512x512',
        )
    except openai.BadRequestError:
        messages_to_send = [config.prompt_message_for_user(message.chat.id)]
        messages_to_send.append(
            {
                'role': 'user',
                'content': f'объясни трагикомичной шуткой почему OpenAI не может сгенерировать картинку по запросу "{prompt}"',
            }
        )
        await message.chat.do('typing')
        llm_reply = await TextResponse.generate(
            client=client,
            config=config,
            messages=messages_to_send,
        )
        await message.answer(llm_reply.text)
    else:
        await message.chat.do('upload_photo')
        image_from_url = types.URLInputFile(response.data[0].url)
        caption = f'DALL-E prompt: {prompt}'
        await message.answer_photo(image_from_url, caption=caption)


@router.message(config.filter_chat_allowed, Command(commands=['ru', 'en']))
async def translate_ruen(message: types.Message, command: types.CommandObject):
    prompt_message = config.fetch_translation_prompt_message(command.command)
    messages_to_send = [prompt_message, {'role': 'user', 'content': command.args}]
    await message.chat.do('typing')
    llm_reply = await TextResponse.generate(
        client=client,
        config=config,
        messages=messages_to_send,
    )
    func = message.reply if llm_reply.success else message.answer
    await func(llm_reply.text)


@router.message(F.text, config.filter_chat_allowed)
async def send_llm_response(message: types.Message):
    # if last message is a single word, ignore it
    args = message.text
    args = args.split()
    if len(args) == 1:
        return

    message_chain = extract_message_chain(message, bot.id)
    # print(message_chain)
    if not any(msg['role'] == 'assistant' for msg in message_chain):
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
        client=client,
        config=config,
        messages=messages_to_send,
    )
    func = message.reply if llm_reply.success else message.answer
    await func(llm_reply.text)


async def main():
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

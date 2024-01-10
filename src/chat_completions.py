import asyncio
import json
import os
import textwrap
from dataclasses import dataclass

import anthropic
import httpx
import openai


openai_client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
anthro_client = anthropic.AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
yagpt_folder_id = os.getenv('YANDEXGPT_FOLDER_ID', default='NoYaFolder')
yagpt_api_key = os.getenv('YANDEXGPT_API_KEY', default='NoYaKey')
kandinski_api_key = os.getenv('KANDINSKI_API_KEY', default='KandiKeyOopsie')
kandinski_api_secret = os.getenv('KANDINSKI_API_SECRET', default='KandiSecretOopsie')


@dataclass(frozen=True)
class TextResponse:
    success: bool
    text: str

    @classmethod
    async def generate(cls, config, chat_id, messages):
        provider = config.provider_for_chat_id(chat_id)
        if provider == config.PROVIDER_OPENAI:
            return await cls._generate_openai(
                openai_client,
                config.model_for_chat_id(chat_id),
                messages,
            )
        elif provider == config.PROVIDER_ANTHROPIC:
            return await cls._generate_anthropic(
                anthro_client,
                config.model_for_chat_id(chat_id),
                messages,
            )
        elif provider == config.PROVIDER_YANDEXGPT:
            async with httpx.AsyncClient() as httpx_client:
                return await cls._generate_yandexgpt(
                    httpx_client,
                    config.model_for_chat_id(chat_id),
                    messages,
                )
        else:
            return cls(success=False, text=f'Unsupported provider: {config.provider}')

    @classmethod
    async def _generate_openai(cls, client, model, messages):
        payload = [{'role': role, 'content': text} for role, text in messages]
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=payload,
            )
        except openai.RateLimitError as e:
            return cls(
                success=False,
                text=f'Кажется я подустал и воткнулся в рейт-лимит. Давай сделаем перерыв ненадолго.\n\n{e}',  # noqa
            )
        except openai.BadRequestError as e:
            return cls(
                success=False,
                text=f'Beep-bop, кажется я не умею отвечать на такие вопросы:\n\n{e}',  # noqa
            )
        except TimeoutError as e:
            return cls(
                success=False,
                text=f'Кажется у меня сбоит сеть. Ты попробуй позже, а я пока схожу чаю выпью.\n\n{e}',  # noqa
            )
        else:
            return cls(
                success=True,
                text=response.choices[0].message.content,
            )

    @classmethod
    async def _generate_anthropic(cls, client, model, messages):
        user_tag = anthropic.HUMAN_PROMPT
        bot_tag = anthropic.AI_PROMPT
        system = [text for role, text in messages if role == 'system'][0]

        # claude 2.1 might need different format for prompting since it has system prompts
        # full_prompt = f'{system} {user_tag}{human}{bot_tag}'

        # claude instant 1.2 though... Needs a different thing
        prompt = textwrap.dedent(
            """
                Here are a few back and forth messages between user and a bot.
                User messages are in tag <user>, bot messages are in tag <bot>
            """.strip()
        )
        prompt = [f'{user_tag}{prompt}']
        for role, text in messages:
            if role == 'system':
                continue
            prompt.append(f'\n<{role}>{text}</{role}>')
        prompt.append(f'\n{system}')
        prompt.append(
            '\nTake content of last unpaired "user" and use this as completion prompt.'
        )
        prompt.append(f'\nRespond ONLY with text and no tags.{bot_tag}')
        prompt = ''.join(prompt)

        # print(prompt)
        try:
            response = await client.completions.create(
                model=model,
                max_tokens_to_sample=1024,  # no clue about this value
                prompt=prompt,
            )
        except openai.RateLimitError as e:
            return cls(
                success=False,
                text=f'Кажется я подустал и воткнулся в рейт-лимит. Давай сделаем перерыв ненадолго.\n\n{e}',  # noqa
            )
        except openai.BadRequestError as e:
            return cls(
                success=False,
                text=f'Beep-bop, кажется я не умею отвечать на такие вопросы:\n\n{e}',  # noqa
            )
        except TimeoutError as e:
            return cls(
                success=False,
                text=f'Кажется у меня сбоит сеть. Ты попробуй позже, а я пока схожу чаю выпью.\n\n{e}',  # noqa
            )
        else:
            # print(response.completion)
            completion = response.completion.replace("<", "[").replace(">", "]")
            return cls(
                success=True,
                text=completion,
            )

    @classmethod
    async def _generate_yandexgpt(cls, client, model, messages):
        params = {
            'messages': [{'role': role, 'text': text} for role, text in messages],
            'modelUri': f'gpt://{yagpt_folder_id}/{model}',
            'completionOptions': {
                'stream': False,
                'temperature': 0.6,
                'maxTokens': "1000",
            },
        }
        headers = {
            'Authorization': f'Api-Key {yagpt_api_key}',
            'x-folder-id': yagpt_folder_id,
        }
        response = await client.post(
            'https://llm.api.cloud.yandex.net/foundationModels/v1/completion',
            json=params,
            headers=headers,
        )
        if response.status_code == 200:
            data = response.json()
            return cls(
                success=True,
                text=data['result']['alternatives'][0]['message']['text'],
            )
        else:
            return cls(
                success=False,
                text=response.text,
            )


@dataclass(frozen=True)
class ImageResponse:
    success: bool
    b64_or_url: str
    censored: bool = False

    @classmethod
    async def generate(cls, prompt, mode='dall-e'):
        if mode == 'dall-e':
            # no other providers yet so meh
            openai_client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            return await cls._generate_dalle(openai_client, prompt)
        elif mode == 'kandinski':
            async with httpx.AsyncClient() as httpx_client:
                return await cls._generate_kandinski(
                    httpx_client,
                    prompt,
                )
        else:
            return cls(success=False, text=f'Unsupported provider: {mode}')

    @classmethod
    async def _generate_dalle(cls, client, prompt):
        img_gen_reply = await client.images.generate(
            prompt=prompt,
            n=1,
            size='512x512',
        )
        return cls(success=True, b64_or_url=img_gen_reply.data[0].url)

    @classmethod
    async def _generate_kandinski(cls, client, prompt):
        BASE_URL = 'https://api-key.fusionbrain.ai/key/api/v1'
        headers = {
            'X-Key': f'Key {kandinski_api_key}',
            'x-Secret': f'Secret {kandinski_api_secret}',
        }
        # pick model
        response = await client.get(
            f'{BASE_URL}/models',
            headers=headers,
        )
        # 2024jan09: only one model supported at the moment anyway
        model_id = response.json()[0]['id']
        params = {
            'type': 'GENERATE',
            'width': 512,
            'height': 512,
            'num_images': 1,
            'generateParams': {
                'query': prompt,
            },
        }
        data = {
            'model_id': (None, str(model_id)),
            'params': (None, json.dumps(params), 'application/json'),
        }
        response = await client.post(
            f'{BASE_URL}/text2image/run',
            headers=headers,
            files=data,
        )
        run_id = response.json()['uuid']

        attempts = 10
        delay = 10
        while attempts > 0:
            response = await client.get(
                f'{BASE_URL}/text2image/status/{run_id}', headers=headers
            )
            data = response.json()
            done = data['status'] == 'DONE'
            if done:
                break
            attempts -= 1
            await asyncio.sleep(delay)
        return cls(
            success=done,
            b64_or_url=data['images'][0],
            censored=data['censored'],
        )

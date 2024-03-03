FROM python:3.11-slim-buster

LABEL org.opencontainers.image.source https://github.com/shrimpsizemoose/matvey-3000

WORKDIR /bot

COPY src/bot_handler.py  /bot/
COPY src/config.py /bot/
COPY src/chat_completions.py /bot/
COPY src/message_store.py /bot/

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install the required packages
RUN pip install \
        aiogram==3.4.1 \
        anthropic==0.16.0 \
        hiredis==2.3.2 \
        httpx==0.27.0 \
        openai==1.12.0 \
        redis==5.0.2

CMD ["python", "/bot/bot_handler.py"]


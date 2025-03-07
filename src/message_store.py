from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass

import redis


logger = logging.getLogger(__name__)


@dataclass
class StoredChatMessage:
    chat_name: str
    from_username: str
    from_full_name: str
    timestamp: int
    text: str

    def serialize(self):
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def deserialize(cls, serialized_dict: str | dict):
        if isinstance(serialized_dict, (str, bytes)):
            serialized_dict = json.loads(serialized_dict)
        obj = cls(**serialized_dict)
        obj.timestamp = int(obj.timestamp)
        return obj

    @classmethod
    def from_tg_message(cls, message):
        from_user = message.from_user

        return cls(
            chat_name=message.chat.full_name,
            from_username=from_user.username,
            from_full_name=from_user.full_name,
            timestamp=int(message.date.timestamp()),
            text=message.text,
        )


class MessageStore:
    def __init__(self, redis_url: str):
        self.redis_conn = redis.from_url(redis_url)
        logger.info('Redis message store connected')

    @classmethod
    def from_env(cls) -> MessageStore:
        url = os.getenv('REDIS_URL')
        return cls(url)

    def save(self, tag: str, message: StoredChatMessage):
        # might need to have a deeper per-hour or per-day split
        # alternatively, just trim it to like 5000?
        self.redis_conn.lpush(tag, message.serialize())

    def fetch_stats(self, keys_pattern: str) -> list[tuple[str, int]]:
        keys = self.redis_conn.keys(keys_pattern)
        return [
            (key.decode(), self.redis_conn.llen(key))
            for key in keys
            if self.redis_conn.type(key) == b'list'  # noqa
        ]

    def fetch_messages(
        self, key: str, limit: int, raw: bool = False
    ) -> list[StoredChatMessage] | list[bytes]:
        messages = self.redis_conn.lrange(key, 0, limit)
        if raw:
            return messages

        return list(map(StoredChatMessage.deserialize, messages))

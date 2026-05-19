"""
推理内容缓存模块

缓存模型返回的 reasoning_content，在回放历史消息时自动填入，
避免空字符串导致的上下文丢失。

缓存策略：
- key: (conversation_hash, message_index, tool_call_id)
- value: reasoning_content 字符串
- 持久化: JSON 文件
- 过期: 可配置，默认 24 小时
"""

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mimo-compat")


class ReasoningCache:
    """推理内容缓存"""

    def __init__(
        self,
        cache_file: str = "reasoning_cache.json",
        max_age_seconds: int = 86400,  # 24 小时
        max_entries: int = 10000,
        persist: bool = True,
    ):
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._cache_file = Path(cache_file)
        self._max_age = max_age_seconds
        self._max_entries = max_entries
        self._persist = persist
        self._stats = {"hits": 0, "misses": 0, "stores": 0, "evictions": 0}

        if persist:
            self._load()

    def _make_key(
        self,
        messages: list[dict],
        assistant_index: int,
        tool_call_ids: list[str],
    ) -> str:
        """
        生成缓存 key。

        基于对话上下文的哈希 + assistant 消息位置 + tool_call_ids。
        相同位置、相同 tool_calls 的消息视为同一条。
        """
        # 取 assistant 消息之前的所有消息计算上下文哈希
        context_msgs = messages[:assistant_index]
        context_str = json.dumps(context_msgs, sort_keys=True, ensure_ascii=False)
        context_hash = hashlib.md5(context_str.encode()).hexdigest()[:12]

        # tool_call_ids 排序后拼接
        tc_str = "|".join(sorted(tool_call_ids))

        return f"{context_hash}:{assistant_index}:{tc_str}"

    def _is_expired(self, entry: dict) -> bool:
        """检查缓存条目是否过期"""
        return time.time() - entry.get("timestamp", 0) > self._max_age

    def _evict(self):
        """清理过期和超限条目"""
        now = time.time()

        # 移除过期条目
        expired = [
            k for k, v in self._cache.items()
            if now - v.get("timestamp", 0) > self._max_age
        ]
        for k in expired:
            del self._cache[k]
            self._stats["evictions"] += 1

        # 如果仍然超限，移除最旧的
        if len(self._cache) > self._max_entries:
            sorted_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k].get("timestamp", 0),
            )
            to_remove = sorted_keys[: len(self._cache) - self._max_entries]
            for k in to_remove:
                del self._cache[k]
                self._stats["evictions"] += 1

    def get(
        self,
        messages: list[dict],
        assistant_index: int,
        tool_call_ids: list[str],
    ) -> Optional[str]:
        """
        获取缓存的 reasoning_content。

        Args:
            messages: 完整消息列表
            assistant_index: assistant 消息在列表中的索引
            tool_call_ids: 该 assistant 消息的 tool_call id 列表

        Returns:
            缓存的 reasoning_content，未命中返回 None
        """
        key = self._make_key(messages, assistant_index, tool_call_ids)

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None

            if self._is_expired(entry):
                del self._cache[key]
                self._stats["misses"] += 1
                return None

            self._stats["hits"] += 1
            return entry["reasoning_content"]

    def store(
        self,
        messages: list[dict],
        assistant_index: int,
        tool_call_ids: list[str],
        reasoning_content: str,
    ):
        """
        存储 reasoning_content。

        Args:
            messages: 完整消息列表
            assistant_index: assistant 消息在列表中的索引
            tool_call_ids: 该 assistant 消息的 tool_call id 列表
            reasoning_content: 要缓存的推理内容
        """
        if not reasoning_content:
            return

        key = self._make_key(messages, assistant_index, tool_call_ids)

        with self._lock:
            self._cache[key] = {
                "reasoning_content": reasoning_content,
                "timestamp": time.time(),
                "tool_call_ids": tool_call_ids,
            }
            self._stats["stores"] += 1

            # 定期清理
            if len(self._cache) > self._max_entries * 1.1:
                self._evict()

            # 持久化
            if self._persist:
                self._save()

    def _load(self):
        """从文件加载缓存"""
        if not self._cache_file.exists():
            return

        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache = data.get("entries", {})
            logger.info(f"Loaded {len(self._cache)} cached reasoning entries")
        except Exception as e:
            logger.warning(f"Failed to load reasoning cache: {e}")

    def _save(self):
        """保存缓存到文件"""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"entries": self._cache, "stats": self._stats},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.warning(f"Failed to save reasoning cache: {e}")

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            return {
                **self._stats,
                "entries": len(self._cache),
                "hit_rate": (
                    f"{self._stats['hits'] / total * 100:.1f}%"
                    if total > 0
                    else "N/A"
                ),
            }

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._stats = {"hits": 0, "misses": 0, "stores": 0, "evictions": 0}
            if self._persist:
                self._save()

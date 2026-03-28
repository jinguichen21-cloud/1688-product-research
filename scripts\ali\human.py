"""人类行为模拟参数（延迟）。"""

import random
import time


def sleep_random(min_ms: int, max_ms: int) -> None:
    """随机延迟。"""
    if max_ms <= min_ms:
        time.sleep(min_ms / 1000.0)
        return
    delay = random.randint(min_ms, max_ms) / 1000.0
    time.sleep(delay)


def navigation_delay() -> None:
    """页面导航后的随机等待，模拟人类阅读。"""
    sleep_random(1000, 2500)

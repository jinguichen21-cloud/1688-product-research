"""Cookie 文件持久化。"""

from __future__ import annotations

import os
from pathlib import Path


def get_cookies_file_path() -> str:
    """获取 cookies 文件路径。

    路径：~/.ali1688/cookies.json
    """
    cookies_dir = Path.home() / ".ali1688"
    cookies_dir.mkdir(parents=True, exist_ok=True)
    return str(cookies_dir / "cookies.json")


def load_cookies(path: str) -> bytes | None:
    """从文件加载 cookies。"""
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def save_cookies(path: str, data: bytes) -> None:
    """保存 cookies 到文件。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def delete_cookies(path: str) -> None:
    """删除 cookies 文件。"""
    import contextlib

    with contextlib.suppress(FileNotFoundError):
        os.remove(path)

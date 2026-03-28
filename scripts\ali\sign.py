"""MTOP API MD5 签名（纯 Python）。"""

import hashlib
import time

APP_KEY = "12574478"
JS_VERSION = "2.7.0"


def get_milliseconds_timestamp() -> int:
    """返回当前毫秒时间戳。"""
    return int(time.time() * 1000)


def compute_sign(m_h5_tk: str, data: str) -> dict[str, str]:
    """生成 MTOP API 签名参数。

    签名公式: MD5(m_h5_tk前半段 & 时间戳 & APP_KEY & data)

    Args:
        m_h5_tk: Cookie 中的 _m_h5_tk 值
        data: 请求参数中的 data 字段（JSON 字符串）

    Returns:
        {"sign": "32位hex签名", "t": "毫秒时间戳字符串"}
    """
    timestamp = get_milliseconds_timestamp()
    tk_prefix = m_h5_tk.split("_")[0] if m_h5_tk and m_h5_tk != "undefined" else ""
    pre_sign_str = f"{tk_prefix}&{timestamp}&{APP_KEY}&{data}"
    sign = hashlib.md5(pre_sign_str.encode("utf-8")).hexdigest()
    return {"sign": sign, "t": str(timestamp)}

"""1688 登录管理（CDP 扫码登录）。"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time

from .cdp import Page
from .human import sleep_random
from .urls import HOME_URL

logger = logging.getLogger(__name__)

_QR_DIR = os.path.join(tempfile.gettempdir(), "ali1688")
_QR_FILE = os.path.join(_QR_DIR, "login_qrcode.png")


def check_login_status(page: Page) -> bool:
    """检查 1688 登录状态。

    导航到 1688 首页，检测已登录用户元素。

    Returns:
        True 已登录，False 未登录。
    """
    current_url = page.evaluate("location.href") or ""
    if "1688.com" not in current_url:
        page.navigate(HOME_URL)
        page.wait_for_load()
        sleep_random(1000, 2000)

    # 检查多种登录状态指示器
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        # 检查是否有用户信息区域（已登录标志）
        logged_in = page.evaluate("""
            (() => {
                // 检查常见的已登录标志
                const myInfo = document.querySelector('.sm-widget-myali');
                if (myInfo) return true;
                const userName = document.querySelector('.user-name');
                if (userName && userName.textContent.trim()) return true;
                const myAli = document.querySelector('.J_MyInfo');
                if (myAli) return true;
                // 检查登录链接是否消失
                const loginLink = document.querySelector('a[href*="login.1688.com"]');
                const hasLoginPrompt = document.querySelector('.login-info-wrapper');
                if (!loginLink && !hasLoginPrompt) return null;  // 不确定
                return false;
            })()
        """)
        if logged_in is True:
            return True
        if logged_in is False:
            return False
        time.sleep(0.5)

    return False


def fetch_qrcode(page: Page) -> tuple[bytes, str, bool]:
    """获取 1688 登录二维码图片。

    Returns:
        (png_bytes, b64_str, already_logged_in)
    """
    # 导航到 1688 登录页
    login_url = "https://login.1688.com/member/signin.htm"
    page.navigate(login_url)
    page.wait_for_load()
    sleep_random(1500, 2500)

    # 快速检查是否已登录
    current_url = page.evaluate("location.href") or ""
    if "login" not in current_url:
        return b"", "", True

    # 等待二维码出现
    deadline = time.monotonic() + 15.0
    qr_data = None
    while time.monotonic() < deadline:
        # 尝试多种方式获取二维码
        qr_data = page.evaluate("""
            (() => {
                // 方式1: img 元素的 src
                const imgs = document.querySelectorAll('img');
                for (const img of imgs) {
                    const src = img.src || '';
                    if (src.includes('qrcode') || src.includes('base64')) {
                        if (src.startsWith('data:image')) {
                            const b64 = src.split('base64,')[1];
                            if (b64) return {type: 'base64', data: b64};
                        }
                    }
                }
                // 方式2: canvas 元素
                const canvases = document.querySelectorAll('canvas');
                for (const canvas of canvases) {
                    try {
                        const dataUrl = canvas.toDataURL('image/png');
                        const b64 = dataUrl.split('base64,')[1];
                        if (b64 && b64.length > 100) return {type: 'base64', data: b64};
                    } catch(e) {}
                }
                // 方式3: 通过 id 或 class 查找二维码容器
                const qrContainer = document.querySelector(
                    '#J_QRCodeImg, .qrcode-img, .login-qrcode'
                );
                if (qrContainer) {
                    const img = qrContainer.querySelector('img');
                    if (img && img.src && img.src.startsWith('data:image')) {
                        const b64 = img.src.split('base64,')[1];
                        if (b64) return {type: 'base64', data: b64};
                    }
                }
                return null;
            })()
        """)
        if qr_data:
            break
        time.sleep(1.0)

    if not qr_data:
        # 回退：直接截图二维码区域
        logger.warning("未能通过 JS 提取二维码，尝试截图方式")
        png_bytes = page.screenshot_element("#J_QRCodeImg, .qrcode-img, .login-qrcode", padding=5)
        if png_bytes:
            import base64
            b64_str = base64.b64encode(png_bytes).decode()
            return png_bytes, b64_str, False
        raise RuntimeError("无法获取登录二维码")

    import base64
    b64_str = qr_data["data"]
    png_bytes = base64.b64decode(b64_str)
    return png_bytes, b64_str, False


def wait_for_login(page: Page, timeout: float = 120.0) -> bool:
    """等待扫码登录完成。

    Args:
        page: CDP 页面对象。
        timeout: 超时时间（秒）。

    Returns:
        True 登录成功，False 超时。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # 检查 URL 是否跳转离开登录页
        current_url = page.evaluate("location.href") or ""
        if "login" not in current_url and "1688.com" in current_url:
            logger.info("登录成功")
            return True
        # 检查页面上是否出现已登录标志
        logged_in = page.evaluate("""
            (() => {
                const myInfo = document.querySelector('.sm-widget-myali, .user-name, .J_MyInfo');
                return myInfo !== null;
            })()
        """)
        if logged_in:
            logger.info("登录成功")
            return True
        time.sleep(1.0)
    return False


def save_qrcode_to_file(png_bytes: bytes) -> str:
    """保存二维码到临时文件。"""
    os.makedirs(_QR_DIR, exist_ok=True)
    with open(_QR_FILE, "wb") as f:
        f.write(png_bytes)
    logger.info("二维码已保存: %s", _QR_FILE)
    return _QR_FILE


def make_qrcode_url(png_bytes: bytes) -> tuple[str, str | None]:
    """通过 goqr.me 解码生成展示 URL。

    Returns:
        (image_url, login_url)
    """
    import base64
    import urllib.parse

    qr_content = _decode_qr_content(png_bytes)
    if qr_content:
        image_url = (
            "https://api.qrserver.com/v1/create-qr-code/"
            "?size=300x300&data="
            + urllib.parse.quote(qr_content, safe="")
        )
        return image_url, qr_content

    b64 = base64.b64encode(png_bytes).decode()
    return "data:image/png;base64," + b64, None


def _decode_qr_content(png_bytes: bytes) -> str | None:
    """通过 goqr.me read API 解码二维码内容。"""
    import http.client

    boundary = "----Ali1688QrBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file";'
        f' filename="qr.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + png_bytes + f"\r\n--{boundary}--\r\n".encode()

    try:
        conn = http.client.HTTPSConnection("api.qrserver.com", timeout=5)
        conn.request(
            "POST",
            "/v1/read-qr-code/",
            body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        resp = conn.getresponse()
        if resp.status != 200:
            return None
        result = json.loads(resp.read().decode())
        data = result[0]["symbol"][0].get("data")
        return data if data else None
    except Exception:
        logger.debug("goqr.me 解码失败")
        return None

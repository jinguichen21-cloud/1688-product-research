"""SessionManager — CDP 浏览器会话与 MTOP API 的桥梁。

核心职责：
1. 通过 CDP 控制浏览器访问 1688 搜索页
2. 注入 JS 拦截器捕获 MTOP API 请求
3. 提取 Cookie、_m_h5_tk、pageId、请求头等构建 RequestTemplate
4. 支持会话刷新（Token 过期时重新导航提取）
"""

from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs, urlparse

from .cdp import Page
from .errors import SessionError
from .human import navigation_delay, sleep_random
from .types import RequestTemplate
from .urls import make_search_url

logger = logging.getLogger(__name__)

# JS 拦截器：在页面加载前注入，捕获所有 MTOP XHR 请求
_XHR_INTERCEPTOR_JS = """
(() => {
    window.__captured_mtop = [];
    const _origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {
        if (typeof url === 'string' && url.includes('h5api.m.1688.com')) {
            window.__captured_mtop.push({
                method: method,
                url: url,
                timestamp: Date.now()
            });
        }
        return _origOpen.apply(this, arguments);
    };
})();
"""

# JS 提取器：导航完成后执行，收集 Cookie、捕获的请求和 pageId
_EXTRACT_SESSION_JS = """
(() => {
    const cookies = document.cookie;
    const m_h5_tk_match = cookies.match(/_m_h5_tk=([^;]+)/);
    const m_h5_tk = m_h5_tk_match ? m_h5_tk_match[1] : '';

    // 从 performance entries 提取 pageId
    let pageId = '';
    try {
        const entries = performance.getEntriesByType('resource');
        for (const e of entries) {
            if (e.name.includes('recommend') && e.name.includes('h5api')) {
                try {
                    const url = new URL(e.name);
                    const ds = url.searchParams.get('data');
                    if (ds) {
                        const d = JSON.parse(ds);
                        const p = typeof d.params === 'string' ? JSON.parse(d.params) : d.params;
                        if (p && p.pageId) { pageId = p.pageId; break; }
                    }
                } catch(ex) {}
            }
        }
    } catch(ex) {}

    return JSON.stringify({
        requests: window.__captured_mtop || [],
        cookies: cookies,
        m_h5_tk: m_h5_tk,
        pageId: pageId
    });
})()
"""


def _parse_cookies_string(cookies_str: str) -> dict[str, str]:
    """将 document.cookie 字符串解析为字典。"""
    cookies: dict[str, str] = {}
    for part in cookies_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies


def _extract_params_from_url(url: str) -> dict[str, str]:
    """从 MTOP API URL 中提取查询参数。"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    return {k: v[0] for k, v in qs.items()}


class SessionManager:
    """管理浏览器会话和 API 会话的生命周期。"""

    def __init__(self, page: Page) -> None:
        self._page = page
        self._template: RequestTemplate | None = None
        self._page_id: str = ""

    @property
    def page_id(self) -> str:
        """当前搜索页的 pageId（MTOP API 必需参数）。"""
        return self._page_id

    def extract_session(
        self,
        keyword: str = "手机壳",
        sort_type: str = "default",
        price_start: float | None = None,
        price_end: float | None = None,
    ) -> RequestTemplate:
        """从浏览器提取会话信息（含 pageId）。

        Args:
            keyword: 搜索关键词
            sort_type: 排序类型，可选: default, sale, price_asc, price_desc
            price_start: 价格区间起始
            price_end: 价格区间结束
        """
        logger.info("开始提取会话...")

        # 1. 注入 XHR 拦截器
        self._page._send_session(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": _XHR_INTERCEPTOR_JS},
        )

        # 2. 导航到搜索页（GBK 编码 URL，带排序和价格参数）
        search_url = make_search_url(
            keyword=keyword,
            sort_type=sort_type,
            price_start=price_start,
            price_end=price_end,
        )
        logger.info("导航到搜索页: %s", search_url)
        self._page.navigate(search_url)
        self._page.wait_for_load(timeout=30.0)
        navigation_delay()
        self._page.wait_dom_stable(timeout=10.0)

        # 等待 MTOP 请求完成（含 pageId 分配）
        sleep_random(3000, 5000)

        # 3. 提取会话数据
        raw = self._page.evaluate(_EXTRACT_SESSION_JS)
        if not raw:
            raise SessionError("无法提取会话数据")

        try:
            session_data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SessionError(f"解析会话数据失败: {e}") from e

        cookies_str = session_data.get("cookies", "")
        m_h5_tk = session_data.get("m_h5_tk", "")
        page_id = session_data.get("pageId", "")
        captured_requests = session_data.get("requests", [])

        if not m_h5_tk:
            raise SessionError("未获取到 _m_h5_tk cookie，可能需要手动访问一次 1688")

        self._page_id = page_id
        cookies = _parse_cookies_string(cookies_str)
        logger.info(
            "会话提取成功: m_h5_tk=%s..., pageId=%s, cookies数=%d, 捕获请求数=%d",
            m_h5_tk[:20], page_id[:20] if page_id else "(无)", len(cookies), len(captured_requests),
        )

        # 4. 从捕获的请求中提取 appKey 和 jsv
        app_key = "12574478"
        jsv = "2.7.4"
        headers: dict[str, str] = {}

        for req in captured_requests:
            url = req.get("url", "")
            if "h5api.m.1688.com" in url:
                params = _extract_params_from_url(url)
                if "appKey" in params:
                    app_key = params["appKey"]
                if "jsv" in params:
                    jsv = params["jsv"]
                break

        # 构建请求头
        ua = self._page.evaluate("navigator.userAgent") or ""
        if ua:
            headers["User-Agent"] = ua
        headers["Referer"] = "https://s.1688.com/"
        headers["Accept"] = "*/*"

        self._template = RequestTemplate(
            cookies=cookies,
            m_h5_tk=m_h5_tk,
            headers=headers,
            app_key=app_key,
            jsv=jsv,
        )
        return self._template

    def refresh_session(
        self,
        keyword: str = "手机壳",
        sort_type: str = "default",
        price_start: float | None = None,
        price_end: float | None = None,
    ) -> RequestTemplate:
        """会话过期时刷新。"""
        logger.info("刷新会话...")
        self._template = None
        self._page_id = ""
        return self.extract_session(keyword, sort_type, price_start, price_end)

    @property
    def template(self) -> RequestTemplate:
        """获取当前会话模板（未初始化时自动提取）。"""
        if not self._template:
            self._template = self.extract_session()
        return self._template

    def ensure_session(
        self,
        keyword: str,
        sort_type: str = "default",
        price_start: float | None = None,
        price_end: float | None = None,
    ) -> RequestTemplate:
        """确保会话已初始化（带完整搜索参数）。

        如果会话已存在且参数匹配，直接返回；否则重新提取。
        """
        if self._template and self._page_id:
            logger.info("使用已有会话")
            return self._template

        return self.extract_session(keyword, sort_type, price_start, price_end)

"""商品搜索 — MTOP API 回放。

核心模块：通过从浏览器捕获的会话模板 + pageId，构建 getOfferList 请求。
关键词使用 GBK URL 编码。
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from .errors import TokenExpiredError
from .human import sleep_random
from .session import SessionManager
from .sign import compute_sign
from .types import Product, RequestTemplate, parse_product_list
from .urls import encode_gbk, make_mtop_url

logger = logging.getLogger(__name__)

# MTOP 搜索 API 常量
SEARCH_API = "mtop.relationrecommend.WirelessRecommend.recommend"
SEARCH_VERSION = "2.0"
SEARCH_APP_ID = 32517

# 排序映射（sortType 值 → MTOP API 参数）
# 参考: scripts/ali/example.md
SORT_MAP = {
    "default": "normal",
    "sale": "va_sales360",
    "price_asc": "price",  # 配合 descendOrder=false
    "price_desc": "price",  # 配合 descendOrder=true
}


def _build_inner_params(
    keyword: str,
    page_id: str,
    sort_type: str = "default",
    price_start: float | None = None,
    price_end: float | None = None,
    page: int = 1,
    page_size: int = 60,
) -> dict:
    """构建 MTOP 搜索内部参数（与真实浏览器请求一致）。"""
    keyword_gbk = encode_gbk(keyword)

    params: dict = {
        "beginPage": page,
        "pageSize": page_size,
        "method": "getOfferList",
        "pageId": page_id,
        "verticalProductFlag": "pcmarket",
        "searchScene": "pcOfferSearch",
        "charset": "GBK",
        "keywords": keyword_gbk,
    }

    sort_value = SORT_MAP.get(sort_type, "normal")
    if sort_value:
        params["sortType"] = sort_value

    # 价格排序需要设置 descendOrder 参数
    if sort_type == "price_asc":
        params["descendOrder"] = "false"
    elif sort_type == "price_desc":
        params["descendOrder"] = "true"
    else:
        # 其他排序默认降序
        params["descendOrder"] = "true"

    if price_start is not None:
        params["priceStart"] = str(int(price_start))
    if price_end is not None:
        params["priceEnd"] = str(int(price_end))

    return params


def _build_data_payload(inner_params: dict) -> str:
    """构建 MTOP data payload。"""
    payload = {
        "appId": SEARCH_APP_ID,
        "params": json.dumps(inner_params, separators=(",", ":")),
    }
    return json.dumps(payload, separators=(",", ":"))


def _parse_jsonp(text: str) -> dict:
    """JSONP 响应 → JSON dict。"""
    text = text.strip()

    if text.startswith("{"):
        return json.loads(text)

    match = re.match(r"^\w+\((.*)\)\s*;?\s*$", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError(f"无法解析响应: {text[:200]}")


def _send_mtop_request(
    template: RequestTemplate,
    data: str,
    callback: str = "mtopjsonpreqTppId_32517_getOfferList2",
) -> dict:
    """发送 MTOP API 请求并解析响应。"""
    sign_result = compute_sign(template.m_h5_tk, data)

    url = make_mtop_url(SEARCH_API, SEARCH_VERSION)

    params = {
        "jsv": template.jsv,
        "appKey": template.app_key,
        "t": sign_result["t"],
        "sign": sign_result["sign"],
        "api": SEARCH_API,
        "v": SEARCH_VERSION,
        "jsonpIncPrefix": "reqTppId_32517_getOfferList",
        "type": "jsonp",
        "dataType": "jsonp",
        "callback": callback,
        "data": data,
    }

    cookie_str = "; ".join(f"{k}={v}" for k, v in template.cookies.items())

    headers = {**template.headers}
    headers["Cookie"] = cookie_str

    logger.debug("发送 MTOP 请求: sign=%s", sign_result["sign"][:8])

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=headers)
        resp.raise_for_status()

    result = _parse_jsonp(resp.text)

    # 检查 Token 过期
    ret = result.get("ret", [])
    expired_tokens = ("TOKEN_EXPIRED", "SESSION_EXPIRED", "FAIL_SYS_TOKEN_EXOIRED")
    if isinstance(ret, list):
        for r in ret:
            if any(t in str(r) for t in expired_tokens):
                raise TokenExpiredError()

    return result


def search_products(
    session: SessionManager,
    keyword: str,
    sort_type: str = "default",
    price_start: float | None = None,
    price_end: float | None = None,
    limit: int = 40,
    begin_page: int = 1,
) -> list[Product]:
    """通过 MTOP API 回放搜索商品。

    Args:
        session: 会话管理器
        keyword: 搜索关键词
        sort_type: 排序类型，可选值:
            - "default": 综合排序 (sortType=normal)
            - "sale": 销量排序 (sortType=va_sales360)
            - "price_asc": 价格升序 (sortType=price, descendOrder=false)
            - "price_desc": 价格降序 (sortType=price, descendOrder=true)
        price_start: 价格区间起始
        price_end: 价格区间结束
        limit: 返回商品数量上限
        begin_page: 起始页码
    """
    template = session.template
    page_id = session.page_id
    if not page_id:
        raise ValueError("pageId 未提取，请先调用 session.extract_session()")

    all_products: list[Product] = []
    current_page = begin_page
    page_size = min(limit, 60)

    while len(all_products) < limit:
        inner_params = _build_inner_params(
            keyword=keyword,
            page_id=page_id,
            sort_type=sort_type,
            price_start=price_start,
            price_end=price_end,
            page=current_page,
            page_size=page_size,
        )
        data = _build_data_payload(inner_params)

        try:
            result = _send_mtop_request(template, data)
        except TokenExpiredError:
            logger.warning("Token 过期，刷新会话后重试...")
            template = session.refresh_session(
                keyword=keyword,
                sort_type=sort_type,
                price_start=price_start,
                price_end=price_end,
            )
            page_id = session.page_id
            inner_params = _build_inner_params(
                keyword=keyword,
                page_id=page_id,
                sort_type=sort_type,
                price_start=price_start,
                price_end=price_end,
                page=current_page,
                page_size=page_size,
            )
            data = _build_data_payload(inner_params)
            result = _send_mtop_request(template, data)

        # 提取商品数据：路径 data.data.OFFER.items
        api_data = result.get("data", {})
        inner_data = api_data.get("data", api_data)
        products = parse_product_list(inner_data)

        if not products:
            logger.info("第 %d 页无更多商品", current_page)
            break

        all_products.extend(products)
        logger.info(
            "第 %d 页获取 %d 条商品，累计 %d 条",
            current_page, len(products), len(all_products),
        )

        if len(products) < page_size:
            break

        current_page += 1

        if len(all_products) < limit:
            sleep_random(1000, 2000)

    return all_products[:limit]

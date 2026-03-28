"""1688 URL 常量和构建函数。

注意：1688 搜索使用 GBK 编码，关键词必须经过 GBK URL 编码。
"""

from urllib.parse import quote

# 基础页面
HOME_URL = "https://www.1688.com"
SEARCH_URL = "https://s.1688.com/selloffer/offer_search.htm"

# MTOP API
MTOP_API_BASE = "https://h5api.m.1688.com/h5"


def encode_gbk(text: str) -> str:
    """将中文文本编码为 GBK URL 编码（如 %B1%A3%CE%C2%B1%AD）。"""
    return quote(text.encode("gbk"), safe="")


# 排序类型映射（内部标识 → URL 参数值）
# 参考: https://s.1688.com/selloffer/offer_search.htm 实际 URL 参数
URL_SORT_MAP = {
    "default": ("normal", "true"),      # 综合排序，默认降序
    "sale": ("va_sales360", "true"),    # 销量排序
    "price_asc": ("price", "false"),    # 价格升序
    "price_desc": ("price", "true"),    # 价格降序
}


def make_search_url(
    keyword: str,
    sort_type: str = "default",
    page: int = 1,
    price_start: float | None = None,
    price_end: float | None = None,
) -> str:
    """构建 1688 搜索结果页 URL（关键词 GBK 编码）。

    Args:
        keyword: 搜索关键词
        sort_type: 排序类型，可选: default, sale, price_asc, price_desc
        page: 页码
        price_start: 价格区间起始
        price_end: 价格区间结束

    Returns:
        完整的搜索 URL，如:
        https://s.1688.com/selloffer/offer_search.htm?keywords=...&beginPage=1&sortType=price&descendOrder=false&priceStart=100&priceEnd=200
    """
    kw_encoded = encode_gbk(keyword)
    url = f"{SEARCH_URL}?keywords={kw_encoded}&beginPage={page}"

    # 添加排序参数
    sort_value, descend_order = URL_SORT_MAP.get(sort_type, ("normal", "true"))
    url += f"&sortType={sort_value}&descendOrder={descend_order}"

    # 添加价格区间参数
    if price_start is not None:
        url += f"&priceStart={int(price_start)}"
    if price_end is not None:
        url += f"&priceEnd={int(price_end)}"

    return url


def make_mtop_url(api: str, version: str) -> str:
    """构建 MTOP API URL。"""
    return f"{MTOP_API_BASE}/{api}/{version}/"

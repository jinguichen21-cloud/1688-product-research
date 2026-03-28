"""1688 数据类型定义。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _clean(text: str) -> str:
    """去除 HTML 标签和控制字符。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.compile(r"[\000-\010]|[\013-\014]|[\016-\037]").sub("", text)
    return text.strip()


@dataclass
class Product:
    """1688 商品数据（基于真实 MTOP API 响应结构）。"""

    # 核心标识
    offer_id: str = ""
    title: str = ""
    product_url: str = ""

    # 图片
    image_url: str = ""          # 主图
    image_list: list[str] = field(default_factory=list)  # 所有图片

    # 价格
    price: str = ""
    price_unit: str = ""

    # 销量
    booked_count: str = ""       # 近期成交数
    total_sold: str = ""         # 总销售文案（如 "已售8300+件"）

    # 店铺信息
    shop_name: str = ""
    shop_url: str = ""
    login_id: str = ""
    member_id: str = ""
    cust_id: str = ""
    biz_type: str = ""           # 生产加工 / 经销批发 等
    tp_year: str = ""            # 经营年限

    # 地理位置
    province: str = ""
    city: str = ""
    location: str = ""           # "省 市" 拼接

    # 回购与质量
    repurchase_rate: str = ""    # 复购率
    return_rate: str = ""        # 回头率

    # 店铺评分
    composite_score: str = ""    # 综合评分
    goods_score: str = ""        # 商品评分
    consultation_score: str = ""  # 咨询评分
    logistics_score: str = ""    # 物流评分
    dispute_score: str = ""      # 纠纷评分

    # 标签与服务
    service_tags: list[str] = field(default_factory=list)   # 如 ["深度验厂", "退货包运费"]
    promotion_tags: list[str] = field(default_factory=list)  # 促销标签
    properties: list[str] = field(default_factory=list)      # 商品属性 如 ["内胆材质:304不锈钢"]

    # 工厂/认证标识
    factory_inspection: bool = False    # 验厂
    super_factory: bool = False         # 超级工厂
    is_tp: bool = False                 # 诚信通

    @classmethod
    def from_dict(cls, raw_item: dict) -> Product:
        """从 API 响应单条商品数据构建 Product。

        数据路径: data.data.OFFER.items[*].data
        """
        d = raw_item.get("data", raw_item) if isinstance(raw_item, dict) else raw_item

        # 核心
        offer_id = str(d.get("offerId", ""))
        title = _clean(d.get("title", ""))
        link_url = d.get("linkUrl", "")
        product_url = link_url if link_url else (
            f"https://detail.1688.com/offer/{offer_id}.html" if offer_id else ""
        )

        # 图片
        pic_str = d.get("offerPicUrl", "")
        image_list = [u.strip() for u in pic_str.split(",") if u.strip()] if pic_str else []
        for i, url in enumerate(image_list):
            if not url.startswith("http"):
                image_list[i] = "https:" + url
        od_pic = d.get("odPicUrl", "")
        if od_pic and not od_pic.startswith("http"):
            od_pic = "https:" + od_pic
        image_url = od_pic or (image_list[0] if image_list else "")

        # 价格
        price_info = d.get("priceInfo", {}) or {}
        price = str(price_info.get("price", ""))

        # 销量
        booked_count = str(d.get("bookedCount", ""))
        after_price = d.get("afterPrice", {}) or {}
        total_sold = after_price.get("text", "")

        # 店铺
        shop = d.get("shop", {}) or {}
        shop_name = _clean(shop.get("text", ""))
        login_id = _clean(d.get("loginId", ""))
        member_id = str(d.get("memberId", ""))
        cust_id = str(d.get("custId", ""))
        biz_type = str(d.get("bizType", ""))
        tp_year = str(shop.get("tpYear", ""))

        shop_addition = d.get("shopAddition", {}) or {}
        shop_url = shop_addition.get("shopLinkUrl", "")
        if not shop_url and member_id:
            shop_url = f"https://{member_id}.1688.com"

        # 地理
        province = d.get("province", "")
        city = d.get("city", "")
        location = f"{province} {city}".strip() if province or city else ""

        # 复购 / 回头率
        repurchase_rate = str(d.get("offerRepurchaseRate", ""))
        turn_head = d.get("turnHead", {}) or {}
        return_rate = turn_head.get("percent", "")

        # 店铺评分
        trade_svc = shop_addition.get("tradeService", {}) or {}
        composite_score = trade_svc.get("compositeNewScore", "")
        goods_score = trade_svc.get("goodsScore", "")
        consultation_score = trade_svc.get("consultationScore", "")
        logistics_score = trade_svc.get("logisticsScore", "")
        dispute_score = trade_svc.get("disputeScore", "")

        # 标签
        service_tags: list[str] = []
        promotion_tags: list[str] = []
        for tag in d.get("tags", []):
            if isinstance(tag, dict):
                tag_text = tag.get("text", "")
                if tag_text:
                    mat = tag.get("matKey", "")
                    if mat == "return_rate":
                        continue  # 已在 return_rate 中提取
                    service_tags.append(tag_text)
        offer_tags = d.get("offerTags", {}) or {}
        for st in offer_tags.get("serviceTags", []):
            if st and st not in service_tags:
                service_tags.append(st)
        for pt in offer_tags.get("promotionTags", []):
            if pt:
                promotion_tags.append(pt)

        # 商品属性 (list.guide 中的 cpv 项)
        properties: list[str] = []
        list_data = d.get("list", {}) or {}
        for guide in list_data.get("guide", []):
            if isinstance(guide, dict) and guide.get("matKey") == "cpv":
                prop_title = guide.get("title", "")
                prop_text = guide.get("text", "")
                if prop_title and prop_text:
                    properties.append(f"{prop_title}:{prop_text}")
                elif prop_text:
                    properties.append(prop_text)

        # 认证
        factory_inspection = d.get("factoryInspection", "") == "true"
        super_factory = d.get("superFactory", "") == "true"
        is_tp = d.get("isTp", "") == "true"

        return cls(
            offer_id=offer_id,
            title=title,
            product_url=product_url,
            image_url=image_url,
            image_list=image_list,
            price=price,
            price_unit="",
            booked_count=booked_count,
            total_sold=total_sold,
            shop_name=shop_name,
            shop_url=shop_url,
            login_id=login_id,
            member_id=member_id,
            cust_id=cust_id,
            biz_type=biz_type,
            tp_year=tp_year,
            province=province,
            city=city,
            location=location,
            repurchase_rate=repurchase_rate,
            return_rate=return_rate,
            composite_score=composite_score,
            goods_score=goods_score,
            consultation_score=consultation_score,
            logistics_score=logistics_score,
            dispute_score=dispute_score,
            service_tags=service_tags,
            promotion_tags=promotion_tags,
            properties=properties,
            factory_inspection=factory_inspection,
            super_factory=super_factory,
            is_tp=is_tp,
        )

    def to_dict(self) -> dict:
        """转为字典（JSON 序列化用）。"""
        return {
            "offer_id": self.offer_id,
            "title": self.title,
            "product_url": self.product_url,
            "image_url": self.image_url,
            "image_list": self.image_list,
            "price": self.price,
            "price_unit": self.price_unit,
            "booked_count": self.booked_count,
            "total_sold": self.total_sold,
            "shop_name": self.shop_name,
            "shop_url": self.shop_url,
            "login_id": self.login_id,
            "member_id": self.member_id,
            "cust_id": self.cust_id,
            "biz_type": self.biz_type,
            "tp_year": self.tp_year,
            "province": self.province,
            "city": self.city,
            "location": self.location,
            "repurchase_rate": self.repurchase_rate,
            "return_rate": self.return_rate,
            "composite_score": self.composite_score,
            "goods_score": self.goods_score,
            "consultation_score": self.consultation_score,
            "logistics_score": self.logistics_score,
            "dispute_score": self.dispute_score,
            "service_tags": self.service_tags,
            "promotion_tags": self.promotion_tags,
            "properties": self.properties,
            "factory_inspection": self.factory_inspection,
            "super_factory": self.super_factory,
            "is_tp": self.is_tp,
        }


@dataclass
class RequestTemplate:
    """从浏览器捕获的 MTOP 请求模板。"""

    cookies: dict[str, str] = field(default_factory=dict)
    m_h5_tk: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    app_key: str = "12574478"
    jsv: str = "2.7.4"

    @property
    def m_h5_tk_prefix(self) -> str:
        """提取 _m_h5_tk 的前半部分（用于签名）。"""
        if self.m_h5_tk and "_" in self.m_h5_tk:
            return self.m_h5_tk.split("_")[0]
        return self.m_h5_tk


def parse_product_list(raw_data: dict) -> list[Product]:
    """从 API 响应中定位商品列表并批量解析。

    真实路径: data.data.OFFER.items (每条 item 含 data 子键)
    """
    if not raw_data:
        return []

    import contextlib

    offer_list = None

    # 路径1: OFFER.items (最常见)
    if isinstance(raw_data, dict):
        offer_section = raw_data.get("OFFER", {})
        if isinstance(offer_section, dict):
            offer_list = offer_section.get("items")

    # 路径2: data.OFFER.items
    if not offer_list and isinstance(raw_data, dict):
        inner_data = raw_data.get("data")
        if isinstance(inner_data, dict):
            offer_section = inner_data.get("OFFER", {})
            if isinstance(offer_section, dict):
                offer_list = offer_section.get("items")

    if not offer_list:
        return []

    products = []
    for item in offer_list:
        with contextlib.suppress(Exception):
            p = Product.from_dict(item)
            if p.offer_id:  # 跳过无 offerId 的项
                products.append(p)
    return products

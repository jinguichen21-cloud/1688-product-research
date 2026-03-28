"""调试脚本：对比 Chrome 页面搜索结果与 API 搜索结果。

同时打开 Chrome 搜索页面和通过脚本搜索相同条件，
将两边的原始结果都保存到 JSON，方便对比顺序和内容。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime

# 将 scripts 目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ali.cdp import Browser, Page
from ali.search import search_products
from ali.session import SessionManager

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    """配置日志。"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _connect(port: int = 9222) -> tuple[Browser, Page]:
    """连接到 Chrome 并获取页面。"""
    browser = Browser(port=port)
    browser.connect()
    page = browser.get_or_create_page()
    return browser, page


def _save_raw_data(data: dict, filename: str, output_dir: str) -> str:
    """保存原始数据到 JSON 文件。"""
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def _extract_chrome_page_products(page: Page) -> list[dict]:
    """从 Chrome 页面中提取商品列表（用于对比）。
    
    通过执行 JS 获取页面上渲染的商品数据。
    """
    import time
    
    # 等待页面加载完成
    page.wait_for_load()
    
    # 等待商品加载（1688是动态加载）
    max_wait = 10  # 最多等待10秒
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        # 检查是否有商品加载出来
        has_items = page.evaluate("""
            () => {
                const selectors = [
                    '[data-spm="offerlist"] .offer-item',
                    '.offer-list .offer-item', 
                    '.sm-offer-item',
                    '[data-offerid]',
                    '.offer-item',
                    '[class*="offerList"] [class*="item"]'
                ];
                for (const s of selectors) {
                    if (document.querySelectorAll(s).length > 0) return true;
                }
                return false;
            }
        """)
        if has_items:
            break
        time.sleep(0.5)
    
    # 额外等待一下确保渲染完成
    time.sleep(1)
    
    # 执行 JS 提取商品数据
    script = """
    () => {
        const items = [];
        // 尝试多种选择器来找到商品卡片
        const selectors = [
            '[data-sper="offerlist"] .offer-item',
            '.offer-list .offer-item',
            '.sm-offer-item',
            '[data-offerid]',
            '.offer-item',
            '[class*="offerList"] [class*="item"]',
            '[class*="offer"] [class*="item"]',
            '.search-offer-item'
        ];
        
        let elements = [];
        for (const selector of selectors) {
            elements = document.querySelectorAll(selector);
            if (elements.length > 0) {
                console.log('Found elements with selector:', selector, elements.length);
                break;
            }
        }
        
        elements.forEach((el, index) => {
            // 尝试多种方式获取标题
            const titleSelectors = ['.title', '.offer-title', '[class*="title"]', 'h3', 'h4', '.name'];
            let titleEl = null;
            for (const s of titleSelectors) {
                titleEl = el.querySelector(s);
                if (titleEl) break;
            }
            
            // 尝试多种方式获取价格
            const priceSelectors = ['.price', '.offer-price', '[class*="price"]', '[class*="Price"]'];
            let priceEl = null;
            for (const s of priceSelectors) {
                priceEl = el.querySelector(s);
                if (priceEl) break;
            }
            
            // 获取链接
            const linkEl = el.querySelector('a[href*="detail.1688.com"], a[href*="offerId"]') || el.closest('a');
            
            const title = titleEl ? titleEl.textContent.trim() : '';
            const price = priceEl ? priceEl.textContent.trim() : '';
            const href = linkEl ? linkEl.href : '';
            
            // 提取 offerId - 从 data 属性或 href
            let offerId = el.getAttribute('data-offerid') || '';
            if (!offerId && href) {
                const match = href.match(/offerId[=:](\\d+)/);
                if (match) offerId = match[1];
            }
            
            if (title || offerId) {
                items.push({
                    index: index,
                    title: title,
                    price: price,
                    offerId: offerId,
                    href: href
                });
            }
        });
        
        return {
            url: window.location.href,
            totalItems: elements.length,
            items: items
        };
    }
    """
    
    try:
        result = page.evaluate(script)
        return result.get("items", [])
    except Exception as e:
        logger.error("从页面提取商品失败: %s", e)
        return []


def run_comparison(
    keyword: str,
    sort_type: str = "sale",
    price_start: float | None = None,
    price_end: float | None = None,
    limit: int = 20,
    port: int = 9222,
    output_dir: str = "./debug_output",
    verbose: bool = False,
) -> dict:
    """运行对比测试。
    
    1. 打开 Chrome 并导航到搜索页面
    2. 同时通过 API 搜索相同条件
    3. 保存两边的原始结果
    4. 对比顺序和内容
    """
    _setup_logging(verbose)
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    browser, page = _connect(port)
    
    try:
        # ========== 第一步：通过 API 搜索 ==========
        logger.info("=" * 60)
        logger.info("【API 搜索】关键词: %s, 排序: %s, 数量: %d", keyword, sort_type, limit)
        logger.info("=" * 60)
        
        session = SessionManager(page)
        session.extract_session(keyword=keyword)
        
        api_products = search_products(
            session=session,
            keyword=keyword,
            sort_type=sort_type,
            price_start=price_start,
            price_end=price_end,
            limit=limit,
            begin_page=1,
        )
        
        # 保存 API 原始结果
        api_result = {
            "source": "api",
            "keyword": keyword,
            "sort": sort_type,
            "price_start": price_start,
            "price_end": price_end,
            "count": len(api_products),
            "timestamp": timestamp,
            "products": [p.to_dict() for p in api_products],
        }
        api_file = _save_raw_data(api_result, f"api_result_{timestamp}.json", output_dir)
        logger.info("API 结果已保存: %s (共 %d 条)", api_file, len(api_products))
        
        # ========== 第二步：Chrome 页面搜索 ==========
        logger.info("=" * 60)
        logger.info("【Chrome 页面】导航到搜索结果页")
        logger.info("=" * 60)
        
        # 构建搜索 URL
        from ali.urls import encode_gbk
        keyword_gbk = encode_gbk(keyword)
        
        # 排序参数映射
        sort_map = {
            "default": "",
            "sale": "va_dsc",
            "price_asc": "price_asc",
            "price_desc": "price_desc",
        }
        sort_param = sort_map.get(sort_type, "")
        
        # 构建 URL
        search_url = f"https://s.1688.com/offer/search.htm?keywords={keyword_gbk}"
        if sort_param:
            search_url += f"&sortType={sort_param}"
        if price_start is not None:
            search_url += f"&priceStart={int(price_start)}"
        if price_end is not None:
            search_url += f"&priceEnd={int(price_end)}"
        
        logger.info("导航到: %s", search_url)
        page.navigate(search_url)
        page.wait_for_load()
        
        # 等待商品加载
        import time
        time.sleep(3)  # 给页面一些时间渲染
        
        # 提取页面上的商品
        page_products = _extract_chrome_page_products(page)
        
        # 保存页面原始结果
        page_result = {
            "source": "chrome_page",
            "keyword": keyword,
            "sort": sort_type,
            "price_start": price_start,
            "price_end": price_end,
            "url": search_url,
            "count": len(page_products),
            "timestamp": timestamp,
            "products": page_products,
        }
        page_file = _save_raw_data(page_result, f"page_result_{timestamp}.json", output_dir)
        logger.info("页面结果已保存: %s (共 %d 条)", page_file, len(page_products))
        
        # ========== 第三步：对比分析 ==========
        logger.info("=" * 60)
        logger.info("【对比分析】")
        logger.info("=" * 60)
        
        comparison = {
            "timestamp": timestamp,
            "keyword": keyword,
            "sort": sort_type,
            "api_count": len(api_products),
            "page_count": len(page_products),
            "match_analysis": [],
        }
        
        # 提取 offerId 进行对比
        api_offer_ids = [p.offer_id for p in api_products if p.offer_id]
        page_offer_ids = [p.get("offerId", "") for p in page_products if p.get("offerId")]
        
        # 检查顺序一致性
        logger.info("API 结果数量: %d", len(api_products))
        logger.info("页面结果数量: %d", len(page_products))
        
        # 对比前 N 条
        compare_count = min(10, len(api_products), len(page_products))
        logger.info("对比前 %d 条商品顺序:", compare_count)
        
        for i in range(compare_count):
            api_product = api_products[i] if i < len(api_products) else None
            page_product = page_products[i] if i < len(page_products) else None
            
            api_id = api_product.offer_id if api_product else ""
            page_id = page_product.get("offerId", "") if page_product else ""
            
            match = api_id == page_id and api_id != ""
            status = "✓ 匹配" if match else "✗ 不匹配"
            
            logger.info("  [%d] API: %s | Page: %s | %s", 
                       i + 1, 
                       api_id[:15] if api_id else "N/A",
                       page_id[:15] if page_id else "N/A",
                       status)
            
            comparison["match_analysis"].append({
                "position": i + 1,
                "api_offer_id": api_id,
                "page_offer_id": page_id,
                "match": match,
                "api_title": api_product.title[:50] if api_product and api_product.title else "",
                "page_title": page_product.get("title", "")[:50] if page_product else "",
            })
        
        # 计算匹配率
        matches = sum(1 for m in comparison["match_analysis"] if m["match"])
        comparison["match_rate"] = matches / compare_count if compare_count > 0 else 0
        
        logger.info("顺序匹配率: %.1f%% (%d/%d)", 
                   comparison["match_rate"] * 100, matches, compare_count)
        
        # 保存对比结果
        comparison_file = _save_raw_data(comparison, f"comparison_{timestamp}.json", output_dir)
        logger.info("对比结果已保存: %s", comparison_file)
        
        return comparison
        
    finally:
        browser.close_page(page)
        browser.close()


def main():
    """主入口。"""
    parser = argparse.ArgumentParser(
        prog="debug_compare.py",
        description="调试：对比 Chrome 页面和 API 搜索结果",
    )
    parser.add_argument("--keyword", "-k", required=True, help="搜索关键词")
    parser.add_argument(
        "--sort", "-s",
        choices=["default", "sale", "price_asc", "price_desc"],
        default="sale",
        help="排序方式",
    )
    parser.add_argument("--price-start", type=float, default=None, help="最低价格")
    parser.add_argument("--price-end", type=float, default=None, help="最高价格")
    parser.add_argument("--limit", "-l", type=int, default=20, help="最大返回数量")
    parser.add_argument("--port", type=int, default=9222, help="Chrome 调试端口")
    parser.add_argument("--output", "-o", default="./debug_output", help="输出目录")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    
    args = parser.parse_args()
    
    try:
        result = run_comparison(
            keyword=args.keyword,
            sort_type=args.sort,
            price_start=args.price_start,
            price_end=args.price_end,
            limit=args.limit,
            port=args.port,
            output_dir=args.output,
            verbose=args.verbose,
        )
        
        print("\n" + "=" * 60)
        print("对比完成!")
        print(f"输出目录: {args.output}")
        print(f"API 结果数: {result['api_count']}")
        print(f"页面结果数: {result['page_count']}")
        print(f"顺序匹配率: {result['match_rate'] * 100:.1f}%")
        
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

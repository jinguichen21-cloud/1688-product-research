"""1688 自动化异常体系。"""


class Ali1688Error(Exception):
    """1688 自动化基础异常。"""


class CDPError(Ali1688Error):
    """CDP 通信异常。"""


class ElementNotFoundError(Ali1688Error):
    """页面元素未找到。"""

    def __init__(self, selector: str) -> None:
        self.selector = selector
        super().__init__(f"未找到元素: {selector}")


class NotLoggedInError(Ali1688Error):
    """未登录。"""

    def __init__(self) -> None:
        super().__init__("未登录，请先扫码登录")


class NoProductsError(Ali1688Error):
    """没有搜索到商品。"""

    def __init__(self) -> None:
        super().__init__("没有搜索到商品")


class TokenExpiredError(Ali1688Error):
    """MTOP API Token 过期。"""

    def __init__(self) -> None:
        super().__init__("_m_h5_tk token 已过期，需要刷新会话")


class SessionError(Ali1688Error):
    """会话提取失败。"""

    def __init__(self, reason: str = "") -> None:
        msg = f"会话提取失败: {reason}" if reason else "会话提取失败"
        super().__init__(msg)

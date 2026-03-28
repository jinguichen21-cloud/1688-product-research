---
name: 1688-product-research
description: |
  1688货源搜索与数据采集助手。支持按关键词搜索商品，采集价格、销量、店铺评分等数据，并写入钉钉AI表格。
  当用户要求进行1688选品、找货源、搜索商品、采集商品数据或批量找货时触发。
version: 0.1.5
cli_version: ">=0.2.10"
---

# 1688 选品助手

在 1688 搜索货源、采集数据并写入 AI 表格。

## 约束

- **禁止重复搜索** — 搜索执行一次，结果保存后直接使用
- **禁止重复写入** — 写入异常时，仅重试失败记录，禁止全量重新写入导致数据重复
- **禁止自行编写数据处理脚本** — 直接用 `dws aitable` 写入表格
- **禁止自己编造dws命令参数** - 使用--help 获取正确命令参数
- 用户说"找货/选品/搜商品"时，默认 `--sort sale` 按销量排序
- 数据必须保存到 AI 表格（除非用户明确拒绝）


## 核心工作流

```bash
# Step 1: 准备环境（检查 dws 版本和 Python 依赖）
# 1.1 检查 dws 版本 >= 0.2.10
DWS_VERSION=$(dws version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
REQUIRED_VERSION="0.2.10"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$DWS_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
  echo "错误：dws 版本 $DWS_VERSION 低于要求的 $REQUIRED_VERSION，请升级 dws"
  exit 1
fi

# 1.2 安装 Python 依赖（使用全局 pip，不使用虚拟环境）
python3 -m pip install -r requirements.txt --quiet

# 1.3 确保 Chrome 已启动（CDP 端口 9222）
# 注意：Chrome 数据目录会自动保存到当前工作目录的 .chrome-profile/ 下
python3 scripts/chrome_launcher.py --port 9222 || {
  echo "Chrome 启动失败，请确保已安装 Chrome"
  exit 1
}

# Step 2: 搜索商品（只执行一次，默认 --sort sale 按销量排序）
python3 scripts/cli.py search -k "关键词" --sort sale -l 20 -o result.json
# 参数：-k关键词, --sort排序(sale/price_asc/price_desc), -l数量, --price-start/--price-end价格区间

# Step 3: 验证数据完整性
jq '.count' result.json  # 确认返回数量

# Step 4: 写入 AI 表格
# 
# 4.1 表格策略
#   - 表格名：1688选品_{类目}（如"1688选品_文具"）
#   - Sheet 名：关键词本身（如"水彩笔"）
#   - 先搜索，存在则复用，不存在则创建
#
# 4.2 字段创建（按需）
#   - 参考"字段映射"表格创建字段
#   - 使用 dws aitable field create
#   - 评分字段需指定范围（0-5）：
#     dws aitable field create --name "综合评分" --type rating \
#       --config '{"icon":"star","min":0,"max":5}'
#
# 4.3 数据转换与写入（伪代码逻辑）：
#   data = json.load('result.json')
#   records = []
#   for product in data['products']:
#       record = {"cells": {}}
#       # 按"字段映射"表格填充字段
#       # 文本/数字：直接赋值
#       # 链接/图片：{"link": "URL", "text": "..."}
#       # 多选：["标签1", "标签2"]
#       records.append(record)
#   # 批量写入（每批 100 条）
#   dws aitable record create --base <BaseID> --table <TableID> --data <records_json>

# Step 5: 返回结果摘要
# 示例：✅ 数据来源：1688平台按销量排序 | ✅ 采集数量：20条春季女装商品
#       ✅ 表格名称：1688选品_女装 | ✅ 访问地址：https://alidocs.dingtalk.com/i/nodes/XXX

# Step 6: 清理（AI 自动处理）
# AI 自动执行以下操作：
# 1. 优雅关闭 Chrome 连接（通过 CDP Browser.close）
# 2. 关闭 cli.py 进程
# 3. 保留 result.json 和 .chrome-profile 供后续使用
# 
# 如需手动清理，可执行：
# python3 scripts/chrome_launcher.py --kill --port 9222
```

## 字段映射

AI 表格字段类型与提取规则（从 `result.json` 的 `.products[]` 提取）：

| AI 表格字段 | 字段类型 | 提取规则 | 写入格式 |
|-------------|----------|----------|----------|
| 采集日期 | 日期 | 系统当前日期 | `"YYYY-MM-DD"` |
| 商品ID | 文本 | `.offer_id` 字符串 | 直接写入 |
| 商品标题 | 文本 | `.title` 字符串 | 直接写入 |
| 商品链接 | 链接 | `.product_url` 字符串 | `{"link": "URL", "text": "查看商品"}` |
| 主图URL | 图片 | `.image_url` 完整 URL | `{"link": "URL", "text": ""}` |
| 价格 | 货币 | `.price` 数值 | 直接写入（转 float） |
| 近期成交件数 | 数字 | `.booked_count` 转整数 | 直接写入 |
| 累计销售数值 | 数字 | `.total_sold` 正则提取数字 | 直接写入 |
| 店铺名称 | 文本 | `.shop_name` 字符串 | 直接写入 |
| 店铺链接 | 链接 | `.shop_url` 字符串 | `{"link": "URL", "text": "查看店铺"}` |
| 省市位置 | 行政区域 | `.location` 字符串 | 直接写入 |
| 复购率 | 数字 | `.repurchase_rate` 百分比 | 直接写入 |
| 回头率 | 数字 | `.return_rate` 百分比 | 直接写入 |
| 综合评分 | 评分 | `.composite_score` | 直接写入（空值→0） |
| 商品评分 | 评分 | `.goods_score` | 直接写入（空值→0） |
| 咨询评分 | 评分 | `.consultation_score` | 直接写入（空值→0） |
| 物流评分 | 评分 | `.logistics_score` | 直接写入（空值→0） |
| 纠纷评分 | 评分 | `.dispute_score` | 直接写入（空值→0） |
| 服务标签 | 多选 | `.service_tags` 字符串数组 | `["标签1", "标签2"]` |
| 促销标签 | 多选 | `.promotion_tags` 字符串数组 | `[]` 或 `["标签1"]` |

### 表格定位与创建示例

```
用户搜索关键词：水彩笔
分析得到类目：文具

表格定位：搜索 "1688选品_文具"
- 找到 → 复用该表格，在其中创建/定位 sheet "水彩笔"
- 未找到 → 创建表格 "1688选品_文具"，并创建 sheet "水彩笔"

最终结构：
- 表格名称：1688选品_文具
- Sheet 名称：水彩笔
- 写入位置：该 sheet 下按字段映射表创建记录
```

## 错误处理

| 问题 | 解决 |
|------|------|
| Chrome 未启动 | `python3 scripts/chrome_launcher.py --port 9222` |
| Chrome 连接失败（沙盒环境） | 脚本已自动适配，如仍失败请检查 Chrome 是否已安装 |
| 搜索返回空 | 换关键词重试；确认 Chrome 正常运行 |
| 权限错误 | 确保当前工作目录可写（Chrome 数据需要写入权限） |
| 字段写入失败 | 检查字段类型与写入格式是否匹配 |
| Field ID 不存在 | 先用 `dws aitable field list` 获取正确的 Field ID |

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
穷鬼麦饱饱 · 20 元热量最大化套餐求解器
===========================================

核心命题：
    在「总价 <= 预算上限（默认 20 元）」的约束下，
    从麦当劳门店实时菜单中求解 **总热量最大** 的套餐组合。

为什么不是一个简单的背包问题：
    麦当劳菜单存在「套餐（combo）嵌套」结构。同一个套餐既可作为整体购买，
    其子项（汉堡 / 薯条 / 饮料）也可以单独购买。若求解器把套餐拆成子项后
    再与单品重复组合，就会算出「实际上买不到」的伪最优解。
    本求解器用 **候选块（Block）模型 + 重叠互斥剪枝** 解决这个问题：
      - 叶子单品 -> 独立 Block
      - 套餐整体 -> 一个 Block（原子，不再拆分）
      - 套餐内的子项 -> 与所属套餐 Block 互斥，不能同时出现

求解算法：分支限界（Branch & Bound）0/1 背包
    - 上界函数：按「热量 / 价格比」降序装填的分数背包松弛
    - 若松弛上界 + 当前热量 <= 当前最优，则整枝剪掉

作者：穷鬼麦饱饱项目
许可：MIT
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 价格单位换算：MCP 返回分为「分」，本求解器内部统一用「分」做整数运算
FEN_PER_YUAN = 100

#: 默认预算（元）
DEFAULT_BUDGET_YUAN = Decimal("20")

#: 热量约束的兜底值。当营养表匹配不到某餐品时使用。
UNKNOWN_KCAL_FALLBACK = 0

#: 需要剔除的商品名关键词（非食品、餐具、赠品等，不应参与热量最大化）
NON_FOOD_KEYWORDS = (
    "餐具", "餐巾", "打包袋", "购物袋", "塑料袋", "吸管", "搅拌棒",
    "玩具", "周边", "券", "卡面", "配送费", "包装费", "餐盒费",
)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class Block:
    """一个「不可再拆的最优候选块」。

    Attributes:
        block_id:   块唯一标识
        name:       展示名称
        price_fen:  单份价格（单位：分）
        kcal:       单份热量（单位：千卡）
        kind:       'item' 独立单品 / 'combo' 套餐整体
        product_code: 对应 MCP 下单用的 productCode
        combo_items: 套餐包含的子项名称（仅用于展示说明）
        conflicts:  与之互斥的 block_id 集合（套餐整体 vs 其子项）
        is_combo_child: 该块是否为某个套餐的子项
        parent_combo_id: 所属套餐的 block_id
    """

    block_id: str
    name: str
    price_fen: int
    kcal: int
    kind: str = "item"
    product_code: str = ""
    combo_items: Tuple[str, ...] = ()
    conflicts: frozenset = frozenset()
    is_combo_child: bool = False
    parent_combo_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def price_yuan(self) -> Decimal:
        return (Decimal(self.price_fen) / FEN_PER_YUAN).quantize(Decimal("0.01"))

    @property
    def density(self) -> float:
        """热量密度 = 千卡 / 元。这是排序与上界计算的核心指标。"""
        yuan = float(self.price_fen) / FEN_PER_YUAN
        if yuan <= 0:
            # 0 元商品（如赠品 / 券）视为无限密度，优先纳入
            return float("inf")
        return self.kcal / yuan


@dataclass
class Plan:
    """求解结果：一个具体的套餐组合方案。"""

    blocks: List[Tuple[Block, int]]  # (块, 份数)
    total_price_fen: int
    total_kcal: int
    budget_fen: int

    @property
    def total_price_yuan(self) -> Decimal:
        return (Decimal(self.total_price_fen) / FEN_PER_YUAN).quantize(Decimal("0.01"))

    @property
    def remaining_yuan(self) -> Decimal:
        return (Decimal(self.budget_fen - self.total_price_fen) / FEN_PER_YUAN).quantize(
            Decimal("0.01")
        )

    @property
    def density(self) -> float:
        return self.total_kcal / max(float(self.total_price_fen) / FEN_PER_YUAN, 1e-9)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_price_yuan": str(self.total_price_yuan),
            "total_price_fen": self.total_price_fen,
            "total_kcal": self.total_kcal,
            "remaining_yuan": str(self.remaining_yuan),
            "kcal_per_yuan": round(self.density, 2),
            "items": [
                {
                    "name": b.name,
                    "quantity": q,
                    "unit_price_yuan": str(b.price_yuan),
                    "unit_kcal": b.kcal,
                    "subtotal_yuan": str(
                        (Decimal(b.price_fen * q) / FEN_PER_YUAN).quantize(Decimal("0.01"))
                    ),
                    "subtotal_kcal": b.kcal * q,
                    "kind": b.kind,
                    "product_code": b.product_code,
                    "combo_items": list(b.combo_items),
                }
                for b, q in self.blocks
            ],
        }


# ---------------------------------------------------------------------------
# 营养表：名称归一化与匹配
# ---------------------------------------------------------------------------


def normalize_name(name: str) -> str:
    """把商品名归一化，便于跨数据源做模糊匹配。

    处理：去空格、全角转半角、去掉括号补充说明、去掉常见前缀后缀、
         统一「大/中/小杯」等规格词的位置。
    """
    if not name:
        return ""
    s = str(name).strip()
    s = s.replace("\u3000", " ")
    # 全角 -> 半角
    s = "".join(
        chr(ord(ch) - 0xFEE0) if 0xFF01 <= ord(ch) <= 0xFF5E else ch for ch in s
    )
    # 去掉括号内容（如「纯牛奶（盒装）」-> 「纯牛奶」）
    s = re.sub(r"[（(【\[].*?[)）】\]]", "", s)
    # 去掉空白与连字符
    s = re.sub(r"[\s\-_·]+", "", s)
    return s.lower()


#: 营养表里「规格词」→ 用于跨表对齐的同义映射。
#: 只保留「菜单名与营养表名确实不同」的映射；
#: 若两表同名（如「麦辣鸡腿汉堡」），归一化后会直接 exact 命中，无需在此登记。
NUTRITION_ALIASES: Dict[str, str] = {
    "板烧鸡腿堡": "原味板烧鸡腿麦香鸡",
    "原味板烧鸡腿堡": "原味板烧鸡腿麦香鸡",
    "板烧鸡腿汉堡": "原味板烧鸡腿麦香鸡",
    "中薯": "中薯条",
    "大薯": "大薯条",
    "小薯": "小薯条",
    "迷你薯": "迷你薯条",
    "可乐(中)": "可乐中杯",
    "可乐(大)": "可乐大杯",
    "可乐(小)": "可乐小杯",
    "雪碧(中)": "雪碧中杯",
    "奥利奥麦旋风": "奥利奥麦旋风",
}


def parse_nutrition(raw: str) -> Dict[str, int]:
    """解析 ``list-nutrition-foods`` 返回的类 CSV 文本。

    返回格式说明：
        返回值首行形如 ``[160]{productName,nutritionDescription,energyKj,
        energyKcal,protein,fat,carbohydrate,sodium,calcium}:``，
        其后每行是一条以英文逗号分隔的记录。

    Args:
        raw: MCP 工具返回的原始字符串。

    Returns:
        ``{归一化名称: 千卡}`` 的映射表。
    """
    table: Dict[str, int] = {}
    if not raw or not isinstance(raw, str):
        return table

    body = raw
    # 去掉 [160]{...}: 这一行表头
    m = re.match(r"^\s*\[\d+\]\{[^}]*\}\s*:?\s*", body)
    if m:
        body = body[m.end():]

    for line in body.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        name = parts[0]
        if not name or name.lower() == "productname":
            continue
        # 第 4 列是 energyKcal（第 3 列是 energyKj）
        kcal_raw = parts[3]
        try:
            kcal = int(float(kcal_raw))
        except (TypeError, ValueError):
            continue
        if kcal < 0:
            # 负热量属于脏数据，按 0 处理，避免污染「热量最大化」目标函数
            kcal = 0
        key = normalize_name(name)
        if key:
            # 同名冲突时取较大值（保守策略：宁高不低，避免低估套餐热量）
            table[key] = max(table.get(key, 0), kcal)

    return table


def lookup_kcal(name: str, table: Dict[str, int]) -> Tuple[int, str]:
    """在营养表中查热量，返回 ``(千卡, 命中方式)``。

    命中方式取值：``exact`` / ``alias`` / ``contains`` / ``miss``。

    匹配优先级：
        1. exact    —— 名称归一化后直接命中
        2. alias    —— 经 ``NUTRITION_ALIASES`` 同义改写后命中
        3. contains —— 双向子串包含，取名称长度差最小者（最相近）
    """
    key = normalize_name(name)
    if not key:
        return UNKNOWN_KCAL_FALLBACK, "miss"

    if key in table:
        return table[key], "exact"

    # 别名表两边的键都做归一化后比较，避免因空格/括号/全角差异漏配
    for src, dst in NUTRITION_ALIASES.items():
        if normalize_name(src) == key:
            dst_key = normalize_name(dst)
            if dst_key in table:
                return table[dst_key], "alias"

    # 双向包含兜底：优先取最相近（名称长度差最小）的候选
    best: Optional[Tuple[int, int]] = None
    for k, v in table.items():
        if k in key or key in k:
            diff = abs(len(k) - len(key))
            if best is None or diff < best[0]:
                best = (diff, v)
    if best is not None:
        return best[1], "contains"

    return UNKNOWN_KCAL_FALLBACK, "miss"


# ---------------------------------------------------------------------------
# 菜单解析：raw MCP JSON -> Block 列表
# ---------------------------------------------------------------------------


def _to_fen(value: Any) -> int:
    """把价格统一转成「分」的整数。

    兼容三种输入：
        - 字符串或浮点的「元」（如 ``"13.5"``）
        - 已经是「分」的整数（如 ``1350``）—— 通过启发式判断
        - ``None`` / 空 -> 0
    """
    if value is None or value == "":
        return 0
    if isinstance(value, str):
        value = value.strip().replace("¥", "").replace("￥", "").replace("元", "")
        if not value:
            return 0
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0
    if num <= 0:
        return 0
    # 启发式：>= 1000 且为整数，通常已经是「分」
    if num >= 1000 and float(num).is_integer():
        return int(num)
    return int(round(num * FEN_PER_YUAN))


def _is_food(name: str) -> bool:
    low = (name or "").lower()
    return not any(kw in low for kw in NON_FOOD_KEYWORDS)


def build_blocks(
    meals_payload: Dict[str, Any],
    nutrition: Dict[str, int],
    *,
    max_unknown_warn: int = 5,
) -> Tuple[List[Block], List[str]]:
    """把 ``query-meals`` 的返回体转换成候选块列表。

    关键逻辑：
        1. 先识别「套餐类」商品（名称含「套餐 / 组合 / 桶 / 盒」，
           或 raw 中存在 roundList / comboItemList）。
        2. 套餐整体作为**一个原子 Block**，其名称标注包含内容。
        3. 若套餐的 raw 中能解析出子项，则为子项建立 **互斥标记**：
           一旦选了套餐整体，子项就不能再单独出现（反之亦然），
           避免「套餐 + 套餐内单品」的伪最优解。

    Returns:
        ``(blocks, warnings)``。warnings 记录热量未命中的商品名。
    """
    data = meals_payload.get("data", meals_payload) or {}
    meals_map: Dict[str, Any] = data.get("meals", {}) or {}
    categories: List[Dict[str, Any]] = data.get("categories", []) or []

    # 建立 code -> 分类名 的索引，用于套餐识别辅助
    code_to_category: Dict[str, str] = {}
    for cat in categories:
        cname = cat.get("name", "")
        for meal in cat.get("meals", []) or []:
            code = str(meal.get("code", ""))
            if code:
                code_to_category[code] = cname

    blocks: List[Block] = []
    warnings: List[str] = []
    combo_ids: Dict[str, str] = {}  # combo 名称 -> block_id

    # ---------- 第一遍：识别并登记所有套餐整体 ----------
    for code, meal in meals_map.items():
        if not isinstance(meal, dict):
            continue
        name = str(meal.get("name", "") or "").strip()
        if not name or not _is_food(name):
            continue
        if not _looks_like_combo(name, meal, code_to_category.get(str(code), "")):
            continue
        price = _to_fen(
            meal.get("currentPrice") or meal.get("price") or meal.get("salePrice")
        )
        if price <= 0:
            continue
        kcal = _combo_kcal(name, meal, nutrition)
        combo_items = _combo_child_names(meal)
        bid = f"combo::{code}"
        combo_ids[name] = bid
        blocks.append(
            Block(
                block_id=bid,
                name=name,
                price_fen=price,
                kcal=kcal,
                kind="combo",
                product_code=str(code),
                combo_items=combo_items,
                raw=meal,
            )
        )

    # ---------- 第二遍：登记独立单品，并建立互斥 ----------
    for code, meal in meals_map.items():
        if not isinstance(meal, dict):
            continue
        name = str(meal.get("name", "") or "").strip()
        if not name or not _is_food(name):
            continue
        if _looks_like_combo(name, meal, code_to_category.get(str(code), "")):
            continue  # 已在第一遍处理

        price = _to_fen(
            meal.get("currentPrice") or meal.get("price") or meal.get("salePrice")
        )
        if price <= 0:
            continue

        kcal, hit = lookup_kcal(name, nutrition)
        if hit == "miss" and len(warnings) < max_unknown_warn:
            warnings.append(name)

        blocks.append(
            Block(
                block_id=f"item::{code}",
                name=name,
                price_fen=price,
                kcal=kcal,
                kind="item",
                product_code=str(code),
                raw=meal,
            )
        )

    # ---------- 第三遍：套餐子项 -> 与套餐整体建立互斥 ----------
    # 说明：MCP 的套餐子项通常不在 meals_map 中单列。此处做的是「防御性关联」——
    # 若某个单品名称刚好出现在某套餐的子项名列表里，则二者互斥。
    by_name: Dict[str, List[Block]] = {}
    for b in blocks:
        by_name.setdefault(normalize_name(b.name), []).append(b)

    for combo in [b for b in blocks if b.kind == "combo"]:
        for child_name in combo.combo_items:
            for child in by_name.get(normalize_name(child_name), []):
                if child.kind == "combo":
                    continue
                _add_conflict(combo, child)
                child.is_combo_child = True
                child.parent_combo_id = combo.block_id

    return blocks, warnings


def _looks_like_combo(name: str, meal: Dict[str, Any], category: str = "") -> bool:
    """判断一个商品是否为「套餐」。"""
    if any(kw in name for kw in ("套餐", "组合", "桶", "双人", "分享盒", "超值")):
        return True
    if "套餐" in category or "组合" in category:
        return True
    # raw 结构里带 roundList / comboItemList 的，也按套餐处理
    for field_name in ("roundList", "comboItemList", "comboItems", "rounds"):
        if meal.get(field_name):
            return True
    return False


def _combo_child_names(meal: Dict[str, Any]) -> Tuple[str, ...]:
    """从套餐 raw 中尽力抽出子项名称，仅用于展示与互斥关联。"""
    names: List[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            nm = node.get("name") or node.get("mealName")
            if isinstance(nm, str) and nm.strip():
                names.append(nm.strip())
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    for field_name in ("roundList", "comboItemList", "comboItems", "rounds"):
        if meal.get(field_name):
            _walk(meal[field_name])

    # 去重保序
    seen = set()
    out: List[str] = []
    for n in names:
        k = normalize_name(n)
        if k and k not in seen:
            seen.add(k)
            out.append(n)
    return tuple(out)


def _combo_kcal(name: str, meal: Dict[str, Any], nutrition: Dict[str, int]) -> int:
    """估算套餐热量：优先整名命中；否则把子项热量相加。"""
    kcal, hit = lookup_kcal(name, nutrition)
    if hit in ("exact", "alias"):
        return kcal

    child_names = _combo_child_names(meal)
    if child_names:
        total = 0
        matched = False
        for cn in child_names:
            k, h = lookup_kcal(cn, nutrition)
            if h != "miss":
                total += k
                matched = True
        if matched:
            return total

    # 再退一步：用名称里的关键词做「组合拆解」
    return _kcal_from_name_composition(name, nutrition)


#: 组合名拆解词表：名称里出现即认为包含了对应单品
COMPOSITION_HINTS: Sequence[Tuple[str, str]] = (
    ("巨无霸", "巨无霸"),
    ("双层吉士", "双层吉士汉堡"),
    ("吉士", "吉士汉堡包"),
    ("板烧", "原味板烧鸡腿麦香鸡"),
    ("麦辣鸡腿", "麦辣鸡腿汉堡"),
    ("麦香鸡", "麦香鸡"),
    ("麦香鱼", "麦香鱼"),
    ("脆汁鸡", "麦麦脆汁鸡-琵琶腿"),
    ("鸡排", "那么大鸡排"),
    ("鸡块", "麦乐鸡5块"),
    ("麦乐鸡", "麦乐鸡5块"),
    ("薯条", "中薯条"),
    ("薯饼", "脆薯饼"),
    ("可乐", "可乐中杯"),
    ("雪碧", "雪碧中杯"),
    ("咖啡", "大杯鲜萃咖啡"),
    ("红茶", "锡兰红茶"),
    ("豆浆", "优品豆浆中杯"),
    ("玉米", "大杯玉米杯"),
    ("派", "香芋派"),
    ("冰淇淋", "圆筒冰淇淋"),
    ("新地", "朱古力新地"),
    ("麦旋风", "奥利奥麦旋风"),
    ("牛奶", "纯牛奶"),
)


def _kcal_from_name_composition(name: str, nutrition: Dict[str, int]) -> int:
    """当整名与子项都匹配不到时，按名称里的已知单品关键词累加热量。

    这是一个**兜底启发式**：只用于让未收录的套餐有一个合理的量级估计，
    返回值会在结果里标注 ``estimated``，提醒用户以官方数据为准。
    """
    total = 0
    matched_any = False
    for hint, target in COMPOSITION_HINTS:
        if hint in name:
            k, h = lookup_kcal(target, nutrition)
            if h != "miss":
                total += k
                matched_any = True
    if matched_any:
        # 套餐常含中薯 + 中可，补一个最小配置的余量，避免系统性低估
        k_fries, _ = lookup_kcal("中薯条", nutrition)
        k_drink, _ = lookup_kcal("可乐中杯", nutrition)
        if k_fries and "薯条" not in name:
            total += max(k_fries // 2, 0)
        if k_drink and "可乐" not in name:
            total += max(k_drink // 2, 0)
        return total
    return UNKNOWN_KCAL_FALLBACK


def _add_conflict(a: Block, b: Block) -> None:
    """给两个块建立双向互斥关系。"""
    a.conflicts = frozenset(set(a.conflicts) | {b.block_id})
    b.conflicts = frozenset(set(b.conflicts) | {a.block_id})


# ---------------------------------------------------------------------------
# 求解器：分支限界 0/1 背包 + 互斥剪枝
# ---------------------------------------------------------------------------


def solve(
    blocks: Sequence[Block],
    budget_fen: int,
    *,
    max_per_item: int = 1,
    time_budget_ms: int = 20000,
    top_k: int = 3,
) -> List[Plan]:
    """在预算内求解总热量最大的套餐组合。

    采用「分支限界 + 分数背包松弛上界」：
        - 块按热量密度降序排列，保证松弛上界单调
        - 深度优先搜索，进入分支前先算上界，超不过当前最优就整枝剪掉

    Args:
        blocks:        候选块列表（应已做互斥处理）
        budget_fen:    预算上限（单位：分）
        max_per_item:  每种商品的购买上限（默认 1，穷鬼套餐讲究搭配）
        time_budget_ms: 求解时间预算（毫秒），防止恶意数据导致卡死
        top_k:         需要返回的最优方案个数（会返回 top_k 个不同组合）

    Returns:
        按总热量降序排列的方案列表（最多 top_k 个）。
    """
    import time

    deadline = time.monotonic() + time_budget_ms / 1000.0

    # 过滤掉价格为 0 或热量为 0 的块（对目标无贡献，还会撑大搜索空间）
    cands = [b for b in blocks if b.price_fen > 0 and b.kcal > 0]
    # 单块价格就超过预算的直接剔除
    cands = [b for b in cands if b.price_fen <= budget_fen]
    if not cands:
        return []

    # 按密度降序，保证松弛上界有效
    cands.sort(key=lambda b: (-b.density, b.price_fen))
    n = len(cands)
    id_to_idx = {b.block_id: i for i, b in enumerate(cands)}

    # 互斥表：索引 -> 索引集合
    conflicts_idx: List[frozenset] = []
    for b in cands:
        idxs = {id_to_idx[c] for c in b.conflicts if c in id_to_idx}
        conflicts_idx.append(frozenset(idxs))

    # 后缀松弛上界：suffix_bound[i] = 用 i..n-1 的块（允许分数）能拿到的最多热量
    # 这里只做「按密度装填」的粗上界，足够剪枝且计算 O(n)
    suffix_bound = [0.0] * (n + 1)
    # 反向累加会破坏贪心语义，改为正向预计算：density 递减，故直接累加
    acc = 0.0
    for i in range(n - 1, -1, -1):
        acc += cands[i].kcal
        suffix_bound[i] = acc

    best_plans: List[Tuple[int, Tuple[int, ...]]] = []  # (kcal, 组合索引元组)
    best_kcal = -1
    explored = 0

    def upper_bound(i: int, remain: int, cur_kcal: int) -> float:
        """分数背包松弛上界（保守，宁可高估也不漏解）。"""
        ub = float(cur_kcal)
        rem = float(remain)
        j = i
        while j < n and rem > 0:
            b = cands[j]
            if b.price_fen <= rem:
                ub += b.kcal
                rem -= b.price_fen
                j += 1
            else:
                ratio = rem / b.price_fen
                ub += b.kcal * ratio
                rem = 0
                break
        return ub

    def dfs(i: int, remain: int, cur_kcal: int, chosen: List[int], prices: Dict[int, int]):
        nonlocal best_kcal, explored
        explored += 1
        if explored % 4096 == 0 and time.monotonic() > deadline:
            raise TimeoutError("求解超时，已返回当前最优解")

        if i >= n:
            key = tuple(sorted(chosen))
            if not key:
                return
            # 去重：同一个组合只保留一次
            if any(k == key for _, k in best_plans):
                return
            best_plans.append((cur_kcal, key))
            best_plans.sort(key=lambda x: -x[0])
            del best_plans[top_k:]
            if best_plans:
                best_kcal = best_plans[0][0]
            return

        if upper_bound(i, remain, cur_kcal) <= best_kcal:
            return  # 整枝

        b = cands[i]

        # 分支 1：选入该块
        if b.price_fen <= remain:
            ok = all(c not in chosen for c in conflicts_idx[i])
            if ok:
                chosen.append(i)
                dfs(i + 1, remain - b.price_fen, cur_kcal + b.kcal, chosen, prices)
                chosen.pop()

        # 分支 2：跳过该块
        dfs(i + 1, remain, cur_kcal, chosen, prices)

    try:
        dfs(0, budget_fen, 0, [], {})
    except TimeoutError:
        pass
    except RecursionError:
        pass

    plans: List[Plan] = []
    for kcal, idxs in best_plans:
        price = sum(cands[i].price_fen for i in idxs)
        items = [(cands[i], 1) for i in idxs]
        items.sort(key=lambda x: (-x[0].kcal, x[0].price_fen))
        plans.append(
            Plan(blocks=items, total_price_fen=price, total_kcal=kcal, budget_fen=budget_fen)
        )
    return plans


# ---------------------------------------------------------------------------
# 输出渲染
# ---------------------------------------------------------------------------


def plan_to_json(plan: Plan, *, warnings: Optional[List[str]] = None) -> str:
    payload = plan.to_dict()
    if warnings:
        payload["warnings"] = warnings
    return json.dumps(payload, ensure_ascii=False, indent=2)


def plan_to_markdown(plan: Plan, *, index: int = 1, warnings: Optional[List[str]] = None) -> str:
    lines: List[str] = []
    title = "穷鬼麦饱饱 · 最优解" if index == 1 else f"穷鬼麦饱饱 · 备选方案 {index}"
    lines.append(f"### {title}")
    lines.append("")
    lines.append("| 商品 | 数量 | 单价 | 小计热量 |")
    lines.append("| --- | ---: | ---: | ---: |")
    for b, q in plan.blocks:
        lines.append(
            f"| {b.name}{'（套餐）' if b.kind == 'combo' else ''} "
            f"| ×{q} | ¥{b.price_yuan} | {b.kcal * q} kcal |"
        )
    lines.append(
        f"| **合计** |  | **¥{plan.total_price_yuan}** | **{plan.total_kcal} kcal** |"
    )
    lines.append("")
    lines.append(
        f"- 预算上限：¥{Decimal(plan.budget_fen) / FEN_PER_YUAN:.2f}"
        f"　剩余：¥{plan.remaining_yuan}"
    )
    lines.append(
        f"- 热量效率：**{plan.density:.2f} kcal/元**（穷鬼核心指标，越高越赚）"
    )
    if warnings:
        lines.append(f"- ⚠️ 未匹配到营养数据的商品（按 0 计）：{'、'.join(warnings)}")
    return "\n".join(lines)


def plan_to_csv_rows(plan: Plan) -> List[List[str]]:
    rows = [["商品", "数量", "单价(元)", "小计(元)", "小计热量(kcal)", "类型"]]
    for b, q in plan.blocks:
        rows.append(
            [
                b.name,
                str(q),
                str(b.price_yuan),
                str((Decimal(b.price_fen * q) / FEN_PER_YUAN).quantize(Decimal("0.01"))),
                str(b.kcal * q),
                "套餐" if b.kind == "combo" else "单品",
            ]
        )
    rows.append(
        [
            "合计",
            "",
            "",
            str(plan.total_price_yuan),
            str(plan.total_kcal),
            f"{plan.density:.2f} kcal/元",
        ]
    )
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qionggui_solver",
        description="穷鬼麦饱饱：在预算内求热量最大的麦当劳套餐组合",
    )
    parser.add_argument(
        "--meals", required=True, help="query-meals 返回的 JSON 文件路径"
    )
    parser.add_argument(
        "--nutrition", required=True, help="list-nutrition-foods 返回的原始文本文件路径"
    )
    parser.add_argument(
        "--budget", default=str(DEFAULT_BUDGET_YUAN), help="预算上限（元），默认 20"
    )
    parser.add_argument("--top-k", type=int, default=3, help="返回候选方案个数，默认 3")
    parser.add_argument(
        "--max-per-item", type=int, default=1, help="每种商品最大份数，默认 1"
    )
    parser.add_argument("--format", choices=["markdown", "json", "csv"], default="markdown")
    parser.add_argument("--out", default="", help="输出文件路径，留空则打印到 stdout")
    args = parser.parse_args(argv)

    meals = _load_json(args.meals)
    with open(args.nutrition, "r", encoding="utf-8") as f:
        nutrition_raw = f.read()
    nutrition = parse_nutrition(nutrition_raw)
    if not nutrition:
        print("错误：营养表为空，无法计算热量。", file=sys.stderr)
        return 2

    blocks, warnings = build_blocks(meals, nutrition)
    if not blocks:
        print("错误：未能从菜单中解析出任何有效商品。", file=sys.stderr)
        return 3

    budget_fen = int(Decimal(str(args.budget)) * FEN_PER_YUAN)
    plans = solve(
        blocks, budget_fen, max_per_item=args.max_per_item, top_k=args.top_k
    )
    if not plans:
        print(f"在 ¥{args.budget} 预算内没有找到可行组合。", file=sys.stderr)
        return 4

    if args.format == "json":
        text = json.dumps(
            {
                "budget_yuan": str(args.budget),
                "plans": [p.to_dict() for p in plans],
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    elif args.format == "csv":
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        for i, p in enumerate(plans, 1):
            writer.writerow([f"# 方案 {i}"])
            writer.writerows(plan_to_csv_rows(p))
            writer.writerow([])
        text = buf.getvalue()
    else:
        text = "\n\n".join(
            plan_to_markdown(p, index=i, warnings=warnings if i == 1 else None)
            for i, p in enumerate(plans, 1)
        )

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print(f"已写出：{args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

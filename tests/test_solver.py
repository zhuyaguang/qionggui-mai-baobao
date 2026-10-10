#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""穷鬼麦饱饱 · 求解器单元测试

运行：
    python -m unittest discover -s tests -v
或：
    python tests/test_solver.py

测试覆盖：
    1. 营养表解析（真实 MCP 返回格式）
    2. 名称归一化与模糊匹配
    3. 价格单位换算（元 / 分 双兼容）
    4. 套餐识别与互斥建立（防伪最优解）
    5. 分支限界求解正确性（与暴力枚举对照）
    6. 预算约束与热量最大化目标
    7. 边界：空菜单、预算过小、全 0 热量
"""

import os
import sys
import unittest
from decimal import Decimal
from itertools import combinations

# 让测试可以直接从 scripts/ 目录导入被测模块。
# 注意：必须在导入被测模块之前完成 sys.path 注入，
# 因此这里不使用 `unittest discover`（它在导入阶段就解析了模块路径），
# 而是直接以脚本方式运行本文件。
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(
    PROJECT_ROOT, "skills", "qionggui-mai-baobao", "scripts"
)
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from qionggui_solver import (  # noqa: E402
    Block,
    FEN_PER_YUAN,
    _to_fen,
    build_blocks,
    lookup_kcal,
    normalize_name,
    parse_nutrition,
    plan_to_markdown,
    solve,
)

# ---------------------------------------------------------------------------
# 真实 MCP 返回样例（截取自 mcd-mcp list-nutrition-foods 实际响应）
# ---------------------------------------------------------------------------

NUTRITION_SAMPLE = (
    "[160]{productName,nutritionDescription,energyKj,energyKcal,protein,"
    "fat,carbohydrate,sodium,calcium}:\n"
    "  猪柳麦满分,null,1288,308,16,16,24,781,213\n"
    "  中薯条,null,1210,289,4,12,38,165,18\n"
    "  大薯条,null,1587,379,6,16,50,216,23\n"
    "  小薯条,null,877,210,3,9,28,120,13\n"
    "  可乐中杯,null,616,147,0,0,36,0,10\n"
    "  可乐大杯,null,936,224,0,0,55,0,15\n"
    "  可乐小杯,null,446,107,0,0,26,0,7\n"
    "  麦乐鸡5块,null,890,213,12,12,13,422,9\n"
    "  麦辣鸡翅-2块,null,937,224,13,15,9,537,13\n"
    "  圆筒冰淇淋,null,391,93,2,3,14,36,77\n"
    "  吉士汉堡包,null,1231,294,16,12,30,673,144\n"
    "  双层吉士汉堡,null,1796,429,27,22,31,1017,232\n"
    "  麦香鸡,null,1546,369,15,17,39,731,73\n"
    "  麦香鱼,null,1359,325,16,13,35,556,99\n"
    "  麦辣鸡腿汉堡,null,2029,485,24,24,42,1208,154\n"
    "  巨无霸,null,2146,513,27,26,42,961,171\n"
    "  汉堡包,null,1039,248,13,8,29,492,61\n"
    "  那么大鸡排,null,1612,385,24,21,24,996,13\n"
    "  脆薯饼,null,612,146,1,9,14,311,7\n"
    "  纯牛奶（盒装）,null,541,129,7,7,10,73,231\n"
    "  香芋派,null,971,232,2,12,28,159,7\n"
    "  奥利奥麦旋风,null,1115,266,5,9,40,116,185\n"
)


def _meals_payload(meals, categories=None):
    """构造一个 query-meals 形状的返回体。"""
    return {
        "success": True,
        "code": 200,
        "data": {
            "categories": categories or [],
            "meals": {m["code"]: m for m in meals},
        },
    }


# ---------------------------------------------------------------------------
# 1. 营养表解析
# ---------------------------------------------------------------------------


class TestNutritionParsing(unittest.TestCase):
    def test_parses_real_mcp_format(self):
        table = parse_nutrition(NUTRITION_SAMPLE)
        self.assertEqual(table["巨无霸"], 513)
        self.assertEqual(table["中薯条"], 289)
        self.assertEqual(table["可乐中杯"], 147)
        self.assertEqual(len(table), 22)

    def test_skips_header_line(self):
        table = parse_nutrition(NUTRITION_SAMPLE)
        self.assertNotIn("productname", table)
        self.assertNotIn("energykcal", table)

    def test_empty_input_returns_empty_table(self):
        self.assertEqual(parse_nutrition(""), {})
        self.assertEqual(parse_nutrition(None), {})

    def test_malformed_lines_are_skipped(self):
        raw = "[2]{a,b,c,d}:\n只有名字\n甲,乙,丙\n丁,戊,己,100"
        table = parse_nutrition(raw)
        self.assertEqual(table, {"丁": 100})

    def test_duplicate_names_keep_max(self):
        raw = "[2]{a,b,c,d}:\n巨无霸,0,100,400\n巨无霸,0,100,513"
        self.assertEqual(parse_nutrition(raw)["巨无霸"], 513)

    def test_negative_or_float_kcal_handled(self):
        """浮点热量取整；负值视为无效数据，按 0 处理（避免污染最大化目标）。"""
        raw = "[2]{a,b,c,d}:\n甲,0,0,308.0\n乙,0,0,-5"
        table = parse_nutrition(raw)
        self.assertEqual(table["甲"], 308)
        self.assertEqual(table["乙"], 0)


# ---------------------------------------------------------------------------
# 2. 名称归一化与匹配
# ---------------------------------------------------------------------------


class TestNormalizeAndLookup(unittest.TestCase):
    def setUp(self):
        self.table = parse_nutrition(NUTRITION_SAMPLE)

    def test_normalize_strips_brackets_and_spaces(self):
        self.assertEqual(normalize_name("纯牛奶（盒装）"), "纯牛奶")
        self.assertEqual(normalize_name(" 巨 无 霸 "), "巨无霸")
        self.assertEqual(normalize_name("麦乐鸡 5块"), "麦乐鸡5块")

    def test_normalize_fullwidth_to_halfwidth(self):
        self.assertEqual(normalize_name("ＡＢＣ"), "abc")

    def test_exact_match(self):
        kcal, hit = lookup_kcal("巨无霸", self.table)
        self.assertEqual((kcal, hit), (513, "exact"))

    def test_bracket_variant_still_matches(self):
        kcal, hit = lookup_kcal("纯牛奶（盒装）", self.table)
        self.assertEqual(hit, "exact")
        self.assertEqual(kcal, 129)

    def test_alias_panshao_returns_real_value(self):
        """别名命中后必须拿到真实热量，而不是回落到 contains 的模糊值。"""
        table = parse_nutrition(
            NUTRITION_SAMPLE
            + "  原味板烧鸡腿麦香鸡,null,1029,246,15,9,25,611,133\n"
        )
        kcal, hit = lookup_kcal("板烧鸡腿堡", table)
        self.assertEqual(hit, "alias")
        self.assertEqual(kcal, 246)

    def test_same_name_hits_exact_not_alias(self):
        """两表同名的商品应直接 exact，不应误走别名。"""
        kcal, hit = lookup_kcal("麦辣鸡腿汉堡", self.table)
        self.assertEqual(hit, "exact")
        self.assertEqual(kcal, 485)

    def test_contains_fallback(self):
        kcal, hit = lookup_kcal("巨无霸套餐", self.table)
        self.assertEqual(hit, "contains")
        self.assertEqual(kcal, 513)

    def test_miss_returns_zero(self):
        kcal, hit = lookup_kcal("不存在的商品", self.table)
        self.assertEqual((kcal, hit), (0, "miss"))


# ---------------------------------------------------------------------------
# 3. 价格单位换算
# ---------------------------------------------------------------------------


class TestPriceConversion(unittest.TestCase):
    def test_yuan_float(self):
        self.assertEqual(_to_fen(13.5), 1350)

    def test_yuan_string(self):
        self.assertEqual(_to_fen("13.50"), 1350)
        self.assertEqual(_to_fen("¥13.5"), 1350)
        self.assertEqual(_to_fen("13.5元"), 1350)

    def test_fen_becomes_fen(self):
        self.assertEqual(_to_fen(1350), 1350)
        self.assertEqual(_to_fen(2000), 2000)

    def test_small_integer_is_yuan(self):
        self.assertEqual(_to_fen(20), 2000)
        self.assertEqual(_to_fen(5), 500)

    def test_none_and_garbage(self):
        for bad in (None, "", "abc", "¥"):
            self.assertEqual(_to_fen(bad), 0)

    def test_zero_and_negative(self):
        self.assertEqual(_to_fen(0), 0)
        self.assertEqual(_to_fen(-5), 0)


# ---------------------------------------------------------------------------
# 4. 套餐识别与互斥
# ---------------------------------------------------------------------------


class TestComboHandling(unittest.TestCase):
    def setUp(self):
        self.nutrition = parse_nutrition(NUTRITION_SAMPLE)

    def test_combo_recognized_by_name(self):
        payload = _meals_payload(
            [
                {"code": "C1", "name": "巨无霸套餐", "currentPrice": "30.00"},
                {"code": "S1", "name": "巨无霸", "currentPrice": "22.00"},
                {"code": "S2", "name": "中薯条", "currentPrice": "13.00"},
            ]
        )
        blocks, _ = build_blocks(payload, self.nutrition)
        kinds = {b.name: b.kind for b in blocks}
        self.assertEqual(kinds["巨无霸套餐"], "combo")
        self.assertEqual(kinds["巨无霸"], "item")
        self.assertEqual(kinds["中薯条"], "item")

    def test_combo_child_conflict_established(self):
        """选了套餐整体，就应排除其子项单品，避免伪最优解。"""
        payload = _meals_payload(
            [
                {
                    "code": "C1",
                    "name": "超值套餐",
                    "currentPrice": "20.00",
                    "roundList": [
                        {"comboItemList": [{"name": "巨无霸"}, {"name": "中薯条"}]}
                    ],
                },
                {"code": "S1", "name": "巨无霸", "currentPrice": "15.00"},
                {"code": "S2", "name": "中薯条", "currentPrice": "8.00"},
            ]
        )
        blocks, _ = build_blocks(payload, self.nutrition)
        combo = next(b for b in blocks if b.kind == "combo")
        self.assertIn("巨无霸", combo.combo_items)
        self.assertIn("中薯条", combo.combo_items)

        bigmac = next(b for b in blocks if b.name == "巨无霸")
        self.assertTrue(bigmac.is_combo_child)
        self.assertEqual(bigmac.parent_combo_id, combo.block_id)
        self.assertIn(bigmac.block_id, combo.conflicts)
        self.assertIn(combo.block_id, bigmac.conflicts)

    def test_combo_kcal_summed_from_children(self):
        payload = _meals_payload(
            [
                {
                    "code": "C1",
                    "name": "自定义组合",
                    "currentPrice": "20.00",
                    "roundList": [
                        {"comboItemList": [{"name": "巨无霸"}, {"name": "大薯条"}]}
                    ],
                }
            ]
        )
        blocks, _ = build_blocks(payload, self.nutrition)
        combo = blocks[0]
        # 巨无霸 513 + 大薯条 379
        self.assertEqual(combo.kcal, 513 + 379)

    def test_non_food_filtered_out(self):
        payload = _meals_payload(
            [
                {"code": "X1", "name": "餐具包", "currentPrice": "1.00"},
                {"code": "X2", "name": "配送费", "currentPrice": "9.00"},
                {"code": "S1", "name": "巨无霸", "currentPrice": "22.00"},
            ]
        )
        blocks, _ = build_blocks(payload, self.nutrition)
        self.assertEqual([b.name for b in blocks], ["巨无霸"])

    def test_zero_price_items_excluded(self):
        payload = _meals_payload(
            [
                {"code": "Z1", "name": "巨无霸", "currentPrice": "0"},
                {"code": "S1", "name": "麦香鸡", "currentPrice": "18.00"},
            ]
        )
        blocks, _ = build_blocks(payload, self.nutrition)
        self.assertEqual([b.name for b in blocks], ["麦香鸡"])


# ---------------------------------------------------------------------------
# 5. 求解正确性：与暴力枚举对照
# ---------------------------------------------------------------------------


class TestSolverCorrectness(unittest.TestCase):
    @staticmethod
    def brute_force(blocks, budget_fen):
        """暴力枚举所有子集（小规模），返回最大热量。"""
        best = 0
        n = len(blocks)
        for r in range(1, n + 1):
            for combo in combinations(range(n), r):
                price = sum(blocks[i].price_fen for i in combo)
                if price > budget_fen:
                    continue
                kcal = sum(blocks[i].kcal for i in combo)
                if kcal > best:
                    best = kcal
        return best

    def test_matches_brute_force_random_small(self):
        import random

        random.seed(20261010)
        for trial in range(60):
            n = random.randint(3, 11)
            blocks = []
            for i in range(n):
                blocks.append(
                    Block(
                        block_id=f"b{i}",
                        name=f"商品{i}",
                        price_fen=random.randint(200, 1600),
                        kcal=random.randint(50, 700),
                    )
                )
            budget = random.randint(500, 3000)
            plans = solve(blocks, budget, top_k=1)
            expected = self.brute_force(blocks, budget)
            got = plans[0].total_kcal if plans else 0
            self.assertEqual(
                got,
                expected,
                msg=f"trial={trial} budget={budget} got={got} expected={expected}",
            )

    def test_respects_budget_strictly(self):
        blocks = [
            Block("a", "A", 1200, 500),
            Block("b", "B", 900, 400),
            Block("c", "C", 700, 250),
        ]
        plans = solve(blocks, 2000, top_k=3)
        for p in plans:
            self.assertLessEqual(p.total_price_fen, 2000)

    def test_maximizes_kcal_not_quantity(self):
        """核心断言：应优先选热量密度高的，而不是件数多的。"""
        blocks = [
            Block("high", "高密度", 2000, 900),  # 0.45 kcal/分
            Block("low1", "低密度1", 500, 60),  # 0.12
            Block("low2", "低密度2", 500, 60),
            Block("low3", "低密度3", 500, 60),
            Block("low4", "低密度4", 500, 60),
        ]
        plans = solve(blocks, 2000, top_k=1)
        self.assertEqual(plans[0].total_kcal, 900)
        self.assertEqual(len(plans[0].blocks), 1)

    def test_conflicts_respected(self):
        a = Block("combo", "套餐", 2000, 800)
        b = Block("child", "套餐子项", 1000, 500)
        from qionggui_solver import _add_conflict

        _add_conflict(a, b)
        plans = solve([a, b], 3000, top_k=3)
        for p in plans:
            names = {blk.name for blk, _ in p.blocks}
            self.assertFalse(
                "套餐" in names and "套餐子项" in names,
                msg=f"互斥被破坏: {names}",
            )

    def test_conflict_prefers_higher_kcal_branch(self):
        """互斥下应选热量更高的那条分支。"""
        a = Block("combo", "套餐", 2000, 800)
        b = Block("child", "套餐子项", 1000, 500)
        from qionggui_solver import _add_conflict

        _add_conflict(a, b)
        plans = solve([a, b], 2000, top_k=1)
        # 选套餐 800 kcal(¥20) 优于 子项 500 kcal(¥10)
        self.assertEqual(plans[0].total_kcal, 800)

    def test_empty_blocks_returns_empty(self):
        self.assertEqual(solve([], 2000), [])

    def test_budget_too_small_returns_empty(self):
        blocks = [Block("a", "A", 3000, 900)]
        self.assertEqual(solve(blocks, 2000), [])

    def test_all_zero_kcal_returns_empty(self):
        blocks = [Block("a", "A", 1000, 0), Block("b", "B", 500, 0)]
        self.assertEqual(solve(blocks, 2000), [])

    def test_zero_price_block_excluded_from_candidates(self):
        blocks = [Block("free", "免费", 0, 999999), Block("a", "A", 1000, 100)]
        plans = solve(blocks, 2000, top_k=1)
        self.assertEqual(plans[0].total_kcal, 100)

    def test_top_k_returns_distinct_plans(self):
        blocks = [
            Block("a", "A", 1000, 300),
            Block("b", "B", 1000, 250),
            Block("c", "C", 500, 200),
        ]
        plans = solve(blocks, 2000, top_k=3)
        keys = [tuple(sorted(blk.name for blk, _ in p.blocks)) for p in plans]
        self.assertEqual(len(keys), len(set(keys)), msg=f"存在重复方案: {keys}")
        self.assertLessEqual(len(plans), 3)

    def test_plans_sorted_by_kcal_desc(self):
        blocks = [
            Block("a", "A", 1000, 300),
            Block("b", "B", 1000, 250),
            Block("c", "C", 500, 200),
        ]
        plans = solve(blocks, 2000, top_k=3)
        kcal = [p.total_kcal for p in plans]
        self.assertEqual(kcal, sorted(kcal, reverse=True))

    def test_large_menu_completes_within_time_budget(self):
        """60 个候选块应在时间预算内完成，不得卡死。"""
        import random
        import time

        random.seed(7)
        blocks = [
            Block(f"b{i}", f"商品{i}", random.randint(300, 2500), random.randint(80, 900))
            for i in range(60)
        ]
        t0 = time.monotonic()
        plans = solve(blocks, 2000, top_k=3, time_budget_ms=15000)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 20.0)
        self.assertTrue(plans)


# ---------------------------------------------------------------------------
# 6. 报告渲染
# ---------------------------------------------------------------------------


class TestRendering(unittest.TestCase):
    def test_markdown_contains_key_fields(self):
        blocks = [Block("a", "巨无霸", 2200, 513), Block("b", "中薯条", 1300, 289)]
        plans = solve(blocks, 4000, top_k=1)
        md = plan_to_markdown(plans[0])
        self.assertIn("巨无霸", md)
        self.assertIn("¥35.00", md)
        self.assertIn("802 kcal", md)
        self.assertIn("kcal/元", md)

    def test_json_serializable(self):
        import json

        blocks = [Block("a", "巨无霸", 2200, 513)]
        plans = solve(blocks, 4000, top_k=1)
        payload = json.loads(plans[0].to_dict() and __import__("json").dumps(plans[0].to_dict(), ensure_ascii=False))
        self.assertEqual(payload["total_kcal"], 513)
        self.assertEqual(payload["items"][0]["name"], "巨无霸")

    def test_remaining_budget_correct(self):
        blocks = [Block("a", "巨无霸", 2200, 513)]
        plans = solve(blocks, 4000, top_k=1)
        self.assertEqual(plans[0].remaining_yuan, Decimal("18.00"))


# ---------------------------------------------------------------------------
# 7. 端到端：真实菜单形态
# ---------------------------------------------------------------------------


class TestEndToEnd(unittest.TestCase):
    def test_full_pipeline_under_20_yuan(self):
        nutrition = parse_nutrition(NUTRITION_SAMPLE)
        payload = _meals_payload(
            [
                {"code": "M1", "name": "巨无霸", "currentPrice": "22.00"},
                {"code": "M2", "name": "麦香鸡", "currentPrice": "15.50"},
                {"code": "M3", "name": "吉士汉堡包", "currentPrice": "11.00"},
                {"code": "M4", "name": "汉堡包", "currentPrice": "9.00"},
                {"code": "M5", "name": "中薯条", "currentPrice": "13.50"},
                {"code": "M6", "name": "可乐中杯", "currentPrice": "9.50"},
                {"code": "M7", "name": "麦乐鸡5块", "currentPrice": "13.00"},
                {"code": "M8", "name": "圆筒冰淇淋", "currentPrice": "4.00"},
                {"code": "M9", "name": "香芋派", "currentPrice": "8.00"},
                {"code": "M10", "name": "那么大鸡排", "currentPrice": "19.50"},
            ]
        )
        blocks, warnings = build_blocks(payload, nutrition)
        self.assertFalse(warnings, msg=f"不应有未匹配商品: {warnings}")

        plans = solve(blocks, 2000, top_k=3)
        self.assertTrue(plans)

        top = plans[0]
        self.assertLessEqual(top.total_price_fen, 2000)
        # 有真实营养数据的情况下，最优解热量必须 > 0
        self.assertGreater(top.total_kcal, 0)

        # 人工核对：¥20 以内的最大热量组合应能装配出 ≥ 500 kcal
        self.assertGreaterEqual(
            top.total_kcal,
            500,
            msg=f"最优解热量偏低，疑似漏解：{top.to_dict()}",
        )

        md = plan_to_markdown(top)
        self.assertIn("kcal/元", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)

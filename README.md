# 穷鬼麦饱饱 🍔

> **20 块钱，在麦当劳吃到最饱。**
> 用实时菜单数据求解「预算内热量最大化」的套餐组合，让每一分钱都换成最实在的饱腹感。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-mcd--mcp-red.svg)](https://github.com/M-China/mcd-mcp-server)

---

## 这是什么

**穷鬼麦饱饱**是一个基于麦当劳 MCP 的 Skill。

它回答一个很具体的问题：

> 「我只有 20 块钱，怎么在麦当劳吃得最饱？」

不是推荐「最便宜的」，也不是推荐「看起来最多的」，
而是用**分支限界算法**在预算硬约束下求**总热量最大**的组合，
并且给出一份**可以直接下单**的商品清单。

## 效果示例

```
> 我只有 20 块，想吃最饱的

## 穷鬼麦饱饱 · 你的 ¥20 最优解

**¥20.00 吃下 542 kcal，热量效率 27.10 kcal/元** —— 本店 20 元档顶配。

| 商品 | 数量 | 单价 | 热量 |
| --- | ---: | ---: | ---: |
| 吉士汉堡包 | ×1 | ¥11.00 | 294 kcal |
| 汉堡包     | ×1 | ¥9.00  | 248 kcal |
| **合计**   |    | **¥20.00** | **542 kcal** |

**为什么这么搭**
- 吉士汉堡包热量密度 26.7 kcal/元，同价位最扛饿；
- 不配可乐 —— 中可 ¥9.5 只换 147 kcal，
  同样的钱买汉堡包能换 248 kcal，差 68%。

**备选方案**
- 想有甜点：香芋派 + 小薯条 + 圆筒冰淇淋，¥20.00 / 535 kcal
- 想省着点：吉士汉堡包 + 香芋派，¥19.00 / 526 kcal
```

## 核心洞察

**热量密度 = 千卡 ÷ 元**，这才是穷鬼套餐的真正指标。

用真实数据算一下，结论相当反直觉：

| 商品 | 价格 | 热量 | 热量密度 |
| --- | ---: | ---: | ---: |
| 香芋派 | ¥8.00 | 232 kcal | **29.0 kcal/元** ⭐ |
| 汉堡包 | ¥9.00 | 248 kcal | **27.6 kcal/元** ⭐ |
| 巨无霸 | ¥22.00 | 513 kcal | 23.3 kcal/元 |
| 圆筒冰淇淋 | ¥4.00 | 93 kcal | 23.3 kcal/元 |
| 可乐中杯 | ¥9.50 | 147 kcal | 15.5 kcal/元 ⚠️ |

**直观点单最容易踩的坑就是可乐。**
它是全菜单里热量性价比最低的品类之一，
而算法会毫不犹豫地把它从你的 20 元里踢出去，换成汉堡包。

> 无糖可乐更极端：0 kcal，纯花钱买液体。

## 快速开始

### 前置条件

1. 在 [麦当劳 MCP 控制台](https://mcp.mcd.cn) 申请 MCP Token
2. 在 WorkBuddy 中配置 MCP 连接器

### 第 1 步：配置 MCP

打开 WorkBuddy → 左侧【专家·技能·连接器】→【连接器】页签
→ 右上角【自定义连接器】→【配置 MCP】，填入：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN"
      }
    }
  }
}
```

> ⚠️ 把 `YOUR_MCP_TOKEN` 换成你自己的 Token。
> 仓库里的 `mcp-config.example.json` 用的是 `${MCD_MCP_TOKEN}`
> 环境变量占位符形式，不会泄露任何凭证。

保存后回到【自定义连接器】，把 `mcd-mcp` 启用。

### 第 2 步：安装 Skill

把本仓库的 `skills/qionggui-mai-baobao/` 目录复制到：

```
~/.workbuddy/skills/qionggui-mai-baobao/
```

（Windows: `C:\Users\<你的用户名>\.workbuddy\skills\qionggui-mai-baobao\`）

### 第 3 步：开始对话

在 WorkBuddy 里直接说：

```
30元以内 帮我点一份最扛饿的麦当劳
```

或

```
我只有20块，人在杭州，想吃热量最高的穷鬼套餐
```

## 使用示例

### 示例 1：基础用法

```
> 20 块吃饱麦当劳

[Skill 自动执行]
1. 询问门店 / 位置
2. query-nearby-stores  → 拿到 storeCode
3. query-meals          → 实时菜单与价格
4. list-nutrition-foods → 热量表
5. 本地求解 → 输出最优组合
```

### 示例 2：指定预算与约束

```
> 25 块，不要辣，想有肉

[Skill 会]
- 把预算调到 2500 分
- 过滤掉含"麦辣"的候选
- 保证方案里至少有一个汉堡类主品
```

### 示例 3：只用命令行（不依赖 WorkBuddy）

```bash
# 拉取数据后手动运行
python skills/qionggui-mai-baobao/scripts/qionggui_solver.py \
    --meals     examples/sample-meals.json \
    --nutrition examples/sample-nutrition.txt \
    --budget    20 \
    --top-k     3 \
    --format    markdown
```

输出还可以是 JSON（便于二次开发）或 CSV（便于做表格）：

```bash
python ... --format json --out result.json
python ... --format csv  --out result.csv
```

## 项目结构

```
qionggui-mai-baobao/
├── README.md                    # 本文件
├── CONTEST_DECLARATION.md       # 参赛声明（官方原文，未改动）
├── MCP_INTEGRATION.md           # MCP 集成说明（Tool / 流程 / 业务价值）
├── mcp-config.example.json      # 脱敏 MCP 配置示例
├── LICENSE                      # MIT
├── .gitignore
│
├── skills/qionggui-mai-baobao/  # Skill 本体
│   ├── SKILL.md                 # Skill 主入口（工作流程与输出模板）
│   ├── scripts/
│   │   └── qionggui_solver.py   # 核心求解器（约 700 行，含完整注释）
│   └── references/
│       ├── algorithm.md         # 算法详解：为什么用分支限界
│       ├── nutrition-mapping.md # 菜单名 ↔ 营养表名 对照
│       └── mcp-tools.md         # MCP 工具参数速查
│
├── tests/
│   └── test_solver.py           # 41 个单元测试
│
├── examples/
│   ├── sample-meals.json        # 菜单样例（演示用）
│   └── sample-nutrition.txt     # 营养表样例（演示用）
│
└── docs/
    └── DEMO.md                  # 完整演示记录
```

## 技术亮点

### 1. 解决「套餐嵌套」导致的伪最优解

麦当劳菜单里，同一个汉堡既能单点也能出现在套餐中。
如果求解器把套餐拆成子项再和单品重复组合，会算出**现实中买不到的组合**。

本项目用 **候选块（Block）+ 互斥剪枝** 解决：

- 套餐作为**原子块**，永不拆分
- 套餐子项与套餐整体建立**双向互斥标记**
- 求解时一次性检查互斥约束

详见 [`references/algorithm.md`](skills/qionggui-mai-baobao/references/algorithm.md)。

### 2. 分支限界 + 分数背包松弛上界

`2^150` 的枚举空间是不可行的。本项目用**按热量密度降序 + 分数背包
松弛上界**做剪枝，实测 60 个候选块在**毫秒级**完成求解。

核心上界函数：

```python
def upper_bound(i, remain, cur_kcal):
    """按热量密度降序装填的分数背包松弛 —— 保证高估不漏解。"""
    ub, rem = float(cur_kcal), float(remain)
    for j in range(i, n):
        if cands[j].price_fen <= rem:
            ub += cands[j].kcal
            rem -= cands[j].price_fen
        else:
            ub += cands[j].kcal * (rem / cands[j].price_fen)
            break
    return ub
```

### 3. 正确性有证据

`tests/test_solver.py` 里有一个关键测试：

```python
def test_matches_brute_force_random_small(self):
    """随机 60 组数据，把分支限界的结果与暴力枚举对照。"""
```

分支限界的输出与暴力枚举**完全一致**，证明剪枝没有丢解。

### 4. 三级名称匹配

菜单名与营养表名并非一一对应（如「板烧鸡腿堡」vs「原味板烧鸡腿麦香鸡」）。
本项目用 `exact → alias → 双向包含（取最相近）` 三级匹配，
命中率从约 70% 提到 95%+。

### 5. 数据缺失绝不编造

营养表里查不到的商品，热量按 **0** 计并在输出中显式告警，
而不是用估算值污染最优解。这是刻意的保守设计。

## 运行测试

```bash
python tests/test_solver.py
```

预期输出：

```
Ran 41 tests in 0.018s

OK
```

测试覆盖：营养表解析、名称匹配、价格单位换算、套餐识别与互斥、
求解正确性（与暴力枚举对照）、预算约束、边界情况（空菜单 / 预算过小 /
全 0 热量）、报告渲染。

## 目标用户

| 用户 | 场景 |
| --- | --- |
| **学生党 / 刚工作的年轻人** | 月底预算紧张，想吃顿实在的 |
| **外卖重度用户** | 每天纠结「吃什么最划算」，想省决策时间 |
| **健身 / 增肌人群** | 需要精确的热量摄入，还要控预算 |
| **麦当劳常客** | 想知道自己的固定搭配是不是真的最划算 |
| **算法爱好者** | 想看一个真实场景下的背包问题工程实现 |

## 适用边界

- 本 Skill **只做信息聚合与组合计算**，价格以门店实际结账为准
- **不构成营养或医疗建议**
- 不鼓励暴饮暴食，方案默认每种商品最多一份（`--max-per-item=1`）
- 热量数据来自麦当劳官方营养表，仅供参考

## 常见问题

**Q：为什么推荐里经常没有饮料？**
A：因为饮料热量密度低（可乐 15.5 kcal/元，无糖可乐 0 kcal/元）。
在「吃饱」这个目标下，算法会把钱优先分配给高密度商品。
如果你就是想喝可乐，可以直接说「要一杯可乐」，Skill 会把它作为
固定项加入后再优化剩余预算。

**Q：为什么结果和我在店里看到的价格不一样？**
A：求解器算的是菜单挂牌价。会员卡、券会改变实际价格。
Skill 会用 `calculate-price` 复核券后价，若你告知有券，它会重新计算。

**Q：营养表里没有的商品怎么办？**
A：按 0 千卡处理并在输出里告警。这是为了避免编造数值误导决策。
如果你发现常用商品长期未收录，欢迎在 Issue 里提出。

---

## 参与活动

本项目为**麦当劳程序员节创意开发大赛**参赛作品，
使用 [WorkBuddy](https://www.workbuddy.cn/) 开发。

## 许可

[MIT](LICENSE)

---

> ⚠️ 本项目为参赛作品，由参赛者独立开发，**非麦当劳官方产品**。
> 项目输出仅供参考，不构成医疗、营养或其他专业建议；
> 餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。

# WorkBuddy 开发上下文

> 本文件记录「穷鬼麦饱饱」使用腾讯 WorkBuddy 开发的对话上下文，
> 用于核验是否符合 WorkBuddy 专项奖励（3000 积分）的联动条件。

## 项目信息

| 项 | 值 |
| --- | --- |
| 项目名称 | 穷鬼麦饱饱 |
| 仓库地址 | https://github.com/zhuyaguang/qionggui-mai-baobao |
| 开发工具 | 腾讯 WorkBuddy |
| 开发时间 | 2026年10月10日 |
| 参赛活动 | 麦当劳程序员节创意开发大赛 |

## 开发过程

### 第 1 轮：需求确认与项目命名

**用户诉求**

> 这是一个麦当劳 MCP 比赛，目前麦当劳的 MCP server 我已经安装好了。
> 我想创建一个这样的 skill：20 元吃饱麦当劳的穷鬼套餐。
> 给用户推荐热量最多、不超过 20 元的麦当劳套餐。

**WorkBuddy 响应**

1. 抓取并解析活动仓库 README 与 activityGuidelines.md，
   提取出**报名所需的全部硬性要求**：

   | 文件 | 要求 |
   | --- | --- |
   | `README.md` | 必须，文件名不可改动 |
   | `CONTEST_DECLARATION.md` | 必须，**文件名及内容均不可改动** |
   | `MCP_INTEGRATION.md` | 必须，说明 MCP Server / Tool / 流程 / 业务价值 |
   | 源代码 | 必须，形式不限 |
   | `workbuddy.md` | 非必须，参加 WorkBuddy 专项奖励时必须 |
   | `mcp-config.example.json` | 必须（activityGuidelines 中列出），仅环境变量占位符 |

2. 探测已安装的 `mcd-mcp` 工具，确认可用能力边界：

   - `query-nearby-stores` / `query-meals` / `list-nutrition-foods`
   - `calculate-price` / `available-coupons` / `now-time-info`

3. 实调 `list-nutrition-foods`，拿到 **160 条真实营养数据**，
   验证了千卡字段（`energyKcal`，第 4 列）可用。

4. 提供 4 个项目名候选，用户选定「**穷鬼麦饱饱**」。

### 第 2 轮：技术方案设计

**WorkBuddy 识别出的核心难点**

「预算内热量最大」表面是 0/1 背包问题，但麦当劳菜单存在
**套餐嵌套单品**的结构，直接套用经典背包会产生**伪最优解**：

```
超值套餐（含巨无霸 + 中薯 + 中可）
├── 巨无霸   也能单点
├── 中薯条   也能单点
└── 可乐中杯 也能单点
```

若把套餐拆成子项放进背包，求解器会算出「套餐 + 套餐内单品」
这种现实中不存在的组合，或者把套餐里的巨无霸当成免费赠送。

**解决方案**

设计**候选块（Block）+ 互斥剪枝**模型：

1. 套餐作为**原子块**，永不拆分
2. 套餐子项与套餐整体建立**双向互斥标记**（`Block.conflicts`）
3. 求解时用 `all(c not in chosen for c in conflicts_idx[i])` 一次性检查

### 第 3 轮：编码实现

**产出 `skills/qionggui-mai-baobao/scripts/qionggui_solver.py`**

核心组件：

| 组件 | 职责 |
| --- | --- |
| `normalize_name()` | 名称归一化（全角转半角、去括号、去空白） |
| `parse_nutrition()` | 解析 MCP 返回的类 CSV 营养文本 |
| `lookup_kcal()` | 三级匹配：exact → alias → 双向包含 |
| `build_blocks()` | 菜单 JSON → 候选块 + 互斥关系 |
| `_combo_kcal()` | 套餐热量三级归属（整名 / 子项求和 / 名称启发） |
| `solve()` | 分支限界 0/1 背包 + 时间预算保护 |
| `plan_to_markdown/json` | 三种输出格式渲染 |

**算法要点**

- 按热量密度 `k_i / p_i` 降序排序，保证松弛上界单调
- DFS 分支限界，`upper_bound()` 用分数背包松弛做紧上界
- 每 4096 次迭代检查 deadline，超时返回当前最优解（**永不卡死**）

### 第 4 轮：测试与缺陷修复

**产出 `tests/test_solver.py`，共 41 个测试**

首次运行结果：**38 通过 / 2 失败**。WorkBuddy 定位到两个真实缺陷：

#### 缺陷 1：`normalize_name` 里的异写规则导致别名失效

```python
# 错误代码
for a, b in (("麦辣鸡腿堡", "麦辣鸡腿汉堡"), ...):
    s = s.replace(a, b)
```

**根因**：这条 replace 规则让「麦辣鸡腿堡」在归一化阶段就被改写成
「麦辣鸡腿汉堡」，于是查表时永远走 exact，`NUTRITION_ALIASES` 里的
别名映射**永远无法触发**——死代码。

**修复**：删除 `normalize_name` 中的所有异写替换，
把同义映射**统一收敛到 `NUTRITION_ALIASES` 一处**。

#### 缺陷 2：别名查表逻辑的 key 不匹配

```python
# 错误代码
alias = NUTRITION_ALIASES.get(name) or NUTRITION_ALIASES.get(key)
```

**根因**：`key` 已经过归一化（去括号、去空白、转小写），
而 `NUTRITION_ALIASES` 的键是**未归一化的原始中文**，
两者永远匹配不上。

**修复**：改为遍历别名表，把**两边的键都归一化后比较**：

```python
for src, dst in NUTRITION_ALIASES.items():
    if normalize_name(src) == key:
        dst_key = normalize_name(dst)
        if dst_key in table:
            return table[dst_key], "alias"
```

#### 修复后

```
Ran 41 tests in 0.018s

OK
```

**41/41 全部通过。**

### 第 5 轮：端到端验证

用示例数据实跑，验证 README 中所有示例数字：

```bash
python skills/qionggui-mai-baobao/scripts/qionggui_solver.py \
    --meals examples/sample-meals.json \
    --nutrition examples/sample-nutrition.txt \
    --budget 20 --top-k 3
```

**输出**：¥20.00 / 542 kcal / 27.10 kcal/元（吉士汉堡包 + 汉堡包）

与 README 中写明的示例**完全一致**。

### 第 6 轮：文档撰写

产出完整文档体系：

- `README.md` —— 项目介绍、安装、示例、目标用户
- `MCP_INTEGRATION.md` —— MCP 集成说明（6 个 Tool 的用途与调用链）
- `skills/.../SKILL.md` —— Skill 主入口，含五步工作流程与输出模板
- `references/algorithm.md` —— 算法详解
- `references/nutrition-mapping.md` —— 名称对照与三级匹配规则
- `references/mcp-tools.md` —— MCP 工具参数速查
- `docs/DEMO.md` —— 完整演示记录与验证证据

## WorkBuddy 发挥的关键作用

| 环节 | WorkBuddy 的贡献 |
| --- | --- |
| **需求解析** | 自动抓取活动仓库规则，提取出 6 项必交文件清单，避免报名失败 |
| **能力探测** | 实调 MCP 工具确认返回结构，发现营养表是**纯文本类 CSV** 而非 JSON（关键实现细节） |
| **架构设计** | 识别出「套餐嵌套」导致的伪最优解陷阱，设计 Block + 互斥模型 |
| **算法选择** | 从朴素枚举（2^150 不可行）切换到分支限界 + 分数背包松弛 |
| **缺陷发现** | 测试暴露 2 个真实代码缺陷（死代码 + key 不匹配），并完成根因定位与修复 |
| **文档产出** | 一次性生成 README / MCP_INTEGRATION / SKILL / 3 份 references / DEMO |

## 技术栈

| 项 | 说明 |
| --- | --- |
| 语言 | Python 3.9+（**零第三方依赖**，仅标准库） |
| MCP | 麦当劳 `mcd-mcp`（streamablehttp） |
| 算法 | 分支限界 0/1 背包 + 分数背包松弛上界 |
| 测试 | `unittest`，41 个用例 |
| 输出 | Markdown / JSON / CSV |

## 声明

本项目使用腾讯 WorkBuddy 完成需求分析、架构设计、代码编写、
缺陷修复与文档撰写。日常对话上下文如上。

我把与WorkBuddy  对话连接分享出来

【WorkBuddy】开发麦当劳20元穷鬼套餐MCP技能
https://workbuddy.link/p/iePO34GOeVDhp1gGZJxz5Y?ext2=copy_link

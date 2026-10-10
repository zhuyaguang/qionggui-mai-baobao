# 麦当劳 MCP 工具速查

本 Skill 实际调用以下 `mcd-mcp` 工具。所有参数说明以 MCP 返回的
工具 schema 为准，本文档为使用速查。

## 1. query-nearby-stores

**用途**：到店场景下查询可点餐门店。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `searchType` | 是 | `2`=按位置搜索，`1`=搜索收藏餐厅（默认） |
| `city` | `searchType=2` 时必填 | 城市名 |
| `keyword` | `searchType=2` 时必填 | 位置关键词 |
| `beType` | 是 | `1`=到店自取，`5`=得来速 |

**返回**：`storeCode`（必用）；`beType=5` 时还有 `beCode`（必传）。

---

## 2. query-meals

**用途**：获取门店完整菜单与**实时价格**。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `storeCode` | 是 | 门店编码 |
| `orderType` | 是 | `1`=到店，`2`=外送 |
| `beType` | 是 | `1`/`2`/`5`/`6` |
| `beCode` | 视场景 | 到店自取**不传**；得来速/外送/团餐**必传** |
| `reservationDate` | 预约场景 | 格式 `yyyy-MM-dd HH:mm` |

**返回结构**：

```
data.categories[].meals[].code        → 餐品编码与分类
data.meals.{code}.name                → 餐品名称
data.meals.{code}.currentPrice        → 现价（销售价）
data.meals.{code}.originalPrice       → 原价（划线价）
data.meals.{code}.discountType        → 优惠类型（null 为无优惠）
data.meals.{code}.withOrder           → 随单购信息
data.frequent.{code}                  → 常点餐品
```

**错误码**：`600057` = 门店可能已关闭或不在营业时间。

> ⚠️ 价格单位：MCP 返回的 `currentPrice` 是**字符串形式的元**（如 `"13.50"`）。
> 求解器的 `_to_fen()` 兼容「元」与「分」两种输入，通过量级启发式判断。

---

## 3. list-nutrition-foods

**用途**：获取全量营养数据（能量、蛋白质、脂肪、碳水、钠、钙）。

**参数**：无。

**返回**：一个**类 CSV 的纯文本字符串**，不是 JSON。格式：

```
[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
  猪柳麦满分,null,1288,308,16,16,24,781,213
  中薯条,null,1210,289,4,12,38,165,18
  巨无霸,null,2146,513,27,26,42,961,171
```

列含义：

| 列号 | 字段 | 含义 |
| ---: | --- | --- |
| 1 | productName | 餐品名 |
| 2 | nutritionDescription | 营养描述（多为 null） |
| 3 | energyKj | 能量（千焦） |
| 4 | **energyKcal** | **能量（千卡）← 本 Skill 用这一列** |
| 5 | protein | 蛋白质（克） |
| 6 | fat | 脂肪（克） |
| 7 | carbohydrate | 碳水化合物（克） |
| 8 | sodium | 钠（毫克） |
| 9 | calcium | 钙（毫克） |

> ⚠️ 取第 **4** 列（`energyKcal`），不要取第 3 列（`energyKj`）。
> 千焦转千卡需除以 4.184，直接用错列会让数值虚高 4 倍。

---

## 4. calculate-price

**用途**：计算**含优惠**的实际价格。求解器算的是挂牌价，
下单前必须用本工具复核。

| 参数 | 说明 |
| --- | --- |
| `storeCode` / `orderType` / `beType` | 同 `query-meals` |
| `items[].productCode` | 商品编码（来自 `query-meals`） |
| `items[].quantity` | 数量，≥1 |
| `items[].couponId` / `couponCode` | 选填，用券时传入 |
| `items[].modification` | 特制选项（来自 `query-meal-detail`） |
| `needTableware` | 是否要餐具 |

**返回**：价格字段单位为**分**，展示时需除以 100 转元。

**特制选项的 key 规则**（易错）：

- 用户**选中**的特调项：`key = selectedKey`
- 用户**未选中**的项目：若其 `unselectedKey` 非空，`key = unselectedKey`，**也必须传入**
- 即：含 `unselectedKey` 的特调组，组内所有项都要传

---

## 5. available-coupons

**用途**：查询用户可领取的优惠券。

**参数**：无。

**返回**：券名称、图片、状态、促销标签。

**用法**：在求解出方案后，用本工具检查是否有可用券，
若有则把 `couponId` 传给 `calculate-price` 重新计算券后价。

---

## 6. now-time-info

**用途**：获取服务器当前时间（毫秒时间戳、格式化日期、时区）。

**何时需要**：

- 查询活动日历、判断「今天」是星期几
- 预约场景构造 `reservationDate`（格式 `yyyy-MM-dd HH:mm`）

> ⚠️ 不要在代码里硬编码日期或自己计算时间戳。

---

## 参数传递规则速查（最容易出错的地方）

| beType | 就餐方式 | orderType | beCode |
| ---: | --- | ---: | --- |
| 1 | 到店自取 | 1 | **不传** |
| 5 | 得来速 | 1 | **必传**（query-nearby-stores） |
| 2 | 麦乐送 | 2 | **必传**（delivery-query-stores） |
| 6 | 企业团餐 | 2 | **必传**（delivery-query-stores） |

记法：**只有到店自取不传 beCode**，其余三种都必须传。

---

## 完整的调用链

```
query-nearby-stores  →  storeCode
        ↓
query-meals          →  菜单 + 实时价格  ┐
list-nutrition-foods →  全量热量表        ├→ 求解器 → 最优组合
                                         ┘
        ↓
calculate-price      →  券后真实价格
        ↓
create-order         →  下单（需用户确认）
```

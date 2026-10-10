# 发布到 SkillHub 指南

> 穷鬼麦饱饱已**通过 SkillHub 本地预检**，只差账号认证这一步。
> 本文档是完整的发布操作指引。

## 当前状态

```
$ skillhub publish skills/qionggui-mai-baobao --dry-run
✓ Dry-run passed: qionggui-mai-baobao@1.0.0
```

| 检查项 | 状态 |
| --- | --- |
| SKILL.md 元数据完整性 | ✅ 通过 |
| 目录结构规范 | ✅ 通过 |
| 打包预检 | ✅ 通过 |
| 账号认证 | ❌ **需要你本人操作** |

## 为什么需要你本人操作

SkillHub 规定：**发布 Skill 必须完成实名认证**（腾讯云人脸核身）。
认证信息加密存储，仅用于身份核实。这一步无法由工具代劳。

---

## 发布步骤

### 第 1 步：注册并实名认证

1. 访问 https://skillhub.cn
2. 点击右上角【登录】完成注册
3. 进入个人中心完成**实名认证**（人脸核身）

### 第 2 步：获取 API Token

在个人中心找到 **API Token**（格式为 `skh_` 开头）。

### 第 3 步：CLI 登录

```bash
skillhub login --key skh_你的Token
```

验证登录成功：

```bash
skillhub auth whoami
```

### 第 4 步：发布

```bash
cd D:/qionggui-mai-baobao
skillhub publish skills/qionggui-mai-baobao \
    --changelog "首个版本：20 元预算内求解热量最大的麦当劳套餐组合"
```

### 第 5 步：等待审核

- 提交后触发**三线并行安全审核**：
  1. 内容合规过滤
  2. 科恩实验室深度漏洞扫描
  3. 云鼎实验室 AI 模型安全评估

- 全部通过后**自动上架**

---

## 备选方案：网页发布

不想用命令行的话，也可以走官网：

1. 登录 https://skillhub.cn
2. 进入 https://skillhub.cn/dashboard/publish
3. 上传 `skills/qionggui-mai-baobao` 目录（或先打包为 zip）
4. 填写元信息（页面提供 AI 辅助生成）
5. 提交审核

> 打包 zip 命令：
> ```bash
> cd skills && zip -r ../qionggui-mai-baobao.zip qionggui-mai-baobao
> ```

---

## 已完成的元数据

`skills/qionggui-mai-baobao/SKILL.md` 的 frontmatter：

```yaml
---
name: qionggui-mai-baobao
slug: qionggui-mai-baobao
displayName: 穷鬼麦饱饱
description: >-
  穷鬼麦饱饱 —— 20 元吃饱麦当劳的穷鬼套餐推荐官……
version: 1.0.0
category: 生活服务
platforms:
  - workbuddy
tags:
  - 麦当劳
  - 省钱
  - 套餐推荐
  - 热量管理
  - 组合优化
  - MCP
license: MIT
---
```

## 审核要点自查

SkillHub 的安全审核重点关注以下维度，本项目均已满足：

| 审核维度 | 本项目情况 |
| --- | --- |
| 供应链风险 | 零第三方依赖，仅用 Python 标准库 |
| 命令执行风险 | 不执行任何系统命令 |
| 网络请求与数据外传 | 代码本身不发网络请求；数据获取由 MCP 完成 |
| 文件操作与敏感路径 | 只读写用户显式指定的输入输出文件 |
| Prompt 注入风险 | 无动态指令拼接 |
| 远程脚本执行 | 无 |
| 可疑编码/混淆 | 全部代码带完整中文注释，无混淆 |
| 敏感信息 | 配置文件仅用 `${MCD_MCP_TOKEN}` 占位符，无私钥 |

## TRACE 评测参考

SkillHub 从五个维度评估技能质量，本项目对应情况：

| 维度 | 本项目 |
| --- | --- |
| **T** 可信任度 | 零依赖、无网络请求、无敏感信息、全中文 |
| **R** 可靠性 | 41 个单元测试；与暴力枚举对照验证；超时保护永不卡死 |
| **A** 适用性 | SKILL.md 明确列出 11 个触发词与依赖的前置条件 |
| **C** 规范性 | SKILL.md + 3 份 references 渐进式披露，示例充分 |
| **E** 有效性 | 输出可直接下单的商品清单，附 productCode |

---

## 常见问题

**Q：发布失败怎么办？**

运行 `skillhub publish` 时会返回具体错误。常见原因：

- 未登录或 Token 过期 → `skillhub login --key skh_xxx` 重新登录
- SKILL.md 格式错误 → 先跑 `--dry-run` 本地预检
- 缺少必需字段 → 检查 `name` / `slug` / `displayName` / `description` / `version`

**Q：可以发私有版本吗？**

可以。CLI 支持 `--visibility` 参数（`public` / `unlisted` / `private` / `org`）。

**Q：发布后还能改吗？**

可以。修改 SKILL.md 后递增 `version`，重新 `skillhub publish` 即可。
建议每次改动都递增版本号。

---

## 与本项目的其他发布渠道的关系

| 渠道 | 目的 | 状态 |
| --- | --- | --- |
| **GitHub** | 参赛作品提交（活动要求） | ✅ 已推送 |
| **SkillHub** | 让 WorkBuddy 用户能搜到并安装 | ⏳ 待你认证后发布 |

两个渠道互不冲突：GitHub 是参赛必需的公开仓库，
SkillHub 是让技能真正被用户使用的分发渠道。

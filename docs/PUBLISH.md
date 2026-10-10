# 发布到 SkillHub 指南

> **当前状态：已成功提交发布，等待平台审核。**

## 发布记录

| 项 | 值 |
| --- | --- |
| 发布时间 | 2026-10-10 17:05 |
| 技能标识 | `qionggui-mai-baobao@1.0.0` |
| Platform skillId | `274491` |
| 发布者 | `@user_33148e32`（userId=788025） |
| 审核状态 | ⏳ 审核中（官方说明 1–3 个工作日） |

发布命令与结果：

```bash
$ skillhub publish skills/qionggui-mai-baobao \
    --changelog "首个版本：在 20 元预算硬约束内，用实时菜单数据求解总热量最大的麦当劳套餐组合"
✓ Published: skillId=274491 status=None
```

## 审核流水线

提交后自动触发**三线并行安全审核**，全部通过才会上架：

1. 内容合规过滤
2. 科恩实验室深度漏洞扫描
3. 云鼎实验室 AI 模型安全评估

审核查询命令：

```bash
skillhub skill reports qionggui-mai-baobao --namespace user_33148e32
skillhub skill evaluation qionggui-mai-baobao --namespace user_33148e32 --json
```

> 当前 `reports` 返回 `{}`（空对象）——说明报告中转已建立、
> 审核尚未产出结论，属于**正常等待状态**。

审核通过后，技能会出现在 https://skillhub.cn/skills/qionggui-mai-baobao
并可在 WorkBuddy 技能入口搜索到。

---

## 本地使用（已可用）

技能已同步安装到本机，**无需等审核即可在 WorkBuddy 中使用**：

```
~/.workbuddy/skills/qionggui-mai-baobao/
├── SKILL.md
├── scripts/qionggui_solver.py
└── references/{algorithm,nutrition-mapping,mcp-tools}.md
```

直接在对话里说「20 元吃饱麦当劳」即可触发。

---

## 后续版本更新

修改 SKILL.md 后递增 `version`，重新发布：

```bash
# 1. 改 SKILL.md 里的 version（如 1.0.1）
# 2. 重新发布
skillhub publish skills/qionggui-mai-baobao \
    --changelog "本次改了什么"
```

> 建议每次改动都递增版本号，便于平台做版本追溯与回滚。

---

## 原始操作指引（已完成，留档）

### 第 1 步：注册并实名认证

1. 访问 https://skillhub.cn
2. 点击右上角【登录】完成注册
3. 进入个人中心完成**实名认证**（人脸核身）

### 第 2 步：获取 API Token

在个人中心找到 **API Token**（格式为 `skh_` 开头）。

### 第 3 步：CLI 登录

```bash
skillhub login --key skh_你的Token
skillhub auth whoami   # 验证
```

### 第 4 步：发布

```bash
cd D:/qionggui-mai-baobao
skillhub publish skills/qionggui-mai-baobao --changelog "..."
```

### 第 5 步：等待审核

见上文「审核流水线」。

---

## 备选方案：网页发布

1. 登录 https://skillhub.cn
2. 进入 https://skillhub.cn/dashboard/publish
3. 上传 `skills/qionggui-mai-baobao` 目录（或先打包为 zip）
4. 填写元信息（页面提供 AI 辅助生成）
5. 提交审核

> 打包 zip：
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

> ⚠️ 字段名是**驼峰** `displayName`，不是 `display_name`。
> 写成下划线形式会在预检时报「缺少 displayName」。

## 审核要点自查

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

## TRACE 评测对照

| 维度 | 本项目 |
| --- | --- |
| **T** 可信任度 | 零依赖、无网络请求、无敏感信息、全中文 |
| **R** 可靠性 | 41 个单元测试；与暴力枚举对照验证；超时保护永不卡死 |
| **A** 适用性 | SKILL.md 明确列出 11 个触发词与依赖的前置条件 |
| **C** 规范性 | SKILL.md + 3 份 references 渐进式披露，示例充分 |
| **E** 有效性 | 输出可直接下单的商品清单，附 productCode |

---

## 安装 SkillHub CLI（Windows 踩坑记录）

Windows + Git Bash 环境下安装有三个连环坑，均已解决：

### 坑 1：证书吊销检查离线

```
curl: (35) schannel: next InitializeSecurityContext failed:
CRYPT_E_REVOCATION_OFFLINE (0x80092013)
```

**解决**：
- git 用 `git config http.sslBackend openssl`
- curl 加 `--ssl-no-revoke`

### 坑 2：tar 把 `C:\` 当远程主机

```
tar: Cannot connect to C: resolve failed
```

**解决**：`tar --force-local`，或设 `TMPDIR=/tmp` 用 Unix 风格路径。

### 坑 3：包装脚本传参被二次转义

用 bash 包一层 tar 反而引入 `C\:\\Users\...` 转义问题。

**最终有效方案**：

```bash
# 只包装 curl（不包装 tar），并设 TMPDIR
mkdir -p /tmp/shbin
cat > /tmp/shbin/curl << 'EOF'
#!/usr/bin/env bash
exec /c/WINDOWS/system32/curl.exe "$@" --ssl-no-revoke
EOF
chmod +x /tmp/shbin/curl

export TMPDIR=/tmp
export PATH=/tmp/shbin:$PATH
bash install.sh --cli-only
```

安装位置：`~/.local/bin/skillhub`（版本 2026.8.5）

---

## 常见问题

**Q：发布失败怎么办？**

常见原因：
- 未登录或 Token 过期 → `skillhub login --key skh_xxx` 重新登录
- SKILL.md 格式错误 → 先跑 `--dry-run` 本地预检
- 缺少必需字段 → 检查 `name` / `slug` / `displayName` / `description` / `version`

**Q：可以发私有版本吗？**

可以。CLI 支持 `--visibility` 参数（`public` / `unlisted` / `private` / `org`）。

**Q：审核要多久？**

官方说明 1–3 个工作日。

---

## 与本项目其他发布渠道的关系

| 渠道 | 目的 | 状态 |
| --- | --- | --- |
| **GitHub** | 参赛作品提交（活动要求） | ✅ 已推送 |
| **SkillHub** | 让 WorkBuddy 用户能搜到并安装 | ⏳ 已提交，审核中 |
| **本地技能目录** | 自己立刻可用 | ✅ 已安装 |

三个渠道互不冲突：GitHub 是参赛必需的公开仓库，
SkillHub 是面向全网用户的分发渠道，本地目录让你自己马上能用。

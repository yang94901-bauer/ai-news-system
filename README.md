# ai-news-system

AI 新闻聚合站（静态可部署版本），接入 8 类来源并生成自动总结：

1. OpenAI Blog
2. Anthropic News
3. GitHub Trending AI
4. Product Hunt AI
5. AI Startup Funding
6. YouTube AI 频道
7. X/Twitter AI KOL

自动总结包含：
- 发生了什么
- 为什么重要
- 普通人机会在哪

## 本地预览

```bash
python3 -m http.server 8000
```

打开 `http://localhost:8000`。

## QQ 邮箱管理插件（新）

已新增 `qq_mail_assistant.py`，支持：

1. 自动读取新邮件内容（主题 + 正文摘要）
2. 以通知方式提醒（默认打印，可配置系统通知命令）
3. 自动过滤低价值邮件（发件人、主题关键词、高价值关键词白名单）

### 快速开始

```bash
cp config.example.json config.json
# 编辑 config.json，填入 QQ 邮箱地址 + IMAP 授权码
python3 qq_mail_assistant.py
```

### 你需要提供的信息

- QQ 邮箱地址（如 `123456@qq.com`）
- QQ 邮箱 IMAP 授权码（不是登录密码）
- 你希望过滤的关键词/发件人（可选）
- 你想保留的高价值邮件关键词（可选）

> 安全建议：不要把 `config.json` 提交到代码仓库。

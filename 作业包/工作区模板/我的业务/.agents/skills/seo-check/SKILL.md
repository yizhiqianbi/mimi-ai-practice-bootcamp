---
name: seo-check
description: 按 SEO 上线前 8 项检查 site/ 网站，逐项写通过或不通过，不通过的直接修改，并补齐 robots.txt、sitemap.xml、llms.txt 和 JSON-LD。作业四 C 步用。
---

# SEO 8 项自查与修复

## 输入

- `site/`
- `业务卡片.md`、`知识库/FAQ素材.md`
- 正式网址：____（还没部署就先用 `https://example.com` 占位，部署后全局替换）

## 8 项

1. 独立的 `<title>` 和 `<meta name="description">`，写进「地区 + 品类 + 品牌」
2. 全页只有一个 `<h1>`；`<h2>` 按客户的问题分段
3. 手机能正常打开（有 viewport），图片压缩过，首屏 3 秒内出来
4. HTTPS；根目录有 `sitemap.xml` 和 `robots.txt`；robots.txt 不挡 GPTBot、ClaudeBot、PerplexityBot、Bytespider、Baiduspider 等爬虫
5. JSON-LD 结构化数据：`Organization`（名称、法定名称、地址、电话、Logo）、`Product` 或 `Service`、`FAQPage`（和页面上的 FAQ 文字完全一致）
6. 关键信息是文字不是图片：公司名、地址、电话、价格区间、服务范围；每张图片有 `alt`
7. 准备提交：百度搜索资源平台、Google Search Console、Bing Webmaster Tools（列出要做的步骤，不替我登录）
8. 公司名、电话、地址全站一致；页内导航链接都能点

另外补一个 `llms.txt`：用几行 Markdown 写清公司是谁、卖什么、FAQ、联系方式。

## 步骤

1. 逐项检查，输出一张表：项目 · 通过 / 不通过 · 依据（文件和行号）
2. 不通过的直接改，改完列出改了哪些文件、哪几处
3. 第 7 项只给步骤清单

## 验收

- [ ] 8 项全部「通过」，或写明为什么暂时做不到
- [ ] FAQPage 里的问答和页面上看到的一字不差
- [ ] 没有编造任何地址、电话、资质、数字；缺的写「待确认」

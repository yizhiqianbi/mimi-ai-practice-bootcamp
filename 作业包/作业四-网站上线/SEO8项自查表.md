# SEO 上线前 8 项自查表

交给 Codex 的一句话：「用 seo-check 这个 Skill 检查 site/，逐项写通过或不通过；不通过的直接改，改完给我看改了哪些。」

改完后自己再按「怎么自己看」那一列核对一遍。

| # | 项目 | 怎么自己看 | 结果 |
|---|---|---|---|
| 1 | 独立标题和描述，含「地区 + 品类 + 品牌」 | 浏览器标签页上的文字；右键「查看网页源代码」搜 `description` | □ 通过 |
| 2 | 只有一个 H1，H2 按客户问题分段 | 源代码里搜 `<h1`，只出现一次 | □ 通过 |
| 3 | 手机能打开，3 秒内出首屏 | 手机流量（不连 Wi-Fi）打开计时 | □ 通过 |
| 4 | HTTPS + `sitemap.xml` + `robots.txt`，不挡 AI 爬虫 | 网址前面有小锁；网址后加 `/robots.txt`、`/sitemap.xml` 能打开 | □ 通过 |
| 5 | JSON-LD：Organization、Product 或 Service、FAQPage | 源代码搜 `application/ld+json`；FAQPage 里的问答和页面一字不差 | □ 通过 |
| 6 | 关键信息是文字，图片有 alt | 鼠标能选中公司名、电话、地址；源代码搜 `<img`，每个都有 `alt="..."` | □ 通过 |
| 7 | 提交收录：百度搜索资源平台、Google Search Console、Bing | 上线后做：三个平台各添加网站、验证、提交 sitemap | □ 已提交 |
| 8 | 内链和联系方式全站一致 | 页面上的电话、地址和 `事实底稿.md` 逐字对比；导航每个都点一下 | □ 通过 |

## 第 7 项怎么做（上线后 10 分钟）

1. **百度搜索资源平台**（ziyuan.baidu.com）：登录 → 用户中心 → 站点管理 → 添加网站 → 按提示用「文件验证」，把下载的验证文件放进 `site/` 重新部署 → 普通收录 → 提交 sitemap
2. **Google Search Console**（search.google.com/search-console）：添加资源 → 网址前缀 → 用「HTML 文件」验证 → 站点地图 → 提交 `sitemap.xml`
3. **Bing Webmaster Tools**（bing.com/webmasters）：可以直接从 Google Search Console 导入

收录需要几天到几周，不是提交完马上能搜到。

## 加分项（GEO）

- [ ] 根目录有 `llms.txt`，几行话说清公司是谁、卖什么、FAQ、联系方式
- [ ] FAQ 每个答案第一句就是结论
- [ ] 公司名、地址、电话和事实底稿、百度百科、企查查完全一致

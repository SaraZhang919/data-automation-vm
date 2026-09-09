"""The in-workbook guide follows actual tab IDs, including renamed tabs."""
from .core import stamp

DESCRIPTIONS={
 'GA4 Data Quality':('数据质量','对照渠道行合计与同范围站点API总量；不一致显示non_additive_review，保留源值，不强行缩放。'),
 'Properties':('人工配置','九种语言的 GA property ID；仅修改确认过的属性配置。'),
 'Page name - manual management':('人工配置','唯一页面台账。Urls 必填；Page Type / Page Name 用于显示映射；JP→ja、TW→zh-tw、BR→pt。任何深度英文路径均支持。'),
 'Site Event Logs - Manual':('人工记录','发布和变更记录；不代表 GA 事件实际触发成功。'),
 'Page Register Checks':('输入检查','逐行检查空 URL、双斜线、重复、语言冲突、未上线状态；原人工表保持不动。'),
 'Event Mapping':('人工配置','唯一业务事件 software_download，精确匹配。confirmed 表示业务含义确认；实际采集状态见 GA4 Business Events。下载点击不代表下载完成或安装。'),
 'GA4 Site':('主要数据','原 GA4 Daily。站点汇总，日/周/月在同表，按 period / start / end 筛选；总量直接查询 API。'),
 'GSC Site':('主要数据','原 GSC Daily。API 汇总；all 为属性总量，各语言按页面路径过滤。预览/正式不可混比。'),
 'GA4 Channels':('主要数据','channel 直接显示渠道名称；Session default channel group。不可将渠道行相加替代站点总量。'),
 'GA4 Landing Pages':('主要数据','会话入口页，不是全部页面 PV。按语言 Top30 Organic active users + 全部人工 URL；周/月保留上期 Top30。page_url 无参数。'),
 'GA4 Events':('事件数据','原始事件次数和触发用户，event_name 可筛选；software_download 及事件质量汇总进入 LLM，避免重复计算旧 dl_。'),
 'GA4 Business Events':('业务指标','software_download 次数、周期内去重触发用户、触发用户 / 同范围 totalUsers。无事件记录显示 waiting_for_event_data，指标留空。'),
 'GSC Pages':('主要数据','每语言 Top30 clicks + 人工 URL；名称类型来自人工表。不是全量页面，不能加总替代 GSC Site。'),
 'GSC Queries':('主要数据','query 明文显示；每语言/日期或周期按点击 Top100，受匿名关键词及 API 返回限制。'),
 'Comparisons':('变化分析','日环比、同星期、周环比、月环比。只有兼容范围和成熟/正式基线才计算；缺数据 unavailable，基线零 new_activity。'),
 'Thresholds':('规则配置','现有新站分层阈值。先检查样本量、绝对变化、相对变化及数据成熟度，再给出告警。'),
 'Period Status':('数据质量','周期刷新状态。周二正式周报与周日 GA 预览分别生成；延迟则后续自动重试。'),
 'Run Status':('运行记录','每次采集任务的成功、失败、等待、未配置状态；缺失不等于零或健康。'),
 'Data Revisions':('修订记录','回补导致的历史指标变动；数值表示差异不计为业务变化。'),
 'SF Pages':('技术快照','仅最新 Screaming Frog 页面摘要、入链计数和文件链接；Drive 保存完整原始 CSV。'),
 'SF Hreflang Issues':('技术问题','仅保存 SF 显式问题字段；网页实时 hreflang 规则另由 Technical Checks 检查。'),
 'Import Batches':('批次记录','SF 原始文件、批次日期、完整性、校验摘要及 Drive 链接。需人工运行 SF 并上传三个 CSV。'),
 'Sitemap URLs':('最新状态','递归读取 sitemap-index.xml。完整成功时更新快照；部分失败保留旧记录。'),
 'Sitemap Sources':('最新状态','每个 Sitemap 的抓取状态及 last_success_at；失败不可把旧成功当成最新成功。'),
 'Sitemap History':('变化记录','仅新增、移除、lastmod 变化；只有完整成功采集才能判定移除。'),
 'Sitemap Crawl Comparison':('技术对照','Sitemap 与最近 SF 快照比较；缺少入链仅是孤立页候选，不能直接证明孤立。'),
 'Technical Checks':('最新状态','页面 HTTP、canonical、robots、hreflang 等最新检查。'),
 'Technical History':('历史检查','有日期的检查证据，按保留期归档。'),
 'Check Coverage':('覆盖核对','实际检查数量和成功数量；轮询或失败页面必须明确。'),
 'URL Inspection':('收录诊断','Google 已知索引版本：verdict / coverage_state / canonical / last_crawl_time。api_status=success 只表示 API 调用成功。全站趋势看 GSC 网页索引。'),
 'Clarity Daily':('行为辅助','滚动24小时窗口，与 GA 自然日不同；不可直接做同日总量对账。'),
 'Clarity Requests':('运行记录','Clarity 请求状态与配额使用。'),
 'Manual Results':('手动查询','自定义日期、语言、URL 查询结果；不替代定时数据分区。'),
 'Archive Config':('存储配置','预先由用户账户拥有的私有 gzip 归档文件 ID。服务账户只更新指定文件；归档回读校验成功才移除主表旧记录。'),
 'Storage Status':('容量与归档','已分配单元格、待归档行数、归档校验状态；失败不删数据。'),
 'Overview':('最新日报','每天更新最新事实；AI 分析标记生成时间，报告修订保存在 Report History。'),
 'Weekly Overview':('最新周报','与日报独立；周日20:00 JST GA预览，周二17:00 JST GA修订+GSC；延迟时标记并重试。'),
 'Monthly Overview':('最新月报','每月4日16:00 JST 前一自然月；与日报/周报互不覆盖。'),
 'Report History':('报告历史','按类型、统计范围、版本保留日报/周报/月报；回补改变证据时生成修订版。'),
 'Issues':('行动清单','P1关键页或核心采集故障；P2局部SEO/成熟指标异常；P3观察机会。看 priority_reason、证据和来源链接。'),
 'Data Status':('数据质量','报告所用来源的运行状态与时间；未配置/延迟/失败不能当成正常。'),
 'Deep Analysis':('按需分析','Actions 手动 deep 模式，填写日期、语言、URL和问题；读取所选历史证据。'),
 'AI Usage':('模型审计','实际模型响应版本、推理程度、token 使用、提示词版本。日/周/月 gpt-5.6-sol medium；deep high。'),
 'AI Cache':('系统内部','相同证据的 AI 缓存，可以隐藏；不应手动编辑。'),
}

def update_guide(store,report=None):
    rows=[]
    topics=[
        ('GA过滤规则','所有GA统计均使用 hostName EXACT www.iboomto.com，精确匹配；不是 CONTAINS，也不是所有 *.iboomto.com。语言取相应独立 GA 属性。'),
        ('排除范围','不等于 www.iboomto.com 的 hostName 全部排除，包括测试子域、后台子域、localhost、内网IP、空/未设置值及裸域 iboomto.com。新出现的测试域也自动排除。'),
        ('GA界面对账','选择相同语言的 GA 属性→相同统计日期（属性时区）→添加 Host name / 主机名 精确等于 www.iboomto.com。渠道使用 Session default channel group；sessions 与 sessions 对比，不用 First user 渠道。'),
        ('采集时间','JST：每日17:00；周日20:00 GA周预览；周二17:00 GA周修订+GSC周报；每月4日16:00月报。GitHub定时可能排队。源数据日期按GA属性时区/GSC洛杉矶时区，不能用JST日期硬对照。'),
        ('回补与成熟度','每日查询最近7个已结束来源日期，上线前截断；按记录键更新而不重复追加。GA48小时是成熟策略，不是保证；GSC显示final_through和first_incomplete_date。'),
        ('页面数量','每日最近可用7天选页：每语言GA Organic active users Top30、GSC clicks Top30，再加人工表全部有效URL；周/月并入上期Top30。人工页无记录时显示 no_data_returned，指标留空。'),
        ('多语言路径','ar/ja/zh-tw/es/de/fr/it/pt 为首段语言前缀；其余任意层级内容路径为en。pt命名例外只在属性标签，URL仍是pt。zh-tw对应hreflang zh-Hant。'),
        ('周期与环比','period=daily/weekly/monthly；周日–周六、自然月。完整周期直接查询API，用户不可逐日相加。首个完整周09/13–19，首个完整月10月；部分上线周期单独标记。'),
        ('百分比定义','CTR=GSC clicks/impressions；user_conversion_rate=软件事件触发用户/相同属性与周期totalUsers；key_events_per_user为次数比值，不叫CTR。变化change_pct为相对百分比，change_pp为百分点。'),
        ('隐藏与筛选','可以隐藏列或sheet，不影响API读写；隐藏不节省容量、不隔离权限。不要改依赖表名/表头，不要在自动行中插入人工备注；请使用筛选视图。'),
        ('容量策略','日明细90天；站点日汇总365天；周104周；月36个月。仅归档写入并回读校验成功后移除旧记录，失败保留并报状态。'),
        ('报告与LLM','程序负责采集、清洗、阈值、对比及优先级。LLM分析周期匹配的业务事件、页面/渠道摘要和异常。无业务事件返回不报零；事实每次刷新，AI文本有独立日期与版本。'),
        ('软件下载设置','各GA属性需要实际发送software_download或通过创建事件规则生成；仅添加Key event名称不会转换dl_*；新建事件不回填过去。'),
        ('服务器日志','目前尚未接入网站CDN访问日志。此处不包含安装包日志分析；软件下载仅使用GA事件。'),
    ]
    for topic,detail in topics:rows.append({'类别':'使用规则','表格或主题':topic,'说明':detail,'链接':''})
    for book in (store,report):
        if not book:continue
        names=set(book.tabs)|set(book.dirty)
        for name in sorted(names):
            if name=='Guide':continue
            category,detail=DESCRIPTIONS.get(name,('系统记录','自动化内部记录；请勿改名或删除表头。'))
            rows.append({'类别':category,'表格或主题':name,'说明':detail,'链接':book.link(name)})
    store.set('Guide',rows,headers=['类别','表格或主题','说明','链接'])

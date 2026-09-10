"""The in-workbook guide follows actual tab IDs, including renamed tabs."""
import os
import math
import unicodedata

DESCRIPTIONS={
 'GA4 Data Quality':('数据质量','对照渠道行合计与同范围站点API总量；不一致显示non_additive_review，保留源值，不强行缩放。'),
 'Properties':('人工配置','九种语言的 GA property ID；仅修改确认过的属性配置。'),
 'Page name - manual management':('人工配置','唯一页面台账。Urls 必填；Page Type / Page Name 用于显示映射；JP→ja、TW→zh-tw、BR→pt。任何深度英文路径均支持。'),
 'Site Event Logs - Manual':('人工记录','发布和变更记录；不代表 GA 事件实际触发成功。'),
 'Page Register Checks':('输入检查','逐行检查空 URL、双斜线、重复、语言冲突、未上线状态；原人工表保持不动。'),
 'Event Mapping':('人工配置','唯一业务事件 software_download，精确匹配。confirmed 表示业务含义确认；实际采集状态见 GA4 Business Events。下载点击不代表下载完成或安装。'),
 'GA4 Site':('主要数据','原 GA4 Daily。站点汇总，日/周/月在同表，按 period / start / end 筛选；总量直接查询 API。'),
 'GSC Site':('主要数据','原 GSC Daily。仅采集和分析已完成的final数据，截止日期按Google完成边界确定；all为属性总量，各语言按页面路径过滤。历史预览记录不参与当前报告。'),
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
 'Technical Findings':('规则证据','最新检查产生的问题证据；人工标记未上线的页面暂作观察，不当作线上关键页故障。'),
 'Technical History':('历史检查','有日期的检查证据，按保留期归档。'),
 'Check Coverage':('覆盖核对','实际检查数量和成功数量；轮询或失败页面必须明确。'),
 'URL Inspection':('收录诊断','Google 已知索引版本：verdict / coverage_state / canonical / last_crawl_time。api_status=success 只表示 API 调用成功。全站趋势看 GSC 网页索引。'),
 'Clarity Snapshots':('行为辅助','每48小时保存一条总体快照，覆盖此前72小时；窗口重叠不可相加。旧快照保留原始时间。页面观察见Clarity Pages。'),
 'Clarity Pages':('页面行为','最近7个已完成GSC数据日、全语言点击Top20的页面；最多20条/批。Clarity URL响应本地筛选，未返回不是零；页面交互覆盖所有渠道。'),
 'Clarity Requests':('运行记录','总体及URL两个视图的请求状态、重试和配额。每视图每48小时批次最多3次尝试，成功视图不重复抓取。'),
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
 'AI Usage':('模型审计','input_tokens / output_tokens / total_tokens 为API实际用量；reasoning_tokens包含在output_tokens内。另记发送字符数、模型响应版本、提示词版本。日/周/月 gpt-5.6-sol medium；deep high。'),
 'AI Cache':('系统内部','相同证据的 AI 缓存，可以隐藏；不应手动编辑。'),
}

def update_guide(store,report=None):
    # Once created, guides are user-owned. Routine jobs must not rebuild notes or layout.
    if any(n.lower().endswith('guide') for n in store.tabs):return
    name=next((n for n in store.tabs if n!='Guide' and n.endswith('Guide')),'Guide')
    rows=[]
    topics=[
        ('GA过滤规则','所有GA统计均使用 hostName EXACT www.iboomto.com，精确匹配；不是 CONTAINS，也不是所有 *.iboomto.com。语言取相应独立 GA 属性。'),
        ('排除范围','不等于 www.iboomto.com 的 hostName 全部排除，包括测试子域、后台子域、localhost、内网IP、空/未设置值及裸域 iboomto.com。新出现的测试域也自动排除。'),
        ('GA界面对账','选择相同语言的 GA 属性→相同统计日期（属性时区）→添加 Host name / 主机名 精确等于 www.iboomto.com。渠道使用 Session default channel group；sessions 与 sessions 对比，不用 First user 渠道。'),
        ('采集时间','JST：每日17:00；周日20:00 GA周预览；周二17:00 GA周修订+GSC周报；每月4日16:00月报。GitHub定时可能排队。源数据日期按GA属性时区/GSC洛杉矶时区，不能用JST日期硬对照。'),
        ('回补与成熟度','每日在最近7个已结束来源日期窗口内回补，上线前截断。GA保持原计划；GSC先核对完成边界，只采集截至final_through的final数据，不以预览数据补位。按记录键更新而不重复追加。'),
        ('页面数量','每日最近可用7天选页：每语言GA Organic active users Top30、GSC clicks Top30，再加人工表全部有效URL；周/月并入上期Top30。人工页无记录时显示 no_data_returned，指标留空。'),
        ('多语言路径','ar/ja/zh-tw/es/de/fr/it/pt 为首段语言前缀；其余任意层级内容路径为en。pt命名例外只在属性标签，URL仍是pt。zh-tw对应hreflang zh-Hant。'),
        ('周期与环比','period=daily/weekly/monthly；周日–周六、自然月。完整周期直接查询API，用户不可逐日相加。首个完整周09/13–19，首个完整月10月；部分上线周期单独标记。'),
        ('百分比定义','CTR=GSC clicks/impressions；user_conversion_rate=软件事件触发用户/相同属性与周期totalUsers；key_events_per_user为次数比值，不叫CTR。变化change_pct为相对百分比，change_pp为百分点。'),
        ('隐藏与筛选','可以隐藏列或sheet，不影响API读写；隐藏不节省容量、不隔离权限。不要改依赖表名/表头，不要在自动行中插入人工备注；请使用筛选视图。'),
        ('容量策略','日明细90天；站点日汇总365天；周104周；月36个月。仅归档写入并回读校验成功后移除旧记录，失败保留并报状态。'),
        ('报告与LLM','程序负责采集、清洗、阈值、对比及优先级。LLM分析周期匹配的业务事件、页面/渠道摘要和异常。无业务事件返回不报零；事实每次刷新，AI文本有独立日期与版本。'),
        ('LLM发送内容','发送结构化汇总，不发送服务器原始日志、录屏、完整SF文件、密钥或整本表格。Clarity只发送最新总体快照及最新Top20页面快照，不发送全部URL响应或页面历史。普通分析保留所选GA/GSC页面和关键词级聚合指标。'),
        ('Clarity频率与窗口','自2026/09/10起每48小时、17:00 JST采集最近72小时，正常每批2个API请求；日报任务检查是否到期，成功后次日跳过。失败视图可在下一次运行重试。重叠窗口不可相加为周/月总数。'),
        ('软件下载设置','各GA属性需要实际发送software_download或通过创建事件规则生成；仅添加Key event名称不会转换dl_*；新建事件不回填过去。'),
        ('服务器日志','目前尚未接入网站CDN访问日志。此处不包含安装包日志分析；软件下载仅使用GA事件。'),
    ]
    groups=[
        ('报告与行动',['Overview','Weekly Overview','Monthly Overview','Issues','Comparisons','Report History','Deep Analysis']),
        ('人工维护',['Properties','Page name - manual management','Site Event Logs - Manual','Event Mapping','Thresholds']),
        ('流量与下载',['GA4 Site','GA4 Channels','GA4 Landing Pages','GA4 Business Events','GA4 Events','GSC Site','GSC Pages','GSC Queries','Clarity Snapshots','Clarity Pages','Manual Results']),
        ('技术 SEO',['Technical Findings','Technical Checks','URL Inspection','SF Pages','SF Hreflang Issues','Sitemap URLs','Sitemap Sources','Sitemap Crawl Comparison','Sitemap History','Technical History']),
        ('数据质量',['Data Status','Run Status','GA4 Data Quality','Page Register Checks','Check Coverage','Period Status','Import Batches','Data Revisions']),
        ('系统与用量',['AI Usage','Storage Status','Archive Config','Clarity Requests','AI Cache']),
    ]
    entries={}
    for book in (store,report):
        if not book:continue
        names=set(book.tabs)|set(book.dirty)
        for tab_name in sorted(names):
            if tab_name.lower().endswith('guide'):continue
            category,detail=DESCRIPTIONS.get(tab_name,('系统记录','自动化内部记录；请勿改名或删除表头。'))
            entries[tab_name]=(detail,book.link(tab_name))
    links={}
    for category,names in groups+[('其他记录',sorted(set(entries)-{n for _,ns in groups for n in ns}))]:
        for tab_name in names:
            if tab_name not in entries:continue
            detail,url=entries[tab_name]
            rows.append({'类别':category,'表格或主题':tab_name,'说明':detail})
            links[tab_name]=url
    for topic,detail in topics:rows.append({'类别':'使用规则','表格或主题':topic,'说明':detail})
    if os.environ.get('IBOOMTO_AI_REPORTS_ENABLED','').lower()!='true':
        rows.append({'类别':'当前运行状态','表格或主题':'LLM 分析授权','说明':'扩展后的数据传输目前暂未启用；采集和事实视图正常运行。获准将汇总证据发送到 OpenAI 后设置 IBOOMTO_AI_REPORTS_ENABLED=true。'})
    store.set(name,rows,headers=['类别','表格或主题','说明'])
    store.guide_links={name:links}
    store.dirty.add(name)  # Refresh native hyperlinks even if displayed text is unchanged.


def guide_format_requests(sid,rows,links,width=6):
    """Reset the old guide layout and attach native links to the visible names."""
    end=len(rows)+1
    requests=[{'repeatCell':{'range':{'sheetId':sid,'startRowIndex':0,'endRowIndex':end,'endColumnIndex':width},
        'cell':{'userEnteredFormat':{'backgroundColor':{'red':1,'green':1,'blue':1},'verticalAlignment':'TOP','wrapStrategy':'WRAP',
            'textFormat':{'fontFamily':'Arial','fontSize':11,'foregroundColor':{'red':.15,'green':.15,'blue':.15}}}},
        'fields':'userEnteredFormat,textFormatRuns'}},
        {'repeatCell':{'range':{'sheetId':sid,'startRowIndex':0,'endRowIndex':1,'endColumnIndex':3},
            'cell':{'userEnteredFormat':{'backgroundColor':{'red':.92,'green':.94,'blue':.96},'textFormat':{'bold':True}}},
            'fields':'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold'}}]
    for i,size in enumerate((145,290,760)):
        requests.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':i,'endIndex':i+1},'properties':{'pixelSize':size},'fields':'pixelSize'}})
    previous=None
    for index,row in enumerate(rows,1):
        category=row['类别'];url=links.get(row['表格或主题'])
        if category!=previous:
            requests.append({'repeatCell':{'range':{'sheetId':sid,'startRowIndex':index,'endRowIndex':index+1,'endColumnIndex':1},
                'cell':{'userEnteredFormat':{'textFormat':{'bold':True},'backgroundColor':{'red':.94,'green':.96,'blue':.98}}},
                'fields':'userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor'}})
        if url:
            requests.append({'repeatCell':{'range':{'sheetId':sid,'startRowIndex':index,'endRowIndex':index+1,'startColumnIndex':1,'endColumnIndex':2},
                'cell':{'userEnteredFormat':{'textFormat':{'link':{'uri':url},'underline':True,'foregroundColor':{'red':.07,'green':.33,'blue':.72}}}},
                'fields':'userEnteredFormat.textFormat.link,userEnteredFormat.textFormat.underline,userEnteredFormat.textFormat.foregroundColor'}})
        previous=category
    # Sheets auto-resize can leave wrapped rows at 21px; reserve explicit reading space.
    requests.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'ROWS','startIndex':0,'endIndex':1},'properties':{'pixelSize':32},'fields':'pixelSize'}})
    for index,row in enumerate(rows,1):
        lines=max(math.ceil(sum(15 if unicodedata.east_asian_width(c) in 'WF' else 8 for c in row[key])/(size-20))
                  for key,size in zip(('类别','表格或主题','说明'),(145,290,760)))
        height=max(44,24*lines+12)
        requests.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'ROWS','startIndex':index,'endIndex':index+1},'properties':{'pixelSize':height},'fields':'pixelSize'}})
    return requests

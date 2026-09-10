"""Shared human-readable headers and narrowly scoped formats."""
FRONT=['period','start','end','language','channel','event_name','subfolder','page_type','page_name','page_url','query','selection_reason','data_status','quality']
PERCENT={'ctr','engagementRate','user_conversion_rate','change_ratio','change_pct','yellow_pct','red_pct','yellow_relative','red_relative','impressions_growth_ratio'}
TECH={'id','dimensions','metadata','scope','property','scope_version'}
COUNTS={'sessions','engagedSessions','activeUsers','totalUsers','newUsers','keyEvents','eventCount','clicks','impressions',
        'event_count','converting_users','eligible_users','api_sessions','channel_rows_sum','baseline_clicks','baseline_impressions'}

def ordered_headers(name,head):
    if name=='Clarity Pages':
        first=['day','language','page_url','gsc_rank','gsc_clicks','data_status','total_sessions','distinct_users','window_start','window_end','gsc_start','gsc_end']
        return [x for x in first if x in head]+[x for x in head if x not in first]
    if name.startswith(('GA4 ','GSC ')) and name not in ('GA4 Reconciliation',):
        return [x for x in FRONT if x in head]+[x for x in head if x not in FRONT and x not in TECH]+[x for x in head if x in TECH]
    if name=='Issues':
        first=['priority','kind','url','state','priority_reason','evidence','source_link']
        return [x for x in first if x in head]+[x for x in head if x not in first]
    return head

def format_columns(sid,name,head,count,new_layout):
    requests=[]
    for i,key in enumerate(head):
        rg={'sheetId':sid,'startRowIndex':1,'endRowIndex':max(2,count+1),'startColumnIndex':i,'endColumnIndex':i+1}
        fmt=None
        if key in COUNTS or (name.startswith('Clarity') and (key.endswith(('_count','_sessions_base')) or key in ('total_sessions','total_bot_sessions','distinct_users','gsc_clicks','gsc_rank'))):fmt={'type':'NUMBER','pattern':'#,##0'}
        elif key in PERCENT or key.endswith('_session_rate') or key=='average_scroll_depth':fmt={'type':'PERCENT','pattern':'0.00%'}
        elif key in ('change_pp','drop_percentage_points'):fmt={'type':'NUMBER','pattern':'0.00" pp"'}
        elif key in ('key_events_per_user','position','averageSessionDuration'):fmt={'type':'NUMBER','pattern':'0.00'}
        if fmt:requests.append({'repeatCell':{'range':rg,'cell':{'userEnteredFormat':{'numberFormat':fmt}},'fields':'userEnteredFormat.numberFormat'}})
        if new_layout:
            width=430 if key in ('page_url','original_url','url','source_link','inspection_link') else 240 if key in ('page_name','query','hostname_filter','coverage_state') else 160
            requests.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':i,'endIndex':i+1},'properties':{'pixelSize':width},'fields':'pixelSize'}})
    if new_layout and head and name.startswith(('GA4 ','GSC ','SF ','Sitemap','URL Inspection','Comparisons','Clarity Pages')):
        requests.append({'setBasicFilter':{'filter':{'range':{'sheetId':sid,'startRowIndex':0,'endColumnIndex':len(head)}}}})
    if new_layout and name.endswith('Guide'):
        for i,width in enumerate((140,250,960,380)):
            requests.append({'updateDimensionProperties':{'range':{'sheetId':sid,'dimension':'COLUMNS','startIndex':i,'endIndex':i+1},'properties':{'pixelSize':width},'fields':'pixelSize'}})
        requests.append({'repeatCell':{'range':{'sheetId':sid,'startRowIndex':1,'endRowIndex':count+1,'endColumnIndex':len(head)},'cell':{'userEnteredFormat':{'wrapStrategy':'WRAP'}},'fields':'userEnteredFormat.wrapStrategy'}})
        requests.append({'autoResizeDimensions':{'dimensions':{'sheetId':sid,'dimension':'ROWS','startIndex':1,'endIndex':count+1}}})
    return requests

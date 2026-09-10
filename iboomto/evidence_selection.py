"""Report relevance filters; source collection and Sheets history stay intact."""
from collections import Counter, defaultdict


def latest_comparisons(rows):
    dates={}
    def key(r):return (r.get('source',''),r.get('language',''),r.get('period',''))
    for r in rows:dates[key(r)]=max(dates.get(key(r),''),r.get('current_end',''))
    return [r for r in rows if r.get('current_end','')==dates[key(r)]]


def query_evidence(rows, period):
    groups=defaultdict(list)
    for r in rows:groups[(r.get('language',''),r.get('start',''),r.get('end',''))].append(r)
    summaries=[];details=[]
    fields=('language','start','end','query','clicks','impressions','ctr','position','selection_reason',
            'baseline_status','baseline_start','baseline_end','impressions_daily_delta','impressions_growth_ratio','quality')
    def num(r,k):
        try:return float(r.get(k) or 0)
        except (TypeError,ValueError):return 0
    for (lang,start,end),items in sorted(groups.items()):
        selected={}
        def add(pool,metric,n):
            for r in sorted(pool,key=lambda x:(-num(x,metric),x.get('query','')))[:n]:selected[r['query']]=r
        if period=='daily' and len(items)>20:
            add(items,'clicks',5);add(items,'impressions',5)
            add([r for r in items if 'new_in_candidate_pool' in r.get('selection_reason','')],'impressions',5)
            add([r for r in items if 'growing_impressions' in r.get('selection_reason','')],'impressions_daily_delta',5)
            for r in items:
                # Never drop explicit alerts or unusually large observed growth just to meet the representative count.
                if r.get('severity') in ('red','yellow') or r.get('priority') in ('P1','P2') or (
                    r.get('baseline_status')=='returned' and num(r,'impressions_daily_delta')>=100 and num(r,'impressions_growth_ratio')>=2):
                    selected[r['query']]=r
        else:selected={r['query']:r for r in items}
        categories=Counter(c for r in items for c in r.get('selection_reason','').split('|') if c)
        summaries.append({'language':lang,'start':start,'end':end,'selected_query_count':len(items),
                          'sent_query_count':len(selected),'omitted_detail_count':len(items)-len(selected),
                          'selected_query_clicks':sum(num(r,'clicks') for r in items),
                          'selected_query_impressions':sum(num(r,'impressions') for r in items),
                          'selection_categories_overlapping':dict(categories),
                          'baseline_status_counts':dict(Counter(r.get('baseline_status','unknown') for r in items)),
                          'candidate_pool_size':max((num(r,'candidate_pool_size') for r in items),default=0),
                          'candidate_pool_truncated':any(r.get('candidate_pool_truncated') in (True,'TRUE','true') for r in items)})
        details.extend({k:r[k] for k in fields if k in r} for r in selected.values())
    return summaries,details

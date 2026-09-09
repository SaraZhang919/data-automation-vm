import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const wb=Workbook.create();
const tabs={
  'Overview':[['section','item','value'],['日报','状态','等待首次采集完成'],['运行时间','每日','17:00 JST 触发，采集后生成日报'],['数据口径','GA / GSC','各来源分别标注统计日期和完整性']],
  'Daily History':[['id','report_date','kind','generated_at','run_id','ai_status','question','summary','findings','actions','deep_analysis_candidates','limitations','data_dates']],
  'Issues':[['id','kind','url','severity','state','first_seen','last_seen','resolved_at','source','evidence']],
  'Data Status':[['id','source','status','started_at','finished_at','run_id','detail']],
  'Deep Analysis':[['id','report_date','kind','generated_at','run_id','ai_status','question','summary','findings','actions','deep_analysis_candidates','limitations','data_dates']],
  'AI Usage':[['id','at','kind','requested_model','response_model','reasoning_effort','prompt_version','rule_version','usage','finish_reason']],
};
await fs.mkdir('outputs/report',{recursive:true});
for(const [name,rows] of Object.entries(tabs)){
  const s=wb.worksheets.add(name);s.showGridLines=false;
  s.getRange('A1').write(rows);
  const end=String.fromCharCode(64+rows[0].length);
  const r=s.getRange(`A1:${end}${Math.max(rows.length,2)}`);
  r.format.font={name:'Arial',size:11};r.format.rowHeightPx=28;r.format.columnWidthPx=165;
  const head=s.getRange(`A1:${end}1`);head.format.fill='#19334D';head.format.font={bold:true,color:'#FFFFFF',size:11};head.format.rowHeightPx=34;
  if(name==='Overview'){
    s.getRange('A1:A4').format.columnWidthPx=130;s.getRange('B1:B4').format.columnWidthPx=160;s.getRange('C1:C4').format.columnWidthPx=480;
  }
  const img=await wb.render({sheetName:name,range:`A1:${name==='Overview'?'C':'F'}${Math.max(rows.length,2)}`,scale:1.5});
  await fs.writeFile(`outputs/report/${name.replaceAll(' ','_')}.png`,new Uint8Array(await img.arrayBuffer()));
}
console.log((await wb.inspect({kind:'sheet',include:'id,name',maxChars:1800})).ndjson);
const file=await SpreadsheetFile.exportXlsx(wb);await file.save('outputs/report/iboomto-daily-report.xlsx');

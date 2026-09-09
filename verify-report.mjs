import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load('outputs/report/live-report.xlsx'));
for(const name of ['Overview','Daily History','Issues','Data Status','Deep Analysis','AI Usage']){
  const range=name==='Overview'?'A1:C12':name==='Daily History'?'H1:J2':name==='Issues'?'B1:E7':name==='Data Status'?'A1:C10':name==='AI Usage'?'B1:F3':'A1:F2';
  const img=await wb.render({sheetName:name,range,scale:1.2});
  await fs.writeFile(`outputs/report/live-${name.replaceAll(' ','_')}.png`,new Uint8Array(await img.arrayBuffer()));
}
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?',options:{useRegex:true,maxResults:10},maxChars:500})).ndjson);

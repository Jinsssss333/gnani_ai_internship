import { useState } from 'react';
import type { VisitRecord } from './types';

export function indianDate(timestamp: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(timestamp));
  return ['year','month','day'].map(type => parts.find(p=>p.type===type)?.value).join('-');
}
const headers = ['Recorded date (IST)','Patient','Age','Visit code','Outcome','Symptoms','Symptoms absent','Follow-up','Notes','Reason not completed','Blood pressure','Temperature (F)'];
const escape = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export default function RegisterExport({visits}: {visits: VisitRecord[]}) {
  const [from,setFrom] = useState('');
  const [to,setTo] = useState('');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const invalid = !!(from && to && from > to);
  const selected = visits.filter(v => !v.deleted_at && (!from || indianDate(v.created_at)>=from) && (!to || indianDate(v.created_at)<=to));
  const rows = selected.map(record => {
    const v = record.visit as VisitRecord['visit'] & {visit_code?: string; visit_status?: string; negated_symptoms?: string[];not_done_reason?: string};
    return [indianDate(record.created_at),v.patient_name || '',v.age ?? '',v.visit_code || '',v.visit_status?.replaceAll('_',' ') || 'Not recorded',v.symptoms.join(', '),(v.negated_symptoms || []).join(', '),v.follow_up_date || v.follow_up_phrase || '',v.notes || '',v.not_done_reason?.replaceAll('_',' ') || '',v.vitals?.blood_pressure || '',v.vitals?.temperature_f ?? ''];
  });
  const title = `SunoCare visits · ${from || 'Beginning'} to ${to || 'Today'} · ${rows.length} submitted`;
  async function excel() {
    setBusy(true); setError('');
    try {
      const {Workbook} = await import('exceljs');
      const workbook = new Workbook();
      const sheet = workbook.addWorksheet('Visits', {views:[{state:'frozen',ySplit:3}]});
      sheet.addRow([title]); sheet.mergeCells(1,1,1,headers.length);
      sheet.addRow([]); sheet.addRow(headers);
      rows.forEach(row => sheet.addRow(row)); // Strings remain strings, including leading '='.
      sheet.getRow(1).font = {bold:true,size:14};
      sheet.getRow(3).font = {bold:true,color:{argb:'FFFFFFFF'}};
      sheet.getRow(3).fill = {type:'pattern',pattern:'solid',fgColor:{argb:'FF263326'}};
      sheet.columns.forEach((column,i)=> { column.width = [22,24,8,14,20,36,30,22,45,26,18,18][i]; });
      sheet.eachRow(row=> { row.alignment={vertical:'top',wrapText:true}; });
      sheet.autoFilter = {from:{row:3,column:1},to:{row:rows.length+3,column:headers.length}};
      const bytes = await workbook.xlsx.writeBuffer();
      const url = URL.createObjectURL(new Blob([bytes], {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
      const link=document.createElement('a'); link.href=url; link.download=`sunocare-${from || 'all'}-${to || 'latest'}.xlsx`; link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch { setError('Excel export failed. Please retry.'); }
    finally { setBusy(false); }
  }
  function pdf() {
    setError('');
    const report=window.open('','_blank');
    if (!report) { setError('Allow pop-ups to open the PDF report.'); return; }
    report.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escape(title)}</title><style>
      @page{size:A4;margin:16mm}body{font:12px system-ui,sans-serif;color:#202920}h1{font-size:22px}article{border-top:2px solid #263326;padding:14px 0;break-inside:avoid}dl{display:grid;grid-template-columns:140px 1fr;gap:8px}dt{font-weight:bold}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}button{padding:12px;font:inherit}@media print{button{display:none}}
      </style></head><body><button onclick="window.print()">Print / Save as PDF</button><h1>SunoCare visit register</h1><p>${escape(title)}</p>${rows.map((row,i)=>`<article><h2>${i+1}. ${escape(row[1] || 'Home visit')}</h2><dl>${headers.map((h,j)=>`<dt>${escape(h)}</dt><dd>${escape(row[j] === '' ? '—' : row[j])}</dd>`).join('')}</dl></article>`).join('')}</body></html>`);
    report.document.close(); report.focus();
  }
  return <section className="register" aria-label="Export visits"><details><summary>Export submitted visits</summary><div style={{display:'flex',gap:12,flexWrap:'wrap',alignItems:'end',paddingTop:16}}>
    <label>From<input aria-label="Export from date" type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label>
    <label>To<input aria-label="Export to date" type="date" value={to} onChange={e=>setTo(e.target.value)}/></label>
    <button disabled={busy || invalid || !rows.length} onClick={()=>void excel()}>Download Excel</button>
    <button disabled={invalid || !rows.length} onClick={pdf}>PDF / Print</button>
    </div><p>{invalid ? 'End date must be on or after start date.' : `${rows.length} submitted visits · Recorded date (IST), inclusive. Blank dates include all dates.`}</p>{error && <p role="alert">{error}</p>}</details></section>;
}

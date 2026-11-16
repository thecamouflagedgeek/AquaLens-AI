import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, message } from '../api';
import { useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Bar, BarChart, Brush, CartesianGrid, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, Empty } from './shared';
import ganga from './ganga-stations.json';
import './context-lab.css';

const blue = '#1659b4';
const valueOf = v => v == null || String(v).trim() === '' || !Number.isFinite(Number(v)) ? null : Number(v);
const fmt = v => Number(v.toPrecision(5));
const label = r => r.unit ? r.parameter + ' (' + r.unit + ')' : r.parameter;
const average = xs => xs.reduce((a,b) => a+b,0)/xs.length;

function Breakdown({ view, finding, purpose, method, limit }) {
  return <details><summary>Understand this</summary><dl>{Object.entries({
    'What am I looking at?': view, 'What does it indicate?': finding, 'Why does it matter?': purpose,
    'How was it calculated?': method, 'What are the limitations?': limit,
  }).map(([key, text]) => <div key={key}><dt>{key}</dt><dd>{text}</dd></div>)}</dl></details>;
}

function archiveRecords(site, archive) {
  if (site?.values) return site.values.map((value,i) => ({ id:i, timestamp:String(2022+i%4), parameter:i<4?'Dissolved oxygen':'BOD', unit:'mg/L', value, provenance:ganga.source, kind:'Archive water quality' }));
  return (site?.observations || []).flatMap(([timestamp,id,...values]) => {
    const fields = archive.headers || ['pH','Dissolved oxygen','Total dissolved solids'];
    return fields.flatMap((parameter,i) => {
      const value = valueOf(values[i]);
      if (value === null) return [];
      const context = ['rainfall(mm)','level(m)'].includes(parameter);
      const unit = archive.headers ? (parameter === 'rainfall(mm)' ? 'mm' : parameter === 'level(m)' ? 'm' : '') : i ? 'mg/L' : '';
      return [{ id:id+':'+i, sampleKey:id, timestamp, parameter:parameter === 'rainfall(mm)' ? 'Rainfall' : parameter === 'level(m)' ? 'Water level' : parameter, value, unit, season:archive.headers ? values[fields.indexOf('season')] : null, provenance:archive.source, kind:context?'Context':'Archive water quality' }];
    });
  });
}
function Series({ title, rows, selected, choose }) {
  const names = [...new Set(rows.map(label))];
  const name = names.includes(selected) ? selected : names[0];
  const points = rows.filter(r => label(r) === name).map(r => ({ ...r, x:Date.parse(r.timestamp.length===4?r.timestamp+'-01-01':r.timestamp.length===10 || /(?:Z|[+-]\d\d:\d\d)$/.test(r.timestamp)?r.timestamp:r.timestamp+'Z') })).filter(r=>Number.isFinite(r.x)).sort((a,b)=>a.x-b.x);
  return <Card title={title}>
    <p>{points.length ? `${name} has ${points.length} reported ${points.length === 1 ? 'reading' : 'readings'} in this selection. Choose a parameter to inspect its record.` : 'The selected location and dates do not have enough evidence to describe this parameter.'}</p>
    {points.length ? <><label>Parameter <select value={name} onChange={e=>choose(e.target.value)}>{names.map(n=><option key={n}>{n}</option>)}</select></label>
      <div className="in-lab-chart"><ResponsiveContainer><LineChart data={points} syncId="context-lab-time" syncMethod="value" margin={{right:18}}>
        <CartesianGrid vertical={false} stroke="#dce7fa"/><XAxis dataKey="x" type="number" scale="time" domain={['dataMin','dataMax']} tickFormatter={x=>new Date(x).toISOString().slice(0,points[0].timestamp.length===4?4:10)}/><YAxis domain={['auto','auto']}/><Tooltip labelFormatter={(_,p)=>p?.[0]?.payload.timestamp}/><Line dataKey="value" name={name} stroke={blue} dot={{r:3}} isAnimationActive={false}/>{points.length>2 && <Brush dataKey="timestamp" height={20}/>}
      </LineChart></ResponsiveContainer></div></> : <Empty>No matching measurements in this period.</Empty>}
    <Breakdown view="Time on the horizontal axis; reported values and source units in the parameter selector." finding={points.length ? points.length+' readings; observed range '+fmt(Math.min(...points.map(p=>p.value)))+' to '+fmt(Math.max(...points.map(p=>p.value)))+'.' : 'No pattern can be assessed.'} purpose="Compare measurements within a single station and parameter." method="Reported readings ordered by timestamp; drag the handles to narrow the view." limit="Lines connect available readings only. Unmeasured periods and units absent from the source are not inferred. Ganga’s 2025 summary covers January–October."/>
  </Card>;
}

const criteria = {
  bathing: { name:'Class B · Organised outdoor bathing', oxygen:5 },
  fisheries: { name:'Class D · Wildlife and fisheries propagation', oxygen:4 },
};

function Assessment({ records }) {
  const [purpose,setPurpose]=useState('');
  const criteriaSet=criteria[purpose];
  const oxygen=records.find(r=>/^(do|dissolved oxygen)$/i.test(r.parameter.trim()) && /^mg\/l$/i.test(r.unit?.trim()));
  const ph=records.find(r=>/^ph$/i.test(r.parameter.trim()) && /^(?:ph(?: units?)?|unitless|dimensionless)?$/i.test(r.unit?.trim() || ''));
  return <Card title="How do readings compare with the selected reference?" hint="Parameter screening · selected station and period">
    <label>Intended use <select value={purpose} onChange={e=>setPurpose(e.target.value)}><option value="">Choose a comparison purpose</option>{Object.entries(criteria).map(([key,c])=><option key={key} value={key}>{c.name}</option>)}</select></label>
    <p><a href="https://cpcb.nic.in/wqm/Designated_Best_Use_Water_Quality_Criteria.pdf" target="_blank" rel="noreferrer">CPCB Designated Best Use criteria ↗</a>. This selection does not establish the station’s official designation.</p>
    {criteriaSet && [[ph,'pH',6.5,8.5],[oxygen,'Dissolved oxygen',criteriaSet.oxygen,null]].map(([row,name,min,max])=>{
      const right=Math.max(max??min,row?.value??0)*1.15, left=Math.min(0,row?.value??0);
      const position=v=>100*(v-left)/(right-left);
      return <section className="in-lab-bullet" key={name}><h3>{name}</h3><p>{name==='pH'?'Acidity or alkalinity can affect aquatic organisms.':'Dissolved oxygen is the oxygen available to aquatic organisms.'}</p>
        <p>Reference: {max===null?'at least '+min+' mg/L':min+'–'+max}.</p>
        {row ? <><div className="in-lab-bullet-track" aria-hidden="true"><i style={{left:position(min)+'%',width:(max===null?100-position(min):position(max)-position(min))+'%'}}/><b style={{left:position(row.value)+'%'}}/></div><p><strong>{row.value} {row.unit}</strong> · {row.timestamp}{row.timestamp==='2025'?' (Jan–Oct)':''} · {row.provenance || 'Source not recorded'} · {row.value>=min&&(max===null||row.value<=max)?'Meets this parameter criterion':'Outside this parameter criterion'}</p></> : <p>No reading with compatible units in this period.</p>}
      </section>;
    })}
    <Breakdown view="The marker shows the latest compatible value; shading shows the criterion range." finding="Each result applies only to the displayed parameter and reporting period." purpose="Compare reported values with a reference chosen for an intended water use." method="Compare directly in source units against the published bounds. No borderline category or conversion is assumed." limit="Archive summaries are not individual samples. This screen does not evaluate microbiology, verify BOD protocol, or establish overall compliance or suitability."/>
  </Card>;
}

function MeasurementChange({ records }) {
  const distinct=[...new Set(records.map(r=>r.timestamp))].sort();
  const endpoints=[distinct[0],distinct.at(-1)].map(t=>records.filter(r=>r.timestamp===t));
  if(distinct.length<2 || endpoints.some(rows=>rows.length!==1)) return <Empty>Change needs two distinct periods with unambiguous readings.</Empty>;
  const [first,last]=endpoints.map(rows=>rows[0]);
  const change=last.value-first.value;
  const points=[{period:first.timestamp,value:first.value},{period:last.timestamp,value:last.value}];
  return <><div className="in-lab-chart"><ResponsiveContainer><BarChart data={points}><XAxis dataKey="period"/><YAxis/><Tooltip/><Bar dataKey="value" name={label(first)} fill={blue}/></BarChart></ResponsiveContainer></div>
    <Breakdown view={label(first)+' at the first and last reported periods in the selection.'} finding={first.value+' → '+last.value+'; signed change '+fmt(change)+(first.value>0&&!/^ph$/i.test(first.parameter)?' ('+fmt(100*change/first.value)+'%)':'')+'.'} purpose="See the magnitude and direction of the measured change before interpreting it against context." method="Last minus first reported value. Relative change divides by the first value where appropriate." limit="The first reading is not a validated baseline. Two endpoints cannot establish degradation, improvement, or a score contribution. Ganga’s 2025 summary covers January–October."/>
  </>;
}

function Distribution({ records }) {
  const values=records.map(r=>r.value);
  const min=values.reduce((a,b)=>Math.min(a,b)), max=values.reduce((a,b)=>Math.max(a,b));
  const size=min===max?1:Math.min(10,Math.ceil(Math.sqrt(values.length)));
  const step=(max-min)/size;
  const bins=Array.from({length:size},(_,i)=>({ range:step?fmt(min+i*step)+' to '+fmt(min+(i+1)*step):String(min), count:0 }));
  values.forEach(value=>bins[step?Math.min(size-1,Math.floor((value-min)/step)):0].count++);
  return <><div className="in-lab-chart"><ResponsiveContainer><BarChart data={bins}><XAxis dataKey="range"/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="count" name="Readings" fill={blue} isAnimationActive={false}/></BarChart></ResponsiveContainer></div>
    <Breakdown view="Measured value ranges and counts; units match the selected parameter." finding={values.length+' readings between '+min+' and '+max+'.'} purpose="Inspect the spread of observed readings." method="Equal-width bins over the observed range; intervals include the lower edge and the final bin includes the maximum." limit="Counts describe available readings only and depend on sampling frequency and bin width."/></>;
}

function Correlation({ rows }) {
  const [x,setX]=useState(''); const [y,setY]=useState('');
  const names=[...new Set(rows.map(label))];
  const a=names.includes(x)?x:names[0], b=names.includes(y)&&y!==a?y:names.find(n=>n!==a);
  const dates=new Map();
  rows.forEach(r=>{ const key=r.sampleKey==null?r.timestamp:'row:'+r.sampleKey; if(!dates.has(key))dates.set(key,new Map()); const group=dates.get(key); const n=label(r); group.set(n,group.has(n)?null:r.value); });
  const paired=(first,second)=>[...dates.values()].flatMap(g=>Number.isFinite(g.get(first))&&Number.isFinite(g.get(second))?[{x:g.get(first),y:g.get(second)}]:[]);
  function pearson(pairs) {
  const mx=average(pairs.map(p=>p.x)), my=average(pairs.map(p=>p.y));
  const denom=Math.sqrt(pairs.reduce((s,p)=>s+(p.x-mx)**2,0)*pairs.reduce((s,p)=>s+(p.y-my)**2,0));
    return pairs.length>=3&&denom ? pairs.reduce((s,p)=>s+(p.x-mx)*(p.y-my),0)/denom:null;
  }
  const pairs=paired(a,b), r=pearson(pairs);
  const matrix=[...new Set([a,b,...names.slice(0,6)].filter(Boolean))];
  return <Card title="Do any measured parameters vary together?" hint="Same archive sample or exact reported station timestamp">
    <p>{r === null ? 'A correlation needs at least three paired readings and variation in both parameters.' : `For the ${pairs.length} paired readings, Pearson r is ${r.toFixed(3)}. This describes linear association and does not show that one parameter causes the other to change.`}</p>
    {names.length>1 && <div className="in-lab-controls">{[[a,setX,'Horizontal'],[b,setY,'Vertical']].map(([v,set,axis])=><label key={axis}>{axis} <select value={v} onChange={e=>set(e.target.value)}>{names.filter(n=>axis==='Horizontal'||n!==a).map(n=><option key={n}>{n}</option>)}</select></label>)}</div>}
    {pairs.length ? <div className="in-lab-chart"><ResponsiveContainer><ScatterChart><CartesianGrid stroke="#dce7fa"/><XAxis type="number" dataKey="x" name={a} domain={['auto','auto']}/><YAxis type="number" dataKey="y" name={b} domain={['auto','auto']}/><Tooltip/><Scatter data={pairs} fill={blue} isAnimationActive={false}/></ScatterChart></ResponsiveContainer></div> : <Empty>No unambiguous paired readings.</Empty>}
    {matrix.length>1 && <details><summary>Correlation heatmap</summary><div className="in-table-wrap"><table><thead><tr><th>Pearson r</th>{matrix.map(n=><th key={n}>{n}</th>)}</tr></thead><tbody>{matrix.map(first=><tr key={first}><th scope="row">{first}</th>{matrix.map(second=>{
      const matched=paired(first,second), score=first===second?null:pearson(matched);
      return <td key={second}>{first===second?'—':<button type="button" style={{background:score===null?'#f3f8ff':'rgba(22,89,180,'+(0.08+0.28*Math.abs(score))+')'}} title={matched.length+' pairs'} aria-label={first+' versus '+second+', '+matched.length+' pairs, r '+(score?.toFixed(2)??'unavailable')} onClick={()=>{setX(first);setY(second);}}>{score?.toFixed(2)??'—'}</button>}</td>;
    })}</tr>)}</tbody></table></div></details>}
    <Breakdown view={a&&b?a+' vs '+b:'Select two measured parameters.'} finding={pairs.length+' pairs. Pearson r: '+(r===null?'unavailable':r.toFixed(3))+'.'} purpose="Explore linear association; correlation does not establish cause." method="Pearson correlation on complete pairs only, with at least three pairs and variation in both series." limit="Missing and duplicate readings within a pair are excluded. Small samples can be unstable; no statistical significance is inferred."/>
  </Card>;
}

function LaboratoryReview({ station, record }) {
  const cache = useQueryClient();
  const review = useMutation({
    mutationFn: payload => api.post(
      `/india/stations/${station.id}/evidence/laboratory/${record.id}/approval`, payload,
    ),
    onSuccess: () => cache.invalidateQueries({ queryKey: ['india'] }),
  });
  const approval = record.wqi_approval || review.data?.data?.wqi_approval;
  if (approval) return <p>Approved · {approval.report_reference} · Sample {approval.sample_id}</p>;
  return <details>
    <summary>Review for Water Health Score</summary>
    <form onSubmit={event => {
      event.preventDefault();
      review.mutate(Object.fromEntries(new FormData(event.currentTarget)));
    }}>
      <p>Check the original report for this station, sampling time, value, and unit before approving.</p>
      <label>Laboratory report reference <input name="report_reference" required minLength={4} maxLength={500}/></label>
      <label>Sample ID exactly as on report <input name="sample_id" required maxLength={160}/></label>
      <button type="submit" disabled={review.isPending}>Approve laboratory record</button>
      {review.isError && <p role="alert">{message(review.error)}</p>}
    </form>
  </details>;
}

export default function ContextLab({ data, station, site, archive, start, end, onLab, onContext }) {
  const [tab,setTab]=useState('overview');
  const [search,setSearch]=useState(''); const [lab,setLab]=useState(''); const [context,setContext]=useState(''); const [month,setMonth]=useState(null);
  const reduce=useReducedMotion();
  const location=site||station;
  const captured = (data?.observations || []).filter(r=>r.season).map(r=>({ timestamp:r.timestamp,season:r.season }));
  const rows=[...archiveRecords(site,archive),...(data?.laboratory||[]).map(r=>({...r,kind:'Laboratory'})),...(data?.context||[]).map(r=>({...r,kind:'Context'}))]
    .map(r=>({...r,value:valueOf(r.value)})).filter(r=>{
      const t=r.timestamp.slice(0,10), annual=t.length===4;
      return r.value!==null && (!start||t>=(annual?start.slice(0,4):start)) && (!end||t<=(annual?end.slice(0,4):end));
    }).sort((a,b)=>b.timestamp.localeCompare(a.timestamp));
  const environmental=rows.filter(r=>r.kind==='Context'||r.parameter.toLowerCase()==='temperature');
  const labs=rows.filter(r=>r.kind!=='Context');
  const labParameter=labs.some(r=>label(r)===lab)?lab:labs[0]&&label(labs[0]);
  const labValues=labs.filter(r=>label(r)===labParameter);
  const seasons=[...new Set([...rows,...captured].map(r=>r.season).filter(Boolean))];
  const dates=[...new Set(rows.filter(r=>r.timestamp.length>=10).map(r=>r.timestamp.slice(0,10)))];
  const months=Array.from({length:12},(_,i)=>({ name:new Date(Date.UTC(2000,i,1)).toLocaleString('en',{month:'short',timeZone:'UTC'}), days:dates.filter(d=>Number(d.slice(5,7))===i+1).length }));
  const visible=(tab==="lab"?labs:rows).filter(r=>(month===null||Number(r.timestamp.slice(5,7))===month+1)&&[label(r),r.timestamp,r.provenance,r.kind,r.notes].some(v=>String(v??'').toLowerCase().includes(search.toLowerCase())));
  const download=()=>{
    const field=v=>{const s=String(v??'');return '"'+(/^[\s]*[=+@-]/.test(s)&&typeof v!=='number'?"'"+s:s).replaceAll('"','""')+'"';};
    const csv=[['Location','Latitude','Longitude','Category','Parameter','Value','Unit','Reported time','Source','Paired observation','Notes'],...visible.map(r=>[location?.name,location?.latitude,location?.longitude,r.kind,r.parameter,r.value,r.unit,r.timestamp,r.provenance,r.observation_id,r.notes])].map(r=>r.map(field).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})); const a=document.createElement('a');a.href=url;a.download='aqualens-context-lab.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  return <motion.div className="in-lab-dashboard" initial={reduce?false:{opacity:0,y:6}} animate={{opacity:1,y:0}}>
    <nav className="in-lab-tabs" aria-label="Context and Lab views">
      {[['overview','Overview'],['lab','Lab Analysis'],['insights','Deep Insights']].map(([id,name])=><button key={id} type="button" aria-pressed={tab===id} onClick={()=>setTab(id)}>{name}</button>)}
    </nav>
    {tab === "overview" && <>
    <div className="in-lab-assessment">
      <Card title="River ecosystem health" hint={site?.name||station?.name||'Select a registered or archive station'}>
        <p>Use the measured evidence below to compare reporting periods, inspect historical variation, and explore a water-use reference.</p>
        <p>{labs.length} water-quality readings in the selected period. Each assessment applies to the selected location and documented records.</p>
      </Card>
      <Card title="Water Health Score" hint="Laboratory ecosystem assessment">
        <strong className="in-lab-score">Not Yet Available</strong>
        <p>No validated laboratory scoring method is configured for this station. Classification, score change, and assessment date are unavailable.</p>
        <details><summary>Why this score?</summary><p>A defensible 0–100 score needs an applicable reference, comparable measurements, documented normalization and weights, and a method validated for the intended assessment. Radar, contribution and waterfall charts require those inputs; the visual fingerprint score does not supply them.</p></details>
      </Card>
    </div>
    <Card title="What do we know about this location?" hint={site?.name||station?.name||'Select a registered or archive station'}>
      <dl className="in-lab-kpis">{[['Water-quality readings',labs.length],['Environmental readings',environmental.length],['Recorded seasons',seasons.join(', ')],['Latest reported period',rows[0]?.timestamp==='2025'?'2025 (Jan–Oct)':rows[0]?.timestamp]].map(([name,value])=><div key={name}><dt>{name}</dt><dd>{value === '' || value == null ? 'Unavailable' : value}</dd></div>)}</dl>
    </Card>
    <Card title="Historical health assessment" hint="Selected station and reporting period"><Empty>No validated laboratory health assessments are available to plot.</Empty></Card>
    {labValues.length>0 && <Card title="What changed in the selected period?" hint={labParameter}><MeasurementChange records={labValues}/></Card>}
    </>}
    {tab === "lab" && <>
    <Series title="What do the water quality measurements show?" rows={labs} selected={lab} choose={setLab}/>
    <Assessment records={labs}/>
    {labValues.length>0 && <Card title="How much has the selected measurement changed?" hint={labParameter}><MeasurementChange records={labValues}/></Card>}
    {labValues.length>0 && <Card title="How much do the readings vary?" hint={labParameter}>
      <Distribution records={labValues}/>
    </Card>}

    </>}
    {tab === "insights" && <>
    <Series title="How have environmental conditions changed?" rows={environmental} selected={context} choose={setContext}/>
    {labValues.some(r=>r.season) && <Card title="How do measurements differ by recorded season?" hint={labParameter}>
      <div className="in-table-wrap"><table><thead><tr>{['Recorded season','Readings','Mean','Minimum','Maximum'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>
        {seasons.map(season=>{
          const values=labValues.filter(r=>r.season===season).map(r=>r.value);
          return values.length?<tr key={season}><th scope="row">{season}</th><td>{values.length}</td><td>{fmt(average(values))}</td><td>{Math.min(...values)}</td><td>{Math.max(...values)}</td></tr>:null;
        })}
      </tbody></table></div>
      <Breakdown view="Selected water-quality parameter grouped by recorded season, in its source units." finding="The table shows the observed range and sample count for each represented season." purpose="Compare observed seasonal conditions before investigating unusual readings." method="Arithmetic means and observed extrema of the available records in each season." limit="Uneven sampling and short records cannot establish a seasonal baseline or identify anomalies."/>
    </Card>}
    <Card title="Can satellite and laboratory readings be compared?" hint="Satellite retrieval and direct measurements are separate evidence">
      <p>No CDOM records are available for this comparison. Satellite surface-water coverage describes the area covered by water; laboratory results describe properties measured in a collected sample.</p><p>A meaningful comparison needs a documented satellite retrieval and a relevant laboratory measurement from the same location and a comparable time window. The available records do not support that comparison.</p>
    </Card>
    {site?.values ? <Card title="Do any measured parameters vary together?"><Empty>Annual Ganga summaries are not paired sample records.</Empty></Card> : <Correlation rows={rows}/>}
    <Card title="Which months are represented in the data?" hint="Monthly sampling coverage across the selected years">
      {dates.length ? <><div className="in-lab-months">{months.map(({name,days},i)=><button type="button" key={name} title={name+': '+days+' sampling dates'} aria-pressed={month===i} style={{backgroundColor:'rgba(22,89,180,'+(0.05+0.25*days/Math.max(...months.map(m=>m.days)))+')'}} onClick={()=>setMonth(month===i?null:i)}>{name}<strong>{days}</strong></button>)}</div>
      <div className="in-lab-chart"><ResponsiveContainer><BarChart data={months}><XAxis dataKey="name" interval={1}/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="days" name="Distinct sampling dates" fill={blue} isAnimationActive={false}/></BarChart></ResponsiveContainer></div></> : <Empty>No dated samples are available for a monthly breakdown. Annual summaries cannot be assigned to individual months.</Empty>}
      <Breakdown view="Month of year and number of distinct sampling dates with reported data." finding={dates.length+' distinct dated records in the selected period.'} purpose="See which months are represented before comparing seasonal conditions." method="Count distinct recorded dates per calendar month across selected years. Select a month to filter the records table." limit="Counts reflect sampling effort, not environmental change. Recorded seasons are shown as supplied; no seasonal baseline is inferred."/>
    </Card>

    </>}
    {tab !== "overview" && <Card title="Where did these readings come from?" hint="Reported units and dates are preserved; archive measurements are labeled separately">
      <div className="in-lab-controls"><label>Search records <input value={search} onChange={e=>setSearch(e.target.value)}/></label><button type="button" onClick={download} className="in-button-outline" disabled={!visible.length}>Download CSV</button><button type="button" onClick={()=>window.print()} className="in-button-outline">Print / save PDF</button><button type="button" disabled={!station} onClick={onLab} className="in-button-outline">Add laboratory result</button><button type="button" disabled={!station} onClick={onContext} className="in-button-outline">Add context record</button></div>
      <p>{location?.name}{Number.isFinite(location?.latitude)&&Number.isFinite(location?.longitude) && ` · ${location.latitude}, ${location.longitude}`}</p><p>{visible.length} matching records{month!==null?' · '+months[month].name:''}.</p>
      {visible.length ? <div className="in-table-wrap"><table><thead><tr>{['Reported period','Category','Parameter','Value','Unit','Source','Pairing / notes'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{visible.map(r=><tr key={r.kind+':'+r.id}><td>{r.timestamp==='2025'?'2025 (Jan–Oct)':r.timestamp}</td><td>{r.kind}</td><th scope="row">{r.kind!=="Context"?<button type="button" className="in-text-button" onClick={()=>{setLab(label(r));setTab("lab");}}>{r.parameter}</button>:r.parameter}</th><td>{r.value}</td><td>{r.unit||'—'}</td><td>{r.provenance||'Not recorded'}{station && onLab && r.kind === 'Laboratory' && Number.isInteger(r.id) && <LaboratoryReview station={station} record={r}/>}</td><td>{[r.observation_id?'Sample #'+r.observation_id:null,r.notes].filter(Boolean).join(' · ')||'—'}</td></tr>)}</tbody></table></div> : <Empty>No evidence records match the current selection.</Empty>}
    </Card>}
  </motion.div>;
}

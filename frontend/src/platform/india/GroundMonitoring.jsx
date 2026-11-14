import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import { api, get, message } from '../api';
import { Card, Empty, SampleImage, date, title } from './shared';
import ContextLab from './ContextLab';
import './ground.css';

const recorded = value => typeof value === 'string' && value.trim() && !/not recorded/i.test(value);
const compatible = (a,b) => a && b && a.station_id===b.station_id && a.ground.location_status==='admin_verified' && b.ground.location_status==='admin_verified' && a.feature_extractor_version===b.feature_extractor_version && ['capture_protocol','camera','camera_settings','illumination','preparation'].every(k=>recorded(a[k])&&a[k]===b[k]);

export default function GroundMonitoring({ feed, officer, stations, river, state, stationId, start, end, view, onNavigate, onLab, onContext }) {
  const [selected,setSelected]=useState(null), [second,setSecond]=useState(''), [wipe,setWipe]=useState(50);
  const stationFor=o=>stations.find(s=>String(s.id)===String(o.station_id));
  const day=o=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(o.timestamp));
  const scope=(feed.data||[]).filter(o=>{const s=stationFor(o);const d=day(o);return s&&(!river||s.river===river)&&(!state||s.state===state)&&(!stationId||String(s.id)===stationId)&&(!start||d>=start)&&(!end||d<=end);});
  const rows=scope.filter(o=>!officer||String(o.ground.officer_id)===officer).sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp));
  const current=rows.find(o=>o.id===selected)||rows[0], other=rows.find(o=>String(o.id)===second&&o.id!==current?.id);
  const station=current?stationFor(current):stations.find(s=>String(s.id)===stationId);
  const evidence=useQuery({queryKey:['india','ground-detail',current?.id],enabled:!!current,queryFn:({signal})=>get('/india/ground/observations/'+current.id+'/analysis',undefined,signal)});
  const review=useMutation({mutationFn:id=>api.post('/india/ground/observations/'+id+'/verify-location'),onSuccess:()=>{feed.refetch();evidence.refetch();}});
  const classification = current?.classification;
  const votes = Object.entries(classification?.raw_probabilities || {})
    .filter(([, probability]) => Number.isFinite(probability))
    .map(([label, probability]) => ({ label, percent: probability * 100 }));
  const featureCount = Object.keys(current?.features || {}).length;
  const scoreReason = 'A validated station baseline and scoring method are required for a Water Health Score.';
  const comparison=current?.ground.location_status==='admin_verified'?evidence.data?.comparison:null;
  const differences=compatible(current,other)?Object.entries(current.features||{}).flatMap(([name,value])=>Number.isFinite(value)&&Number.isFinite(other.features?.[name])?[{name,value,previous:other.features[name],delta:value-other.features[name]}]:[]):[];
  const coords=current?[current.ground.latitude,current.ground.longitude]:[22.5,80.5];
  return <section className="in-ground" aria-label="Ground monitoring">
    {view==='evidence'?<><p>Lab and environmental records are for {station?.name||'the selected station'}. Image predictions are separate; no CDOM or lab value is inferred from photos.</p>{station && <Card title="Field sampling context">
      <div className="in-table-wrap"><table>
        <thead><tr><th>Captured (IST)</th><th>Officer</th><th>Latitude</th><th>Longitude</th><th>GPS accuracy</th></tr></thead>
        <tbody>{rows.filter(row => row.station_id === station.id).map(row => <tr key={row.id}>
          <td>{date(row.timestamp)}</td><td>{row.ground.officer}</td><td>{row.ground.latitude}°</td>
          <td>{row.ground.longitude}°</td><td>{row.ground.accuracy_m} m</td>
        </tr>)}</tbody>
      </table></div>
    </Card>}<ContextLab station={station} data={{ ...evidence.data, observations: rows.filter(row => row.station_id === station?.id) }} start={start} end={end} onLab={onLab} onContext={onContext}/></>:<>
    <div className="in-overview-kpis">{[['Field observations',rows.length],['Monitored stations',new Set(rows.filter(o=>o.ground.location_status==='admin_verified').map(o=>o.station_id)).size],['Analyzed samples',rows.filter(o=>o.processing_status==='completed').length],['Validated Water Health Scores','Unavailable']].map(([name,n])=><div className="in-overview-kpi" key={name}><div><strong>{feed.isSuccess?n:'—'}</strong>{name}</div></div>)}</div>
    <div className="in-ground-grid">
      {view==='overview'&&<Card title="Capture locations" hint="Markers show reported smartphone GPS, pending administrator verification where indicated."><MapContainer key={current?.id||'india'} center={coords} zoom={current?11:4} scrollWheelZoom={false} style={{height:380}}><TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors"/>{rows.map(o=><CircleMarker key={o.id} center={[o.ground.latitude,o.ground.longitude]} radius={o.id===current?.id?9:5} eventHandlers={{click:()=>setSelected(o.id)}}><Popup>{stationFor(o)?.name} · {date(o.timestamp)} IST</Popup></CircleMarker>)}</MapContainer></Card>}
      <Card title={view==='samples'?'Historical field samples':'Recent field observations'}><div className="in-ground-feed">{rows.length?rows.map(o=><article key={o.id}><button type="button" aria-pressed={o.id===current?.id} onClick={()=>setSelected(o.id)}>{stationFor(o)?.name} · #{o.id}</button><SampleImage observation={o} label="Original capture"/><p>{date(o.timestamp)} IST · {o.ground.officer} · {title(o.processing_status)}</p></article>):<Empty>{feed.isPending?'Loading field observations.':feed.isError?feed.error?.response?.status === 403 ? 'An India administrator account is required to view field uploads.' : message(feed.error):'No field uploads match these filters.'}</Empty>}</div></Card>
      <Card title={station?.name||'Observation preview'}>{current?<><SampleImage observation={current} label="Original smartphone capture"/><p>{station.river} · {station.state} · {date(current.timestamp)} IST</p><dl className="in-ground-metadata">
        <dt>Latitude</dt><dd>{current.ground.latitude}°</dd>
        <dt>Longitude</dt><dd>{current.ground.longitude}°</dd>
        <dt>GPS accuracy</dt><dd>{current.ground.accuracy_m} m</dd>
        <dt>Distance from station</dt><dd>{current.ground.distance_m} m</dd>
        <dt>Field officer</dt><dd>{current.ground.officer}</dd>
        <dt>Uploaded (IST)</dt><dd>{date(current.ground.uploaded_at)}</dd>
        <dt>Processing status</dt><dd>{title(current.processing_status)}</dd>
      </dl><p>{title(current.ground.location_status)} {current.ground.location_status!=='admin_verified'&&<button type="button" disabled={review.isPending} onClick={()=>review.mutate(current.id)}>Verify station match</button>}</p>{review.isError&&<p role="alert">Verification failed. Try again.</p>}<dl>
        <dt>Model classification</dt><dd>{classification?.predicted_condition || 'Unavailable'}</dd>
        <dt>Visual descriptors extracted</dt><dd>{featureCount}</dd>
        <dt>Water Health Score</dt><dd>Unavailable. {scoreReason}</dd>
      </dl>{current.processing_error && <p role="status">{current.processing_error}</p>}<button type="button" className="in-button-solid" onClick={()=>onNavigate(view==='findings'?'samples':'findings')}>{view==='findings'?'Compare historical samples':'Know more'}</button></>:<Empty>Select a field observation.</Empty>}</Card>
    </div>
    {current&&['findings','fingerprint','samples'].includes(view)&&<Card title={view==='samples'?'What changed?':'Visual evidence breakdown'}>
      {view==='samples'&&<><label>Compare with <select value={second} onChange={e=>setSecond(e.target.value)}><option value="">Select a second sample</option>{rows.filter(o=>o.id!==current.id).map(o=><option key={o.id} value={o.id}>#{o.id} · {date(o.timestamp)} IST</option>)}</select></label>
      {other&&<><label>Image reveal <input type="range" min="0" max="100" value={wipe} onChange={e=>setWipe(Number(e.target.value))}/></label><div className="in-ground-wipe"><SampleImage observation={current} label="Selected sample"/><div style={{clipPath:'inset(0 '+(100-wipe)+'% 0 0)'}}><SampleImage observation={other} label="Comparison sample"/></div></div></>}
      {other&&!differences.length&&<p>Numeric comparison requires verified samples from the same station, with matching extraction and acquisition settings.</p>}</>}
      {view === 'findings' && votes.length > 0 && <div>
        <h3>Model votes by visual condition</h3>
        <ResponsiveContainer width="100%" height={255}>
          <BarChart data={votes}>
            <CartesianGrid strokeDasharray="3 3" vertical={false}/>
            <XAxis dataKey="label"/>
            <YAxis domain={[0, 100]} unit="%"/>
            <Tooltip formatter={value => [`${Number(value).toFixed(1)}%`, 'Tree votes']}/>
            <Bar dataKey="percent" fill="#1759ad" radius={[6, 6, 0, 0]}/>
          </BarChart>
        </ResponsiveContainer>
      </div>}
      {classification && <details open={view==='findings'}>
        <summary>Random Forest model results</summary>
        <p>Predicted visual condition: <strong>{classification.predicted_condition}</strong></p>
        <p>Model version: {classification.model_version || 'Not recorded'}</p>
        <ul>{Object.entries(classification.raw_probabilities || {}).map(([label, probability]) =>
          <li key={label}>{label}: {(probability * 100).toFixed(1)}% of tree votes</li>
        )}</ul>
        <p>{classification.probability_note}</p>
        <p>{classification.disclaimer}</p>
      </details>}
      {evidence.isError && <p role="status">Reference analysis could not be loaded.</p>}
      {!featureCount && <Empty>No visual descriptors are available for this capture.</Empty>}
      <p>Fingerprint comparison: {comparison?title(comparison.status):'Unavailable until location and a compatible reference are available'}.</p>
      <div className="in-table-wrap"><table><thead><tr><th>Descriptor</th><th>Selected value</th>{differences.length>0&&<><th>Comparison value</th><th>Signed change</th></>}<th>Reference median</th><th>Signed IQR deviation</th></tr></thead><tbody>{Object.entries(current.features||{}).map(([name,value])=>{const f=comparison?.features?.find(item=>item.name===name), d=differences.find(item=>item.name===name);return <tr key={name}><th scope="row">{title(name)}</th><td>{value}</td>{differences.length>0&&<><td>{d?.previous??'—'}</td><td>{d?.delta.toPrecision(5)??'—'}</td></>}<td>{f?.baseline?.median??'—'}</td><td>{f?.normalized_deviation??'—'}</td></tr>;})}</tbody></table></div>
      <details><summary>Understand this</summary><p>Signed change subtracts the comparison value from the selected value. Descriptor units differ; raw distances across features would be misleading. A reference departure describes a visual difference, not chemical quality or safety. The classifier does not currently provide local feature attributions.</p></details>
    </Card>}
    </>}
  </section>;
}

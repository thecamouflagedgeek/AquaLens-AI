import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import { api, get, message } from '../api';
import { Card, Empty, SampleImage, date, title } from './shared';
import ContextLab from './ContextLab';
import './ground.css';

const recorded = value => typeof value === 'string' && value.trim() && !/not recorded/i.test(value);
const compatible = (a,b) => a && b && a.station_id===b.station_id && a.ground.location_status==='admin_verified' && b.ground.location_status==='admin_verified' && a.feature_extractor_version && a.feature_extractor_version===b.feature_extractor_version && ['capture_protocol','camera','camera_settings','illumination','preparation'].every(k=>recorded(a[k])&&a[k]===b[k]);

export default function GroundMonitoring({ feed, officer, stations, river, state, stationId, start, end, view, onNavigate, onLab, onContext }) {
  const [selected,setSelected]=useState(null), [second,setSecond]=useState(''), [wipe,setWipe]=useState(50);
  const [descriptor, setDescriptor] = useState('');
  const stationFor=o=>stations.find(s=>String(s.id)===String(o.station_id));
  const day=o=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(o.timestamp));
  const scope=(feed.data||[]).filter(o=>{const s=stationFor(o);const d=day(o);return s&&(!river||s.river===river)&&(!state||s.state===state)&&(!stationId||String(s.id)===stationId)&&(!start||d>=start)&&(!end||d<=end);});
  const rows=scope.filter(o=>!officer||String(o.ground.officer_id)===officer).sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp));
  const current=rows.find(o=>o.id===selected)||rows[0], other=rows.find(o=>String(o.id)===second&&o.id!==current?.id);
  const station=current?stationFor(current):stations.find(s=>String(s.id)===stationId);
  const evidence=useQuery({queryKey:['india','ground-detail',current?.id,'descriptor-deviations'],enabled:!!current,queryFn:({signal})=>get('/india/ground/observations/'+current.id+'/analysis',{ schema: 'descriptor-deviations' },signal)});
  const review=useMutation({mutationFn:id=>api.post('/india/ground/observations/'+id+'/verify-location'),onSuccess:()=>{feed.refetch();evidence.refetch();}});
  const classification = current?.classification;
  const votes = Object.entries(classification?.raw_probabilities || {})
    .filter(([, probability]) => Number.isFinite(probability))
    .map(([label, probability]) => ({ label, percent: probability * 100 }));
  const featureCount = Object.keys(current?.features || {}).length;
  const comparison=current?.ground.location_status==='admin_verified'?evidence.data?.comparison:null;
  const explanation = useQuery({
    queryKey: ['india', 'ground-explanation', current?.id, current?.ground.location_status, evidence.data?.reference?.id],
    enabled: view === 'findings' && !!current && evidence.isSuccess,
    queryFn: async ({ signal }) => (await api.post(
      `/india/ground/observations/${current.id}/explanation`, undefined, { signal },
    )).data.explanation,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const nearbyReference = evidence.data?.nearby_reference;
  const usingUieb = !Number.isFinite(comparison?.visual_stability_score) && !nearbyReference && !!evidence.data?.uieb_comparison;
  const stabilityScore = usingUieb ? evidence.data.uieb_comparison.score : (comparison?.visual_stability_score ?? nearbyReference?.score);
  const stabilitySource = usingUieb
    ? `UIEB benchmark · ${evidence.data.uieb_comparison.sample_count} underwater images`
    : nearbyReference
      ? `Cross-station comparison · ${nearbyReference.station_name} · ${nearbyReference.distance_m.toLocaleString()} m away`
      : 'Exploratory station comparison';
  const activeReference = usingUieb ? evidence.data.uieb_comparison : nearbyReference || comparison;
  const nearestStation = evidence.data?.nearest_station ?? (current && stations.reduce((closest, site) => {
    const { latitude, longitude } = current.ground;
    if (![latitude, longitude, site.latitude, site.longitude].every(Number.isFinite)) return closest;
    const radians = value => value * Math.PI / 180;
    const h = Math.sin(radians(site.latitude - latitude) / 2) ** 2
      + Math.cos(radians(latitude)) * Math.cos(radians(site.latitude))
      * Math.sin(radians(site.longitude - longitude) / 2) ** 2;
    const distance_m = 12742000 * Math.asin(Math.sqrt(Math.min(1, h)));
    return !closest || distance_m < closest.distance_m ? { name: site.name, distance_m } : closest;
  }, null));
  const deviations = (activeReference?.features || [])
    .filter(feature => Number.isFinite(feature.normalized_deviation))
    .map(feature => ({ name: title(feature.name), deviation: feature.normalized_deviation }));
  const stabilityReason = current?.ground.location_status !== 'admin_verified'
    ? 'Verify the capture location first.'
    : evidence.isError ? 'Reference analysis could not be loaded.'
    : evidence.isPending ? 'Loading reference analysis.'
    : ({
      reference_sample: 'This observation belongs to the reference set.',
      context_mismatch: 'The capture conditions differ from the station reference.',
      undefined_feature_scale: 'The reference cannot scale every visual descriptor.',
    }[comparison?.status] || 'No compatible station reference is available for this capture.');
  const differences=compatible(current,other)?Object.entries(current.features||{}).flatMap(([name,value])=>Number.isFinite(value)&&Number.isFinite(other.features?.[name])?[{name,value,previous:other.features[name],delta:value-other.features[name]}]:[]):[];
  const sampleLabel = row => `#${row.id} · ${stationFor(row)?.name || 'Field station'} · ${date(row.timestamp)} IST`;
  const empty = feed.isPending ? 'Loading field observations…'
    : feed.isError ? message(feed.error) : 'No field observations match the current filters.';
  const observationPicker = current && <label className="in-ground-control">Observation
    <select value={current.id} onChange={event => setSelected(Number(event.target.value))}>
      {rows.map(row => <option key={row.id} value={row.id}>{sampleLabel(row)}</option>)}
    </select>
  </label>;
  const score = Number.isFinite(stabilityScore) ? `${stabilityScore.toFixed(1)} / 100` : 'Unavailable';

  if (view === 'findings') return <section className="in-ground in-ground-workspace" aria-label="Ground findings">
    <div className="in-ground-heading"><div><h2>Findings</h2><p>Interpret the model output for a field observation.</p></div>{observationPicker}</div>
    {current ? <>
      <div className="in-ground-findings">
        <Card title="Visual classification" hint={classification?.model_version}>
          <strong className="in-ground-value">{classification?.predicted_condition || 'Unavailable'}</strong>
          {current.processing_error && <p>{current.processing_error}</p>}
          {classification?.disclaimer && <p>{classification.disclaimer}</p>}
        </Card>
        <Card title="Visual Stability Score" hint={stabilitySource}>
          <strong className="in-ground-value">{score}</strong>
          {!Number.isFinite(stabilityScore) && <p>{stabilityReason}</p>}
          <button className="in-button-outline" type="button" onClick={() => onNavigate('fingerprint')}>Inspect station reference</button>
        </Card>
      </div>
      <div className="in-ground-findings">
        <Card title="Random Forest votes" hint="Raw tree votes, uncalibrated">
          {votes.length ? <ResponsiveContainer width="100%" height={245}>
            <BarChart data={votes}><CartesianGrid strokeDasharray="3 3" vertical={false}/>
              <XAxis dataKey="label"/><YAxis domain={[0, 100]} unit="%"/>
              <Tooltip formatter={value => [`${Number(value).toFixed(1)}%`, 'Tree votes']}/>
              <Bar dataKey="percent" fill="#2874bf" radius={[6, 6, 0, 0]}/>
            </BarChart>
          </ResponsiveContainer> : <Empty>No model votes are available.</Empty>}
        </Card>
        <Card title="Observation breakdown">
          <dl className="in-ground-metadata">
            <dt>Capture</dt><dd>{sampleLabel(current)}</dd>
            <dt>Field officer</dt><dd>{current.ground.officer}</dd>
            <dt>GPS coordinates</dt><dd>{current.ground.latitude}°, {current.ground.longitude}°</dd>
            <dt>GPS accuracy</dt><dd>±{current.ground.accuracy_m.toFixed(1)} m</dd>
            <dt>Distance from station</dt><dd>{current.ground.distance_m} m</dd>
            <dt>Location review</dt><dd>{title(current.ground.location_status)}</dd>
            <dt>Visual descriptors extracted</dt><dd>{featureCount}</dd>
            <dt>Model version</dt><dd>{classification?.model_version || 'Not recorded'}</dd>
          </dl>
          {votes.length > 0 && <details open>
            <summary>Model votes by class</summary>
            <dl className="in-ground-metadata">{votes.map(({ label, percent }) =>
              <div key={label}><dt>{label}</dt><dd>{percent.toFixed(1)}%</dd></div>
            )}</dl>
            <p>The percentages are raw Random Forest votes. The classification describes the image’s visual appearance.</p>
          </details>}
          {explanation.data ? <p className="in-ground-explanation">{explanation.data}</p> : <>
            <p>{classification?.predicted_condition
              ? `The model classified this capture as ${classification.predicted_condition}. The chart shows raw tree votes.`
              : 'A visual classification is unavailable for this capture.'}</p>
            <p>{Number.isFinite(stabilityScore) ? `Visual stability: ${score} · ${stabilitySource}.` : stabilityReason}</p>
            {(explanation.isFetching || evidence.isPending) && <p role="status">Preparing a detailed explanation…</p>}
          </>}
        </Card>
      </div>
    </> : <Empty>{empty}</Empty>}
  </section>;

  const descriptors = [...new Set([...Object.keys(current?.features || {}), ...Object.keys(other?.features || {})])];
  const activeDescriptor = descriptors.includes(descriptor) ? descriptor : descriptors[0];
  const descriptorValues = [current, other].filter(Boolean).flatMap(row => {
    const value = row.features?.[activeDescriptor];
    return Number.isFinite(value) ? [{ capture: `Capture #${row.id}`, value }] : [];
  });
  const formatDescriptor = value => Number.isFinite(value)
    ? Number(value.toPrecision(6)).toString() : '—';

  if (view === 'samples') return <section className="in-ground in-ground-workspace" aria-label="Ground samples">
    <div className="in-ground-heading"><div><h2>Samples</h2><p>Browse original field photographs and compare captures.</p></div></div>
    {current ? <div className="in-ground-samples">
      <Card title="Capture library" hint={`${rows.length} matching observations`}>
        <div className="in-ground-gallery">{rows.map(row => <button key={row.id} type="button"
          aria-pressed={row.id === current.id} onClick={() => setSelected(row.id)}>
          <SampleImage observation={row} label={stationFor(row)?.name || 'Field capture'}/>
          <span>#{row.id} · {row.ground.officer}</span>
        </button>)}</div>
      </Card>
      <Card title={sampleLabel(current)} hint={`${current.ground.officer} · ${title(current.ground.location_status)}`}>
        <label className="in-ground-control">Compare with
          <select value={other?.id || ''} onChange={event => setSecond(event.target.value)}>
            <option value="">Choose another capture</option>
            {rows.filter(row => row.id !== current.id).map(row => <option key={row.id} value={row.id}>{sampleLabel(row)}</option>)}
          </select>
        </label>
        {other ? <>
          <label className="in-ground-control">Image reveal
            <input type="range" min="0" max="100" value={wipe} onChange={event => setWipe(Number(event.target.value))}/>
          </label>
          <div className="in-ground-wipe"><SampleImage observation={current} label={`Capture #${current.id}`}/>
            <div style={{clipPath: `inset(0 ${100 - wipe}% 0 0)`}}><SampleImage observation={other} label={`Capture #${other.id}`}/></div>
          </div>
          {!differences.length && <p>Signed changes require verified station matches and documented, matching capture and extraction settings.</p>}
        </> : <SampleImage observation={current} label="Original capture"/>}
        <p>{current.ground.latitude}°, {current.ground.longitude}° · GPS ±{formatDescriptor(Math.round(current.ground.accuracy_m * 10) / 10)} m</p>
      </Card>
      <Card className="in-ground-descriptor-panel" title="Visual descriptor comparison"
        hint="Image-derived values for the selected captures">
        {descriptors.length ? <>
          <label className="in-ground-control">Chart descriptor
            <select value={activeDescriptor} onChange={event => setDescriptor(event.target.value)}>
              {descriptors.map(name => <option key={name} value={name}>{title(name)}</option>)}
            </select>
          </label>
          {descriptorValues.length ? <ResponsiveContainer width="100%" height={210}>
            <BarChart data={descriptorValues} layout="vertical">
              <CartesianGrid strokeDasharray="3 3"/>
              <XAxis type="number" tickFormatter={formatDescriptor}/>
              <YAxis type="category" dataKey="capture" width={90}/>
              <ReferenceLine x={0} stroke="#667e99"/>
              <Tooltip formatter={value => [formatDescriptor(value), title(activeDescriptor)]}/>
              <Bar dataKey="value" fill="#2874bf" barSize={22}/>
            </BarChart>
          </ResponsiveContainer> : <Empty>No finite readings for this descriptor.</Empty>}
          <div className="in-table-wrap"><table className="in-ground-comparison-table">
            <thead><tr><th scope="col">Descriptor</th><th scope="col">Capture #{current.id}</th>
              {other && <th scope="col">Capture #{other.id}</th>}
              {other && <th scope="col">Signed change</th>}
            </tr></thead>
            <tbody>{descriptors.map(name => {
              const delta = differences.find(item => item.name === name)?.delta;
              return <tr key={name} className={name === activeDescriptor ? 'is-selected' : undefined}>
                <th scope="row"><button type="button" aria-pressed={name === activeDescriptor}
                  onClick={() => setDescriptor(name)}>{title(name)}</button></th>
                <td>{formatDescriptor(current.features?.[name])}</td>
                {other && <td>{formatDescriptor(other.features?.[name])}</td>}
                {other && <td>{delta > 0 ? '+' : ''}{formatDescriptor(delta)}</td>}
              </tr>;
            })}</tbody>
          </table></div>
          {other && <p>{differences.length ? `Signed change = capture #${current.id} minus capture #${other.id}.`
            : 'Values are shown as recorded. Signed changes are unavailable until the captures meet the comparison requirements.'}</p>}
        </> : <Empty>No extracted descriptors are available.</Empty>}
      </Card>
    </div> : <Empty>{empty}</Empty>}
  </section>;

  if (view === 'fingerprint') return <section className="in-ground in-ground-workspace" aria-label="Ground fingerprints">
    <div className="in-ground-heading"><div><h2>Fingerprints</h2><p>Evaluate each observation against its station’s frozen visual reference.</p></div>{observationPicker}</div>
    {current ? <div className="in-ground-reference">
      <Card title="Station reference" hint={station?.name}>
        {station?.name.trim().toLowerCase() === 'mumbai' && <details open>
          <summary>Mumbai tap-water evidence</summary>
          <p><strong>2019 BIS survey:</strong> All 10 Mumbai piped-water samples conformed on the 44 parameters reported. <a href="https://bis.gov.in/wp-content/uploads/2019/11/Drinking_Water_20112019.pdf" target="_blank" rel="noreferrer">BIS report</a> · <a href="https://www.dnaindia.com/india/report-bis-study-mumbai-tops-ranking-for-quality-of-tap-water-delhi-lowest-2801970" target="_blank" rel="noreferrer">DNA coverage</a></p>
          <p><strong>May 2022, Bhakti Park, Wadala:</strong> Mid-Day reported private lab detections of E. coli and coliform in local samples. <a href="https://www.mid-day.com/mumbai/mumbai-news/article/mumbai-residents-suffering-due-to-dirty-water-but-bmc-is-doing-nothing-to-help-23227618" target="_blank" rel="noreferrer">Mid-Day report</a></p>
          <p><strong>17–18 October 2024:</strong> BMC announced a 5–10% supply cut for repairs on the Vaitarna network. <a href="https://www.indiatvnews.com/maharashtra/mumbai-bmc-announces-5-to-10-per-cent-water-cut-on-october-17-and-18-brihanmumbai-municipal-corporation-vaitarna-pipeline-latest-updates-2024-10-16-957520" target="_blank" rel="noreferrer">India TV coverage</a> · <a href="https://indianexpress.com/article/cities/mumbai/bmc-announces-5-10-percent-water-cut-throughout-mumbai-for-october-17-18-9623927/" target="_blank" rel="noreferrer">Indian Express report</a></p>
          <p>These reports give historical context. The gauge identifies whether it uses a station reference or the UIEB benchmark.</p>
        </details>}
        <dl className="in-ground-metadata">
          <dt>Nearest registered station</dt>
          <dd>{nearestStation ? `${nearestStation.name} · ${Math.round(nearestStation.distance_m)} m from capture` : 'Unavailable'}</dd>
          <dt>Location review</dt><dd>{title(current.ground.location_status)}</dd>
          <dt>Screening status</dt><dd>{comparison ? title(comparison.status) : 'Unavailable'}</dd>
          <dt>Reference images</dt><dd>{(usingUieb ? activeReference.sample_count : nearbyReference?.sample_count ?? evidence.data?.reference?.sample_count) ?? 'No compatible station reference'}</dd>
          <dt>Comparable descriptors</dt><dd>{activeReference?.comparable_features ?? 'Awaiting reference'}</dd>
        </dl>
        <div className="in-stability-gauge">
          <h3>Visual Stability Score</h3>
          <div className="in-stability-dial" aria-hidden="true"
            style={{ '--stability-sweep': Number.isFinite(stabilityScore) ? `${stabilityScore * 1.8}deg` : '0deg' }}>
            <strong>{score}</strong>
          </div>
          {nearbyReference && <p>This comparison uses a nearby station’s visual reference.</p>}
          {usingUieb && <p>Image similarity to an underwater benchmark. Lighting, framing and the sample container can influence the score.</p>}
          <div className="in-stability-scale" aria-hidden="true"><span>0</span><span>100</span></div>
          <p>{Number.isFinite(stabilityScore) ? `${score} · ${stabilitySource}` : stabilityReason}</p>
        </div>
        {current.ground.location_status !== 'admin_verified' && <button type="button" className="in-button-outline"
          disabled={review.isPending} onClick={() => review.mutate(current.id)}>Verify station match</button>}
        {review.isError && <p role="alert">{message(review.error)}</p>}
        <details><summary>How stability is calculated</summary><p>{comparison?.limitations || 'AquaLens scales deviations from the reference medians by the reference interquartile ranges. A score requires a complete set of comparable descriptors.'}</p></details>
      </Card>
      <Card title="Deviation from reference" hint={`${stabilitySource} · Signed interquartile-range units`}>
        {deviations.length ? <ResponsiveContainer width="100%" height={Math.max(240, deviations.length * 27)}>
          <BarChart data={deviations} layout="vertical">
            <CartesianGrid strokeDasharray="3 3"/><XAxis type="number"/>
            <YAxis type="category" dataKey="name" width={125} interval={0}/>
            <ReferenceLine x={0} stroke="#667e99"/>
            <Tooltip formatter={value => [Number(value).toFixed(3), 'Signed IQR deviation']}/>
            <Bar dataKey="deviation" fill="#2874bf"/>
          </BarChart>
        </ResponsiveContainer> : <Empty>{evidence.isFetching ? 'Loading descriptor deviations…' : evidence.isError ? message(evidence.error)
          : Number.isFinite(stabilityScore) ? 'The connected API returned a score without descriptor data.' : stabilityReason}
          {(evidence.isError || Number.isFinite(stabilityScore)) && <button type="button" className="in-button-outline"
            disabled={evidence.isFetching} onClick={() => evidence.refetch()}>Reload analysis</button>}
        </Empty>}
      </Card>
    </div> : <Empty>{empty}</Empty>}
  </section>;

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
        <dt>Water Health Score</dt><dd>Unavailable without a validated health assessment.</dd>
        <dt>Visual Stability Score</dt><dd>{Number.isFinite(stabilityScore)
          ? `${stabilityScore.toFixed(1)} / 100 · ${stabilitySource}`
          : stabilityReason}</dd>
      </dl>{current.processing_error && <p role="status">{current.processing_error}</p>}<button type="button" className="in-button-solid" onClick={()=>onNavigate(view==='findings'?'samples':'findings')}>{view==='findings'?'Compare historical samples':'Know more'}</button></>:<Empty>Select a field observation.</Empty>}</Card>
    </div>
    </>}
  </section>;
}

import { useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Area, Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, Empty, date, number, title, Status, ViewButton } from './shared';
import './findings.css';

const palette = ['#1659b4', '#007e94'];
const numeric = value => value == null || String(value).trim() === '' ? null : Number.isFinite(Number(value)) ? Number(value) : null;
const inPeriod = (day, start, end) => (!start || day >= start) && (!end || day <= end);

function measurements(site, archive, data, start, end) {
  if (site?.values) {
    return site.values.map((value, i) => ({ parameter: i < 4 ? 'DO (mg/L)' : 'BOD (mg/L)', time: String(2022 + i % 4), value: numeric(value) }))
      .filter(row => (!start || row.time >= start.slice(0, 4)) && (!end || row.time <= end.slice(0, 4)));
  }
  if (site?.observations) {
    const headers = archive.headers || ['pH', 'DO (mg/L)', 'TDS (mg/L)'];
    return site.observations.filter(row => inPeriod(row[0].slice(0, 10), start, end))
      .flatMap(row => headers.map((parameter, i) => ({ parameter, time: row[0], value: numeric(row[i + 2]), record: row[1] })));
  }
  return (data?.laboratory || []).filter(row => inPeriod(row.timestamp.slice(0, 10), start, end))
    .map(row => ({ parameter: [row.parameter, row.unit].filter(Boolean).join(' · '), time: row.timestamp, value: numeric(row.value), record: row.id, provenance: row.provenance }));
}

function Trend({ rows, name, color, area }) {
  const points = rows.filter(row => row.parameter === name).sort((a, b) => a.time.localeCompare(b.time))
    .map(row => ({ ...row, instant: Date.parse(row.time) })).filter(row => Number.isFinite(row.instant));
  if (!points.some(row => row.value !== null)) return null;
  const stamp = instant => new Date(instant).toISOString().slice(0, points[0].time.length === 4 ? 4 : 10);
  return <figure className="in-findings-figure"><figcaption>{name}</figcaption><div className="in-findings-chart"><ResponsiveContainer>
    <ComposedChart data={points} margin={{ right: 18 }}>
      <CartesianGrid stroke="#e0eaf7" vertical={false}/><XAxis type="number" scale="time" domain={['dataMin', 'dataMax']} dataKey="instant" tickFormatter={stamp} minTickGap={20}/><YAxis domain={['auto', 'auto']} width={64}/>
      <Tooltip labelFormatter={(_, payload) => {
        const point = payload?.[0]?.payload;
        return point ? [point.time, point.provenance].filter(Boolean).join(' · ') : '';
      }} />
      {area ? <Area dataKey="value" name={name} stroke={color} fill={color} fillOpacity={0.13} dot isAnimationActive={false}/> : <Line dataKey="value" name={name} stroke={color} dot isAnimationActive={false}/>}
    </ComposedChart>
  </ResponsiveContainer></div></figure>;
}

function EnvironmentalContext({ site, archive, data, rows, parameter, start, end }) {
  const rain = rows.filter(row => row.parameter === 'rainfall(mm)' && row.value !== null);
  const contextualRows = (data?.context || []).filter(row => inPeriod(row.timestamp.slice(0, 10), start, end));
  const siteRain = contextualRows.filter(row => row.parameter.trim().toLowerCase() === 'rainfall' && row.unit.trim().toLowerCase() === 'mm' && numeric(row.value) !== null);
  const pairs = site
    ? rain.flatMap(r => rows.filter(row => row.record === r.record && row.parameter === parameter && row.value !== null).map(row => ({ value: row.value, rainfall: r.value, time: row.time })))
    : siteRain.flatMap(r => rows.filter(row => Date.parse(row.time) === Date.parse(r.timestamp) && row.parameter === parameter && row.value !== null).map(row => ({ value: row.value, rainfall: numeric(r.value), time: row.time })));
  const seasonIndex = archive.headers?.indexOf('season') ?? -1;
  const seasons = seasonIndex < 0 ? [] : [...new Set((site?.observations || []).filter(row => inPeriod(row[0].slice(0, 10), start, end)).map(row => row[seasonIndex + 2]).filter(Boolean))];
  return <Card title="Environmental context" hint="Paired observations show association, not cause">
    {seasons.length > 0 && <p>Seasons recorded in this period: {seasons.join(', ')}.</p>}
    {pairs.length ? <><p>{pairs.length} {site ? 'same-record' : 'same-timestamp'} pairs: rainfall (mm) and {parameter}.</p><div className="in-findings-chart"><ResponsiveContainer><ScatterChart>
      <CartesianGrid stroke="#e0eaf7"/><XAxis type="number" dataKey="rainfall" name="Rainfall" unit=" mm"/><YAxis type="number" dataKey="value" name={parameter} domain={['auto', 'auto']}/><Tooltip labelFormatter={(_, points) => points?.[0]?.payload.time}/><Scatter data={pairs} fill={palette[1]} isAnimationActive={false}/>
    </ScatterChart></ResponsiveContainer></div></> : <Empty>No paired rainfall readings for the selected parameter and dates.</Empty>}
    {contextualRows.length > 0 && <details><summary>Recorded station context ({contextualRows.length})</summary><ul>{contextualRows.map(row => <li key={row.id}>{date(row.timestamp)} IST · {row.parameter}: {row.value} {row.unit} · {row.provenance || 'Source not recorded'}</li>)}</ul></details>}
  </Card>;
}

export default function FindingsDashboard({ sites, site, station, archive, gangaSource, data, start, end, onSelect, onObservation, exportReport, busy, children }) {
  const reducedMotion = useReducedMotion();
  const [primary, setPrimary] = useState('');
  const [secondary, setSecondary] = useState('');
  const [area, setArea] = useState(false);
  const [descriptor, setDescriptor] = useState('');
  const current = data?.current;
  const comparison = data?.comparison;
  const reference = data?.reference;
  const rows = measurements(site, archive, data, start, end);
  const parameters = [...new Set(rows.filter(row => row.value !== null && row.parameter !== 'rainfall(mm)').map(row => row.parameter))];
  const parameter = parameters.includes(primary) ? primary : (parameters.includes('pH') ? 'pH' : parameters[0]);
  const compareParameter = parameters.includes(secondary) && secondary !== parameter ? secondary : '';
  const screened = (data?.timeline || []).filter(row => Number.isFinite(row.anomaly_score));
  const flagged = screened.filter(row => row.status === 'potential_anomaly');
  const features = (comparison?.features || []).filter(f => Number.isFinite(f.normalized_deviation)).sort((a, b) => Math.abs(b.normalized_deviation) - Math.abs(a.normalized_deviation));
  const feature = features.find(f => f.name === descriptor) || features[0];
  const history = (data?.timeline || []).map(row => ({ timestamp: row.timestamp, value: row.feature_deviations?.[feature?.name] ?? null }));
  const latest = [data?.observations?.[0]?.timestamp, ...rows.filter(row => row.value !== null).map(row => row.time)].filter(Boolean).sort().at(-1);
  const source = site?.values ? gangaSource : site ? archive.source : 'AquaLens station records';
  return <motion.div className="in-findings" initial={reducedMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.24 }}>
    <Card title="Findings overview" hint={site?.name || station?.name || 'Select a station from the filters'} action={<button type="button" className="in-button-solid in-findings-print" onClick={() => window.print()}>Print / save PDF</button>}>
      <dl className="in-findings-kpis">
        <div><dt>Flagged observations</dt><dd>{screened.length ? flagged.length : 'Unavailable'}</dd><small>{screened.length ? `Among ${screened.length} independently scored observations` : 'No independent visual screening results'}</small></div>
        <div><dt>Locations in selection</dt><dd>{sites.length}</dd><small>Registered and historical records matching filters</small></div>
        <div><dt>Latest record in period</dt><dd>{latest?.length > 10 && !site ? date(latest) + ' IST' : latest?.slice(0, 10) || 'Unavailable'}</dd><small>{site?.values && latest === '2025' ? 'January–October 2025 summary' : source}</small></div>
        <div><dt>Data confidence</dt><dd>Not validated</dd><small>{reference ? `${reference.sample_count} reference samples · exploratory comparison` : 'No validated confidence estimate available'}</small></div>
      </dl>
    </Card>
    <Card title="Water quality trends" hint="Measured records only. Comparison panels use separate axes.">
      <p>Source: {source}. Satellite-derived CDOM: unavailable; surface-water coverage is a separate product.</p>
      {site?.values && <p>Annual summaries, not dated samples. Date filters select reporting years; 2025 covers January–October only.</p>}
      {parameter ? <><div className="in-findings-controls">
        <label>Parameter<select value={parameter} onChange={e => setPrimary(e.target.value)}>{parameters.map(name => <option key={name}>{name}</option>)}</select></label>
        <label>Compare with<select value={compareParameter} onChange={e => setSecondary(e.target.value)}><option value="">No comparison</option>{parameters.filter(name => name !== parameter).map(name => <option key={name}>{name}</option>)}</select></label>
        <label>Chart style<select value={area ? 'area' : 'line'} onChange={e => setArea(e.target.value === 'area')}><option value="line">Line</option><option value="area">Area</option></select></label>
      </div><Trend rows={rows} name={parameter} color={palette[0]} area={area}/>{compareParameter && <Trend rows={rows} name={compareParameter} color={palette[1]} area={area}/>}</> : <Empty>No measured parameter readings are available for this station and period.</Empty>}
    </Card>
    <Card title="Anomaly breakdown" hint="Source-specific visual screening · mean absolute deviation in reference IQR units">
      {screened.length ? <><div className="in-findings-chart"><ResponsiveContainer><ComposedChart data={data.timeline}>
        <CartesianGrid stroke="#e0eaf7"/><XAxis dataKey="timestamp" tickFormatter={value => value.slice(0, 10)} minTickGap={22}/><YAxis/><Tooltip labelFormatter={value => date(value) + ' IST'}/><Legend/>
        {Number.isFinite(comparison?.threshold) && <ReferenceLine y={comparison.threshold} label="Screening threshold" stroke="#86531e" strokeDasharray="4 3"/>}
        <Line dataKey="anomaly_score" name="Deviation index" stroke={palette[0]} dot isAnimationActive={false}/>
      </ComposedChart></ResponsiveContainer></div>
      <div className="in-findings-list">{flagged.map(row => <details key={row.id}><summary>Sample #{row.id} · {date(row.timestamp)} IST · <Status value={row.status}/></summary>
        <p>{station?.name} · Mean absolute deviation: {number(row.anomaly_score)} IQR. The sample crossed the reference screening threshold. This flag supports follow-up on a visual departure; it does not identify a cause.</p>
        <ul>{Object.entries(row.feature_deviations || {}).filter(([, value]) => Number.isFinite(value)).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 4).map(([name, value]) => <li key={name}>{title(name)}: {number(value)} signed IQR</li>)}</ul>
        <ViewButton onClick={() => onObservation(String(row.id))}>Inspect sample and feature departures</ViewButton>
      </details>)}</div></> : <Empty>{site ? 'Historical measured records do not include AquaLens visual screening.' : 'No independent samples can be scored against this reference in the selected period.'}</Empty>}
      {comparison?.persistent_screening_flag && <p>Repeated flag: three consecutive independent samples crossed the same screening threshold.</p>}
    </Card>
    {feature && <Card title="Feature deviation distribution" hint="Signed departures in reference IQR units for individual observations">
      <div className="in-findings-controls"><label>Visual descriptor<select value={feature.name} onChange={e => setDescriptor(e.target.value)}>{features.map(f => <option key={f.name} value={f.name}>{title(f.name)}</option>)}</select></label></div>
      {history.some(row => Number.isFinite(row.value)) ? <div className="in-findings-chart"><ResponsiveContainer><ComposedChart data={history}><CartesianGrid stroke="#e0eaf7"/><XAxis dataKey="timestamp" tickFormatter={value => value.slice(0, 10)} minTickGap={22}/><YAxis/><Tooltip labelFormatter={value => date(value) + ' IST'}/><ReferenceLine y={0} stroke="#566884"/><Bar dataKey="value" name="Signed IQR deviation" fill={palette[0]} isAnimationActive={false}/></ComposedChart></ResponsiveContainer></div> : <Empty>No independently comparable feature values in this period.</Empty>}
    </Card>}
    <Card title="Location insights" hint="Choose a location to drill into its evidence">
      <div className="in-findings-controls"><label>Monitoring location<select value={String(site?.id || station?.id || '')} onChange={e => onSelect(e.target.value)}><option value="">Select a location</option>{sites.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
    </Card>
    <EnvironmentalContext site={site} archive={archive} data={data} rows={rows} parameter={parameter} start={start} end={end}/>
    <Card title="Detailed findings and methods" hint={`Source: ${source} · Period: ${start || 'earliest available'} to ${end || 'latest available'}`}>
      <details open><summary>What the selected evidence supports</summary><p>{comparison ? `Sample #${current.id} at ${station.name}, ${date(current.timestamp)} IST: ${title(comparison.status)}. ${features.length ? `Largest comparable departure: ${title(features[0].name)}, ${number(features[0].normalized_deviation)} signed IQR from the reference median.` : 'No comparable feature departure is available.'}` : 'Use the measured readings to describe the selected time period. No visual anomaly or water safety conclusion is available from these readings.'}</p></details>
      <details><summary>Methodology and limitations</summary><p>Trends plot reported readings in chronological order. Missing values are not imputed. Visual screening uses the backend comparison against a matching station reference; absolute IQR departures describe the size of visual changes. Rainfall plots require paired measurements from the same archive record.</p></details>
      <p className="in-fineprint">Summary generated: {date(new Date().toISOString())} IST. PDF includes the displayed charts. The station evidence file includes the backend records and reference data.</p>
      {station && <button type="button" className="in-button-outline in-findings-print" onClick={exportReport} disabled={busy}>Download station evidence (.txt)</button>}
    </Card>
    {children}
  </motion.div>;
}

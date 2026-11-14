import { Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from 'recharts';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, get } from '../api';
import { errorText } from './shared';

const percent = value => Number.isFinite(value) ? (100 * value).toFixed(1) + '%' : 'Unavailable';
const pp = value => Number.isFinite(value) ? (100 * value).toFixed(1) + ' pp' : 'Unavailable';
const utcDate = value => new Date(value).toISOString().slice(0, 10);

function CoverageRadar({ result }) {
  const open = result.features.find(feature => feature.name === 'open');
  const partial = result.features.find(feature => feature.name === 'partial');
  if (!Number.isFinite(open?.current) || !Number.isFinite(partial?.current)) return null;
  const rows = [
    { label: 'Open water', current: open.current, baseline: open.median },
    { label: 'Partial water', current: partial.current, baseline: partial.median },
    { label: 'Non-water', current: Math.max(0, 1 - open.current - partial.current), baseline: result.non_water_median },
  ];
  const hasBaseline = rows.every(row => Number.isFinite(row.baseline));
  return <figure className="in-coverage-radar">
    <h3>Surface-water fingerprint</h3>
    <div className="in-coverage-metrics">{rows.map(row => <div key={row.label}>
      <span>{row.label}</span><strong>{percent(row.current)}</strong>
      <div className="in-coverage-meter" aria-hidden="true"><i style={{width: percent(row.current)}}/></div>
    </div>)}</div>
    <div className="in-coverage-chart"><ResponsiveContainer width="100%" height="100%">
      <RadarChart data={rows} outerRadius="60%" margin={{left: 12, right: 12}}>
        <PolarGrid stroke="#c9d6f3" />
        <PolarAngleAxis dataKey="label" tick={{fill: '#415c7a', fontSize: 11}} />
        <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false}/>
        {hasBaseline && <Radar name="Baseline median" dataKey="baseline" stroke="#568ed3" strokeDasharray="4 3" fill="none" isAnimationActive={false}/>}
        <Radar name="Latest observation" dataKey="current" stroke="#3064d7" fill="#3064d7" fillOpacity={0.12} dot={{r: 4, fill: '#3064d7', stroke: '#fff'}} isAnimationActive={false}/>
        <Tooltip formatter={percent}/><Legend/>
      </RadarChart>
    </ResponsiveContainer></div>
    <figcaption>Share of classified pixels · 0–100% scale · {utcDate(result.latest.date)} UTC</figcaption>
  </figure>;
}

export default function EarthdataScenes({ site }) {
  const located = Number.isFinite(site?.latitude) && Number.isFinite(site?.longitude);
  const point = { latitude: site?.latitude, longitude: site?.longitude };
  const queryKey = ['india', 'earthdata-profile', site?.id, point];
  const cache = useQueryClient();
  const profile = useQuery({
    queryKey, enabled: located, retry: false,
    queryFn: ({ signal }) => get('/india/earthdata/profile', point, signal),
  });
  const build = useMutation({
    mutationFn: async () => {
      await cache.cancelQueries({ queryKey, exact: true });
      return (await api.post('/india/earthdata/profile', null, { params: point, timeout: 180000 })).data;
    },
    onSuccess: data => cache.setQueryData(queryKey, data),
  });
  const result = profile.data;
  const dates = result?.reference.map(row => utcDate(row.date)).sort() || [];

  return <section className="in-fingerprint-summary" aria-label="Satellite water fingerprint">
    <header><div><h2>Satellite surface-water fingerprint</h2><p>Satellite surface-water characteristics · NASA OPERA DSWx-HLS</p></div><span className="in-fingerprint-badge">Exploratory</span></header>
    <header><div><h3>{located ? site.name : 'Selected monitoring station'}</h3><p>{located ? 'Baseline vs. latest usable observation' : 'Select a station with mapped coordinates.'}</p></div><span className="in-fingerprint-badge">Reference comparison</span></header>
    {located && <button type="button" className="in-button-solid" disabled={build.isPending || profile.isFetching} onClick={() => build.mutate()}>
      {build.isPending ? 'Building fingerprint…' : result?.latest ? 'Refresh fingerprint' : 'Build satellite fingerprint'}
    </button>}
    {located && profile.isFetching && <p role="status">Loading station fingerprint…</p>}
    {located && (build.isError || profile.isError) && <p role="alert">{errorText(build.error || profile.error)}</p>}
    {result?.import && (result.import.failed > 0 || result.import.access_denied > 0) &&
      <p role="status">Some satellite images could not be retrieved. Refresh to retry.</p>}
    {result?.latest ? <>
      <dl className="in-fingerprint-metrics">
        <div><dt>Baseline samples</dt><dd>{dates.length}</dd></div>
        <div><dt>Features compared</dt><dd>{result.features.filter(row => row.difference != null).length} / {result.features.length}</dd></div>
        <div><dt>Deviation index</dt><dd>{pp(result.deviation)}</dd></div>
      </dl>
      <p>Latest usable observation: {utcDate(result.latest.date)} (UTC).</p>
      <p>{dates.length >= 5 ? 'Reference period: ' + dates[0] + ' to ' + dates.at(-1) + ' (UTC).' : 'Five earlier usable dates on the same grid are required for a baseline.'} {result.latest.valid}/100 pixels classified in the latest observation.</p>
      <CoverageRadar result={result}/>
      <div className="in-fingerprint-deviations"><h3>Visual fingerprint comparison</h3>
        <p>Share of classified pixels · baseline median and latest observation</p>
        {result.features.map(row => <div key={row.name} className="in-fingerprint-deviation">
          <div><strong>{row.name === 'open' ? 'Open water' : 'Partial surface water'}</strong></div>
          {[['Baseline', row.median], ['Current', row.current]].map(([label, value]) => <div key={label} className="in-satellite-comparison-row">
            <span>{label}: {percent(value)}</span>
            {Number.isFinite(value) && <div className="in-fingerprint-track" aria-hidden="true"><i className={label === 'Baseline' ? 'is-baseline' : ''} style={{ width: percent(value) }}/></div>}
          </div>)}
          <p>Reference range: {row.reference_min == null ? 'Unavailable' : percent(row.reference_min) + '–' + percent(row.reference_max)}</p>
        </div>)}
      </div>
      <div className="in-fingerprint-deviations"><h3>Largest feature deviations</h3>
        {[...result.features].filter(row => Number.isFinite(row.difference)).sort((a, b) => Math.abs(b.difference) - Math.abs(a.difference)).map(row => <div key={row.name} className="in-fingerprint-deviation"><div><span>{row.name === 'open' ? 'Open water' : 'Partial surface water'}</span><strong>{row.difference > 0 ? '+' : ''}{pp(row.difference)}</strong></div></div>)}
        {result.deviation == null && <p>No comparable deviations are available.</p>}
      </div>
      <p>The fingerprint covers a 300 m × 300 m area around this station. The deviation index averages the absolute changes from the two reference medians.</p>
    </> : located && result && <p>No usable satellite observations for this station yet.</p>}
  </section>;
}

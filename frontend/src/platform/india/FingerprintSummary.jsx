import { Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from 'recharts';
import { date, number, title } from './shared';

export default function FingerprintSummary({ station, current, reference, comparison }) {
  const features = comparison?.features || [];
  const ranked = features.filter(f => Number.isFinite(f.normalized_deviation))
    .sort((a, b) => Math.abs(b.normalized_deviation) - Math.abs(a.normalized_deviation));
  const axes = ranked.filter(f => f.baseline?.iqr > 1e-9).slice(0, 6).map(f => ({
    feature: title(f.name),
    baseline: 50,
    current: 50 + 100 * Math.atan(f.normalized_deviation) / Math.PI,
    deviation: f.normalized_deviation,
  }));
  const largest = ranked.slice(0, 3);
  const scale = Math.abs(largest[0]?.normalized_deviation ?? 0);
  return <section className="in-fingerprint-summary" aria-label="Water fingerprint summary">
    <header><div><h2>Sample-based visual fingerprint</h2><p>Source-specific visual characteristics</p></div><span className="in-fingerprint-badge">Exploratory</span></header>
    <header><div><h3>{station?.name || 'Selected monitoring station'}</h3><p>{current ? 'Observation #' + current.id + ' · ' + date(current.timestamp) + ' IST' : 'Baseline vs. observation'}</p></div><span className="in-fingerprint-badge">{comparison ? title(comparison.status) : 'Reference comparison'}</span></header>
    <dl className="in-fingerprint-metrics">
      <div><dt>Baseline samples</dt><dd>{number(reference?.sample_count)}</dd></div>
      <div><dt>Features compared</dt><dd>{comparison ? comparison.comparable_features + ' / ' + features.length : '—'}</dd></div>
      <div><dt>Deviation index</dt><dd>{number(comparison?.is_reference_sample ? null : comparison?.anomaly_score)}</dd></div>
    </dl>
    <h3>Visual fingerprint comparison</h3><p>Up to six descriptors with the largest comparable departures</p>
    {axes.length >= 3 ? <div className="in-fingerprint-radar"><ResponsiveContainer width="100%" height="100%">
      <RadarChart data={axes} outerRadius="57%" margin={{ left: 6, right: 6 }}>
        <PolarGrid stroke="#395779"/>
        <PolarAngleAxis dataKey="feature" tick={{ fill: '#E3F2FD', fontSize: 9 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false}/>
        <Radar name="Baseline" dataKey="baseline" stroke="#90CAF9" fill="#90CAF9" fillOpacity={0.18} isAnimationActive={false}/>
        <Radar name="Current" dataKey="current" stroke="#2196F3" fill="#2196F3" fillOpacity={0.14} isAnimationActive={false}/>
        <Tooltip content={({ active, payload }) => active && payload?.[0] ? <div className="in-fingerprint-tooltip">{payload[0].payload.feature}: {number(payload[0].payload.deviation)} IQR from baseline</div> : null}/>
        <Legend/>
      </RadarChart>
    </ResponsiveContainer></div> : <p className="in-fingerprint-empty">{station ? 'At least three features with a usable reference spread are needed for this chart.' : 'Select a station with a matching visual reference to see the comparison.'}</p>}
    <div className="in-fingerprint-deviations"><h3>Largest feature deviations</h3>
      {largest.length ? largest.map(f => <div key={f.name} className="in-fingerprint-deviation"><div><span>{title(f.name)}</span><strong>{f.normalized_deviation > 0 ? '+' : ''}{number(f.normalized_deviation)} IQR</strong></div><div className="in-fingerprint-track" aria-hidden="true"><i style={{ width: (scale ? Math.abs(f.normalized_deviation) / scale * 100 : 0) + '%' }}/></div></div>) : <p>No comparable deviations are available.</p>}
    </div>
    {axes.length >= 3 && <p>Radar positions use a bounded arctangent scale centered on the baseline median. Bar lengths are relative to the largest departure; labels give signed deviations in IQR units.</p>}
    {comparison?.persistent_screening_flag && <p>Three consecutive observations crossed the exploratory screening threshold.</p>}
    {current?.processing_error && <p>{current.processing_error}</p>}
  </section>;
}

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, Empty } from './shared';
import dataset from './ganga-stations.json';
import './findings.css';

const periods = [2022, 2023, 2024, 2025];
const formatAnnualPeriod = year => year === 2025 ? '2025 (Jan–Oct)' : String(year);
const oxygenMetrics = [['do', 'Dissolved oxygen', '#1659b4'], ['bod', 'Biochemical oxygen demand', '#007e94']];
const reading = value => value != null && String(value).trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : null;

export default function RiverArchiveFindings({ river, archive, sites, selected, start, end, onSelect }) {
  const annual = river === 'Ganga';
  const source = annual ? dataset : archive;
  const displayPeriod = value => annual ? formatAnnualPeriod(value) : value.replace('T', ' ');
  const metrics = river === 'Mahanadi'
    ? [['do', 'Dissolved oxygen', '#1659b4', 3], ['bod', 'Total dissolved solids', '#007e94', 4]]
    : river === 'Narmada'
      ? oxygenMetrics.map((metric, i) => [...metric, archive.headers.indexOf(i ? 'BOD' : 'Dissolved Oxygen') + 2])
      : oxygenMetrics;
  const unit = river === 'Narmada' ? '' : ' mg/L';
  const showValue = value => value === null ? 'Not reported' : value + unit;
  const site = selected || sites[0];
  const rows = annual ? periods.filter(year => (!start || year >= Number(start.slice(0, 4))) &&
    (!end || year <= Number(end.slice(0, 4)))).map(year => {
    const index = periods.indexOf(year);
    return { year, do: reading(site?.values[index]), bod: reading(site?.values[index + 4]) };
  }) : (site?.observations || []).filter(([timestamp]) =>
    (!start || timestamp.slice(0, 10) >= start) && (!end || timestamp.slice(0, 10) <= end)
  ).map(row => ({ year: row[0], instant: Date.parse(row[0].length === 10 ? row[0] : row[0] + 'Z'), id: row[1], do: reading(row[metrics[0][3]]), bod: reading(row[metrics[1][3]]) }))
    .sort((a, b) => a.year.localeCompare(b.year));
  const latest = key => rows.findLast(row => row[key] !== null);
  return <div className="in-ganga-findings">
    <div className="in-ganga-main">
      <div className="in-ganga-summary">
        <Card className="in-ganga-station" title="Monitoring station" hint={river + " historical archive"}>
          <div className="in-findings-controls"><label>Archive location<select value={site?.id || ''} onChange={e => onSelect(e.target.value)}>
            {!site && <option value="">No matching stations</option>}
            {sites.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select></label></div>
          <p>{site?.state || 'No state in selection'}</p><small>{sites.length} archive locations match the river and state filters.</small>
        </Card>
        {metrics.map(([key, name]) => {
          const row = latest(key);
          return <Card key={key} title={name} hint="Latest reported in selection"><strong className="in-ganga-value">{row ? `${showValue(row[key])}` : 'Unavailable'}</strong>{row && <p>{displayPeriod(row.year)}</p>}</Card>;
        })}
        <div className="in-ganga-source">Source: {source.source}{annual && " · 2025 covers January–October only."}{!unit && " · The source does not specify units for DO or BOD."}</div>
      </div>
      <Card title={river === "Mahanadi" ? "Water quality trends" : "Oxygen trends"} hint={annual ? "Reported station values by reporting year" : "Reported station values by sample date"}>
        {rows.some(row => row.do !== null || row.bod !== null) ? <div className="in-findings-chart in-ganga-chart"><ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 12, right: 20, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke="#dce7fa"/>
            <XAxis {...(annual ? { dataKey: "year" } : { dataKey: "instant", type: "number", scale: "time", domain: ["dataMin", "dataMax"], tickFormatter: value => new Date(value).toISOString().slice(0, 10) })} minTickGap={22}/><YAxis yAxisId="do" unit={unit} width={72}/><YAxis yAxisId="bod" orientation="right" unit={unit} width={72}/>
            <Tooltip labelFormatter={(label, entries) => { const period = entries?.[0]?.payload.year; return period == null ? "" : displayPeriod(period); }} formatter={showValue}/><Legend/>
            {metrics.map(([key, name, color]) => <Line key={key} yAxisId={key} name={name} dataKey={key} type="linear" connectNulls={false} stroke={color} strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false}/>)}
          </LineChart>
        </ResponsiveContainer></div> : <Empty>No readings match this station and reporting period.</Empty>}
        <p className="in-fineprint">{annual ? "Date filters select reporting years. " : "Date filters select sample dates. "}Missing readings remain gaps. Each series has its own vertical axis.</p>
      </Card>
    </div>
    <aside className="in-ganga-rail" aria-label="Reported readings and coverage">
      <Card title="Reported readings" hint="Selected station · latest reporting periods">
        {site && rows.length ? <dl className="in-ganga-readings">{[...rows].reverse().slice(0, 4).map(row => <div key={row.id ?? row.year}><dt>{displayPeriod(row.year)}</dt><dd>{metrics[0][1]}: {showValue(row.do)} · {metrics[1][1]}: {showValue(row.bod)}</dd></div>)}</dl> : <Empty>No reporting periods to show.</Empty>}
      </Card>
      <Card title="Data coverage" hint={annual ? "Reported values / selected reporting years" : "Reported values / sample records in selection"}>
        {site && rows.length ? metrics.map(([key,name]) => {
          const count = rows.filter(row => row[key] !== null).length;
          return <div className="in-ganga-coverage" key={key}><label>{name} · {count}/{rows.length}<progress value={count} max={rows.length}/></label></div>;
        }) : <Empty>No coverage to calculate.</Empty>}
        <p className="in-fineprint">Coverage describes record availability. These summaries do not establish visual anomalies or water safety.</p>
      </Card>
    </aside>
  </div>;
}

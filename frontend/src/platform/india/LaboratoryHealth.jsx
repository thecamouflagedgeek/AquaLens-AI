import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { get, message } from '../api';
import { Card, Empty, StationMap } from './shared';

const scoreText = score => Number.isFinite(score) ? `${score.toFixed(1)} / 100` : 'Insufficient Laboratory Data';

export default function LaboratoryHealth({ river, state, stationId, stationName, start, end }) {
  const params = { river, state, start: start || undefined, end: end || undefined };
  const query = useQuery({
    queryKey: ['india', 'laboratory-health', params],
    queryFn: ({ signal }) => get('/india/laboratory/water-health', params, signal),
  });
  const data = query.data;
  const sites = data?.stations || [];
  const [mappedId, setMappedId] = useState('');
  const nameMatches = stationName ? sites.filter(site => site.name.toLowerCase() === stationName.toLowerCase()) : [];
  const selected = mappedId ? sites.find(site => site.id === mappedId)
    : sites.find(site => site.id === stationId) || (nameMatches.length === 1 ? nameMatches[0] : undefined);
  const fullScore = stationId || selected ? selected?.assessment?.score : data?.score;
  const partialScore = stationId || selected ? selected?.partial_assessment?.score : data?.partial_score;
  const partial = !Number.isFinite(fullScore) && Number.isFinite(partialScore);
  const score = partial ? partialScore : fullScore;
  const selectedAssessment = partial ? selected?.partial_assessment : selected?.assessment;
  const scoreLabel = query.isPending ? 'Loading laboratory records…'
    : query.isError ? 'Assessment unavailable' : !river && !stationId && !selected ? 'Select a river or station' : scoreText(score);
  const mapped = sites.filter(site => site.coordinates).map(site => ({
    ...site, latitude: site.coordinates[0], longitude: site.coordinates[1],
    coordinate_source: site.agency + ' archive',
  }));
  const stationQuery = useQuery({
    queryKey: ['india', 'laboratory-health', params, selected?.id],
    enabled: !!selected,
    queryFn: ({ signal }) => get('/india/laboratory/water-health', { ...params, station: selected.id }, signal),
  });
  const firstSample = selectedAssessment?.first || (!stationId && (partial ? data?.partial_earliest : data?.earliest));
  const lastSample = selectedAssessment?.last || (!stationId && (partial ? data?.partial_latest : data?.latest));
  const scoreSources = selectedAssessment?.sources || (!stationId && (partial ? data?.partial_sources : data?.score_sources));
  const trendData = selected ? stationQuery.data : data;
  const trend = partial ? trendData?.partial_trend : trendData?.trend;

  return <Card title="Water Health Score" hint={data?.water_use}>
    <strong className="in-ground-value">{scoreLabel}</strong>
    {Number.isFinite(score) && <p><strong>{partial ? 'Partial Laboratory Water Quality Index · pH and dissolved oxygen' : 'Full WQI'}</strong></p>}
    {partial && <p>Full WQI: {scoreText(fullScore)}. Coverage: 2 of 4 Class B objectives in this index. BOD and total coliform are excluded. This score does not establish overall water safety.</p>}
    {query.isError && <p role="alert">{message(query.error)}</p>}
    {data && <p>{selected
      ? `${selected.observed_events} recorded sampling events at ${selected.name}`
      : `${partial ? data.partial_scored_stations : data.scored_stations} of ${data.total_stations} archive stations scored`}

    </p>}
    {Number.isFinite(score) && firstSample && lastSample && <p>
      Scored samples: {firstSample.slice(0, 10)} to {lastSample.slice(0, 10)}
      {selected && ` · ${selectedAssessment.sample_count} complete events`}
      {scoreSources?.length > 0 && <> · {scoreSources.join(', ')}</>}
    </p>}
    {river && data?.excluded_archives?.[river] && <p>{data.excluded_archives[river]}</p>}
    {data?.sources.length > 0 && <p>Archive files: {data.sources.join(', ')}</p>}
    {trend?.some(point => point.score !== null) && <ResponsiveContainer width="100%" height={240}>
      <LineChart data={trend}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="year"/>
        <YAxis domain={[0, 100]}/><Tooltip/><Line dataKey="score" name={partial ? 'Annual partial index' : 'Annual full WQI'} stroke="#1659b4"/>
      </LineChart>
    </ResponsiveContainer>}
    {data && <details>
      <summary>Know More · methodology and station coverage</summary>
      <p>Partial index ({data.partial_version}): each paired measurement receives continuous ratings. The pH rating is 100 ÷ (1 + (pH − 7.5)²). The DO rating is 100 × DO ÷ (DO + 5), with DO in mg/L. Each CPCB threshold rates 50 for its parameter. The pH midpoint is the scoring reference and the DO rating increases with diminishing returns. Average each parameter’s ratings, then give each average 50% weight. At least four distinct paired sampling dates are required. These AquaLens rating curves describe pH and oxygen conditions against Class B reference points. They do not estimate oxygen saturation, quantify total water quality, or establish water safety.</p>
      <p>AquaLens applies CCME WQI to CPCB Class B objectives. Scope counts parameters that fail, frequency counts failed tests, and amplitude measures the size of excursions. The three factors contribute equally in the index formula. Each parameter has one test per complete event. At least four distinct sampling dates with all four readings are required.</p>
      <p>River scores average eligible station scores equally. Coverage shows how many stations contributed. Annual scores are calculated independently and describe the selected period only. AquaLens reports an index against the chosen objectives. Official CPCB classification is a separate determination.</p>
      <p><a href={data.criteria}>CPCB objectives</a> · <a href={data.method}>CCME method</a> · {data.version}</p>
      {mapped.length > 0 && <StationMap stations={mapped} selected={mapped.find(site => site.id === selected?.id)} onSelect={id => setMappedId(id)}/>}
      {sites.length > 0 && <label>Archive station <select value={selected?.id || ''} onChange={event => setMappedId(event.target.value)}>
        <option value="">{stationId ? "Use dashboard selection" : "River summary"}</option>
        {sites.map(site => <option value={site.id} key={site.id}>{site.name} · {site.river || 'River unreported'}</option>)}
      </select></label>}
      {sites.length ? <div className="in-table-wrap"><table>
        <thead><tr><th>Station</th><th>Agency</th><th>Sampling events</th><th>Complete dates</th><th>Sampling dates by parameter</th><th>Full WQI</th><th>Partial index</th></tr></thead>
        <tbody>{sites.map(site => <tr key={site.id} id={`wqi-site-${site.id}`}><th scope="row">{site.name} · {site.river || 'River unreported'}{site.metadata_source && <> · <a href={site.metadata_source}>CPCB #{site.station_code}</a></>}</th>
          <td>{site.agency}</td><td>{site.observed_events}</td><td>{site.complete_sampling_dates ?? '—'}</td><td>{site.parameter_sampling_dates ? Object.entries(site.parameter_sampling_dates).map(([name, count]) => `${name}: ${count}`).join(' · ') : site.available_parameters.join(', ') || 'None'}</td>
          <td>{scoreText(site.assessment?.score)}{site.ineligibility_reason && <p>{site.ineligibility_reason}</p>}{site.assessment && <details><summary>Parameter results</summary>
            <p>{site.assessment.first.slice(0, 10)} to {site.assessment.last.slice(0, 10)} · {site.assessment.sources.join(', ')}</p>
            <p>{Object.entries(site.assessment.factors).map(([name, value]) => `${name} ${value.toFixed(1)}`).join(' · ')}</p>
            <ul>{Object.entries(site.assessment.parameters).map(([name, item]) => <li key={name}>
              {name} {item.latest} {item.unit} · {item.failures}/{item.tests} outside objective
              {' · '}{item.minimum != null && item.maximum != null ? `${item.minimum}–${item.maximum}` : item.minimum != null ? `≥ ${item.minimum}` : `≤ ${item.maximum}`}
            </li>)}</ul>
          </details>}</td><td>{scoreText(site.partial_assessment?.score)}
          {site.partial_assessment && <details><summary>pH and DO breakdown</summary>
            <p>{site.partial_assessment.first.slice(0, 10)} to {site.partial_assessment.last.slice(0, 10)} · {site.partial_assessment.sampling_dates} paired dates · {site.partial_assessment.sources.join(', ')}</p>
            <ul>{Object.entries(site.partial_assessment.parameters).map(([name, item]) => <li key={name}>
              {name} · {item.tests - item.failures}/{item.tests} passed · {item.mean_rating?.toFixed(1) ?? '—'} mean rating · {item.contribution.toFixed(1)} of 50 points
            </li>)}</ul>
          </details>}
          </td></tr>)}</tbody>
      </table></div> : <Empty>No eligible dated archive records match this selection.</Empty>}
    </details>}
  </Card>;
}

import LaboratoryHealth from './india/LaboratoryHealth';
import GroundMonitoring from './india/GroundMonitoring';
import ContextLab from './india/ContextLab';
import RiverArchiveFindings from './india/GangaFindings';
import FindingsDashboard from './india/FindingsDashboard';
import narmada from './india/narmada-stations.json';
import cwc from './india/cwc-chemical.json';
import EarthdataScenes from './india/EarthdataScenes';
import { RiverMeasurements, SatelliteCatalog } from './india/DatasetPanels';
import gangaDataset from './india/ganga-stations.json';
import FingerprintSummary from './india/FingerprintSummary';
import React, { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Waves, LayoutGrid, Fingerprint, ScanLine, Activity, CloudSun, ArrowUpRight, Download, Plus, LogOut, MapPin, SlidersHorizontal, CircleHelp, Search } from 'lucide-react';
import { useAuth } from './state';
import { api, get } from './api';
import WaterScene from './india/WaterScene';
import DataForm, { Dialog } from './india/Forms';
import { Card, Empty, Status, SampleImage, StationMap, Timeline, FeatureBars, FeatureTable, Meta, ViewButton, number, date, title, seasons, rivers, errorText } from './india/shared';
import './india.css';
import './india-overview.css';

const tabs = [ ['overview', 'Overview', LayoutGrid], ['fingerprint', 'Fingerprint', Fingerprint], ['samples', 'Samples', ScanLine], ['findings', 'Findings', Activity], ['evidence', 'Context & lab', CloudSun] ];
const formTitles = { station: 'Register a monitoring station', sample: 'Record a water sample', baseline: 'Establish a station reference', laboratory: 'Add a laboratory measurement', context: 'Add a contextual measurement' };

export default function IndiaWorkspace() {
  const { user, logout } = useAuth(); const navigate = useNavigate(); const cache = useQueryClient();
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [mapSearch, setMapSearch] = useState(null);
  const [exploreOpen, setExploreOpen] = useState(false);
  const [params, setParams] = useSearchParams(); const [dialog, setDialog] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const mode = ['ground','combined'].includes(params.get('mode')) ? params.get('mode') : 'remote';
  const stationId = params.get('station') || ''; const view = tabs.some(t => t[0] === params.get('view')) ? params.get('view') : 'overview';
  const river = params.get('river') || ''; const state = params.get('state') || ''; const start = params.get('from') || ''; const end = params.get('to') || ''; const observation = params.get('observation') || '';
  const update = patch => { const next = new URLSearchParams(params); Object.entries(patch).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key)); setParams(next, { replace: true }); };
  const selectStation = id => {
    if ((id.startsWith('ganga-csv-') || id.startsWith('cwc-') || id.startsWith('narmada-csv-')) && view === 'overview') {
      setExploreOpen(true);
      setMapSearch({ river });
    }
    update({ station: id, observation: '' });
  };
  const laboratoryCatalog = useQuery({
    queryKey: ['india', 'laboratory-health', 'catalog'],
    queryFn: ({ signal }) => get('/india/laboratory/water-health', undefined, signal),
    enabled: mode !== 'ground',
    staleTime: 60000,
  });
  const riverOptions = [...new Set([...rivers, ...(laboratoryCatalog.data?.available_rivers || [])])].sort();
  const stationsQuery = useQuery({ queryKey: ['india', 'stations'], queryFn: ({ signal }) => get('/india/stations', undefined, signal) });
  const stations = stationsQuery.data || [];
  const groundFeed = useQuery({queryKey:['india','ground'], enabled:mode!=='remote', queryFn:({signal})=>get('/india/ground/observations',undefined,signal), refetchInterval:10000});
  const officer = params.get('officer') || '';
  const location = params.get('location') || '';
  const officers = [...new Map((groundFeed.data || []).map(o=>[String(o.ground.officer_id),o.ground.officer]))];
  const filtered = useMemo(() => stations.filter(s => (!river || s.river === river) && (!state || s.state === state)), [stations, river, state]);
  const station = filtered.find(s => String(s.id) === stationId);
  const dateError = start && end && start > end;
  const queryParams = { observation_id: observation || undefined, start: start ? `${start}T00:00:00+05:30` : undefined, end: end ? `${end}T23:59:59.999999+05:30` : undefined };
  const analysisQuery = useQuery({ queryKey: ['india', 'analysis', station?.id, queryParams], queryFn: ({ signal }) => get(`/india/stations/${station.id}/analysis`, queryParams, signal), enabled: !!station && !dateError });
  const data = analysisQuery.data; const current = data?.current; const comparison = data?.comparison; const reference = data?.reference;
  const features = comparison?.features || [];
  const refresh = () => cache.invalidateQueries({ queryKey: ['india'] });
  const showGanga = view === 'overview' && river === 'Ganga' && mapSearch?.river === 'Ganga' && !station;
  const showCwc = view === 'overview' && ['Mahanadi', 'Godavari', 'Narmada'].includes(river) && !station;
  const showArchive = (showGanga || showCwc) && archiveOpen;
  function search() {
    if (view === 'overview') {
      setExploreOpen(true);
      setArchiveOpen(false);
    }
    setMapSearch({ river });
    return refresh();
  }
  async function saved(kind, record) { await refresh(); if (kind === 'station') update({ station: String(record.id), river: record.river, state: record.state, observation: '' }); if (kind === 'sample') update({ observation: String(record.id), from: '', to: '' }); setNotice('Record saved to the Indian workspace.'); }
  async function signOut() { setBusy(true); try { await logout(); navigate('/', { replace: true }); } catch (e) { setNotice(errorText(e)); } finally { setBusy(false); } }
  async function exportReport() {
    if (!station) return; setBusy(true);
    try { const res = await api.get(`/india/stations/${station.id}/report`, { params: queryParams, responseType: 'blob' }); const url = URL.createObjectURL(res.data); const link = document.createElement('a'); link.href = url; link.download = `aqualens-india-station-${station.id}.txt`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
    catch (e) { setNotice(errorText(e)); } finally { setBusy(false); }
  }
  const chemicalDataset = river === 'Narmada' ? narmada : cwc;
  const datasetStations = river === 'Ganga' ? gangaDataset.stations : chemicalDataset.stations.filter(site => site.river === river);
  const datasetFiltered = datasetStations.filter(site => !state || site.state === state);
  const datasetStation = datasetFiltered.find(site => site.id === stationId);
  const mappedDatasetSites = datasetFiltered.filter(site => Number.isFinite(site.latitude) && Number.isFinite(site.longitude)).map(site => ({ ...site, river, historical: true, coordinate_source: river === 'Ganga' ? gangaDataset.coordinateSource : chemicalDataset.source }));
  const mapStations = [...filtered, ...mappedDatasetSites];
  const mapStation = station || mappedDatasetSites.find(site => site.id === stationId);
  const visibleDatasetSites = datasetStation ? [datasetStation] : datasetFiltered;
  const states = [...new Set([...stations.filter(s => !river || s.river === river), ...datasetStations, ...(laboratoryCatalog.data?.stations || []).filter(s => !river || s.river === river)].map(s => s.state))].sort();
  const remoteOverview = mode === 'remote' && view === 'overview';
  const [showScoreDetails, setShowScoreDetails] = useState(false);
  const healthParams = { river, state, start: start || undefined, end: end || undefined };
  const healthQuery = useQuery({
    queryKey: ['india', 'laboratory-health', healthParams],
    enabled: remoteOverview && !dateError,
    queryFn: ({ signal }) => get('/india/laboratory/water-health', healthParams, signal),
  });
  const health = healthQuery.data;
  const laboratorySites = remoteOverview ? health?.stations || [] : [];
  const archiveMapSites = laboratorySites.filter(site => Array.isArray(site.coordinates)).map(site => ({
    ...site, latitude: site.coordinates[0], longitude: site.coordinates[1],
    coordinate_source: site.agency + ' archive',
  }));
  const overviewMapSites = [...mapStations, ...archiveMapSites];
  const overviewMapStation = mapStation || archiveMapSites.find(site => site.id === stationId);

  const stationMatches = (health?.stations || []).filter(site =>
    site.id === stationId || ((station || datasetStation) && site.name.toLowerCase() === (station || datasetStation).name.toLowerCase()
      && site.state === (station || datasetStation).state));
  const healthSite = stationMatches.length === 1 ? stationMatches[0] : null;
  const fullScore = stationId ? healthSite?.assessment?.score : health?.score;
  const partialScore = stationId ? healthSite?.partial_assessment?.score : health?.partial_score;
  const score = fullScore ?? partialScore;
  const scoreName = fullScore != null ? 'Full laboratory WQI' : partialScore != null ? 'Partial Laboratory Water Quality Index · pH + DO' : 'Laboratory index unavailable';
  const labEvents = healthSite ? healthSite.observed_events : stationId ? null
    : health?.stations.reduce((total, site) => total + site.observed_events, 0);
  function openScoreDetails() {
    setShowScoreDetails(true);
    requestAnimationFrame(() => document.getElementById('remote-score-details')?.scrollIntoView({ block: 'start' }));
  }
  return <div className={`india-app in-overview-layout in-gradient-workspace ${remoteOverview ? "in-remote-overview" : ""}`}><a className="in-skip" href="#india-main">Skip to monitoring content</a><div className="in-shell">
    {view !== 'overview' && <WaterScene/>}
    <header className="in-topbar"><Link to="/" className="in-brand"><Waves size={29} strokeWidth={2.2}/><span>AquaLens<span className="in-brand-country">INDIA</span></span></Link><nav aria-label="Indian workspace">{tabs.map(([id, label, Icon]) => <button key={id} aria-label={label} title={label} aria-current={view === id ? 'page' : undefined} className={view === id ? 'is-active' : ''} onClick={() => update({ view: id })}><Icon size={14}/><span>{label}</span></button>)}</nav><div className="in-account"><span className="in-avatar" title={user.username}>A1</span><button aria-label="Logout" title="Logout" onClick={signOut} disabled={busy}><LogOut size={17}/></button></div></header>
    <div className="in-welcome"><div><span className="in-kicker">WATER FINGERPRINTING · INDIAN RIVERS</span><h1>{view === 'overview' ? (remoteOverview ? 'Remote monitoring overview' : 'River monitoring overview') : tabs.find(([id]) => id === view)?.[1]}</h1><p>{remoteOverview ? <>Nationwide river insights from satellite and laboratory observations.<br/>Track water quality and environmental change.</> : <>A clearer perspective on our rivers.<br/>Observe the sample. Understand the change.</>}</p></div><div className="in-monitoring-modes" aria-label="Monitoring mode">{[["remote","Remote (Satellite)"],["ground","Ground (Smartphone)"],["combined","Combined"]].map(([id,label])=><button type="button" key={id} aria-pressed={mode===id} onClick={()=>update({mode:id==="remote"?"":id})}>{label}</button>)}</div><div className="in-welcome-actions"><button className="in-button-outline" onClick={exportReport} disabled={!station || busy || !!dateError || analysisQuery.isError}><Download size={14}/>Export report</button><button className="in-button-white" onClick={() => setDialog(station && !remoteOverview ? 'sample' : 'station')}><Plus size={15}/>{station && !remoteOverview ? 'Record sample' : 'Register station'}</button></div></div>
    <main id="india-main">
      <section className="in-filters" aria-label="Monitoring filters">{view === "overview" ? <button type="button" className="in-filter-icon in-explore-toggle" aria-expanded={exploreOpen} aria-controls={showArchive ? undefined : "india-explore-cards"} onClick={() => { if (showArchive) setArchiveOpen(false); else setExploreOpen(open => !open); }}><SlidersHorizontal size={17} aria-hidden="true"/><span>Explore</span></button> : <div className="in-filter-icon"><SlidersHorizontal size={17}/><span>Explore</span></div>}{mode === 'ground' ? <><label>Field officer<select value={officer} onChange={e=>update({officer:e.target.value})}><option value="">All officers</option>{officers.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><label>Capture location<select value={location} onChange={e=>update({location:e.target.value})}><option value="">All locations</option>{stations.map(s=><option key={s.id} value={s.id}>{s.name} · {s.state} · {s.river}</option>)}</select></label></> : <><label>River<select value={river} onChange={e => update({ river: e.target.value, state: '', station: '', observation: '' })}><option value="">All rivers</option>{riverOptions.map(r => <option key={r}>{r}</option>)}</select></label><label>State<select value={state} onChange={e => update({ state: e.target.value, station: '', observation: '' })}><option value="">All states</option>{states.map(s => <option key={s}>{s}</option>)}</select></label><label>Station<select value={stationId} onChange={e => selectStation(e.target.value)}><option value="">Select a station</option>{filtered.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}{datasetFiltered.length > 0 && <optgroup label={river === "Ganga" ? "Ganga dataset · 2022–2025" : river === "Narmada" ? "Narmada historical dataset" : "CWC chemical monitoring archive"}>{datasetFiltered.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</optgroup>}{laboratorySites.length > 0 && <optgroup label="Laboratory monitoring sites">
        {laboratorySites.filter(site => !filtered.some(item => String(item.id) === site.id)).map(site => <option key={site.id} value={site.id}>{site.name}</option>)}
      </optgroup>}</select></label></>}<label>From<input aria-label="Observation period from" type="date" value={start} max={end || undefined} onChange={e => update({ from: e.target.value, observation: '' })}/></label><label>To<input aria-label="Observation period to" type="date" value={end} min={start || undefined} onChange={e => update({ to: e.target.value, observation: '' })}/></label><div className="in-filter-actions"><button type="button" className="in-button-solid" onClick={search} disabled={!!dateError || stationsQuery.isFetching || analysisQuery.isFetching}><Search size={15} aria-hidden="true"/>{stationsQuery.isFetching || analysisQuery.isFetching ? 'Loading…' : 'Search'}</button><button className="in-circle-button" title="Register station" aria-label="Register station" onClick={() => setDialog('station')}><Plus size={18}/></button></div></section>
      {notice && <div className="in-notice" role="status">{notice}<button aria-label="Dismiss notification" onClick={() => setNotice('')}>×</button></div>}
      {dateError && <p className="in-error" role="alert">Choose an end date on or after the start date.</p>}
      {(stationsQuery.isError || analysisQuery.isError) && <p className="in-error" role="alert">{errorText(stationsQuery.error || analysisQuery.error)} <button onClick={() => { stationsQuery.refetch(); if (station) analysisQuery.refetch(); }}>Retry</button></p>}
      {(stationsQuery.isPending || (station && analysisQuery.isPending)) && <div className="in-loading" role="status">Loading recorded monitoring evidence…</div>}
      {mode !== "ground" && stationId && !station && !datasetStation && !laboratorySites.some(site => site.id === stationId) && stationsQuery.isSuccess && <p className="in-error">Selected station is not available in the current river and state filters.</p>}
      {mode === 'combined' && view === 'overview' && !dateError && <LaboratoryHealth key={JSON.stringify([river, state, stationId, start, end])}
        river={river} state={state} stationId={stationId} stationName={station?.name || datasetStation?.name}
        start={start} end={end}/>}
      {mode !== 'remote' && !dateError && <GroundMonitoring feed={groundFeed} officer={mode==="ground"?officer:""} stations={stations} river={mode==="ground"?"":river} state={mode==="ground"?"":state} stationId={mode==="ground"?location:stationId} start={start} end={end} view={view} onNavigate={v=>update({view:v})} onLab={station ? ()=>setDialog('laboratory') : undefined} onContext={station ? ()=>setDialog('context') : undefined}/>}
      {mode !== 'ground' && <>
      {view === 'overview' && !showArchive && <>
        <div className="in-overview-kpis" aria-label="Monitoring metrics">
          {[
            [MapPin, 'Monitoring stations', stationsQuery.isSuccess ? new Set([...filtered, ...datasetFiltered].map(s => s.id)).size : '—', 'Matches river and state filters'],
            [ScanLine, 'Satellite observations', '—', 'See the selected station’s Fingerprint'],
            [CloudSun, 'Laboratory records', remoteOverview ? (labEvents ?? '—') : data?.laboratory?.filter(r => (!start || r.timestamp.slice(0,10) >= start) && (!end || r.timestamp.slice(0,10) <= end)).length ?? '—', 'Selected registered station and dates'],
            ...(remoteOverview ? [[Activity, 'Water Health Score', score?.toFixed(1) ?? '—', scoreName]] : []),
            [Fingerprint, 'Visual screening flags', data?.timeline?.some(r => Number.isFinite(r.anomaly_score)) ? data.timeline.filter(r => r.status === 'potential_anomaly').length : '—', 'Selected station and reference'],
          ].map(([Icon, label, value, detail]) => <div className="in-overview-kpi" key={label}><span className="in-card-icon"><Icon size={21}/></span><div><strong>{value}</strong><div>{label}</div><small>{detail}</small></div></div>)}
        </div>
      </>}
      {view === 'overview' && <section className={`in-map-dashboard ${showArchive ? "in-archive-split" : "in-overview-board"}`} aria-label="Indian river monitoring overview">
        <div className="in-map-dashboard-canvas"><StationMap layerControls={remoteOverview && !showArchive} key={showArchive ? "archive" : "overview"} showRivers mapSearch={mapSearch} stations={overviewMapSites} selected={overviewMapStation} onSelect={selectStation}/>{!showArchive && <aside className="in-map-dashboard-legend" aria-label="Map legend">
          <strong>Map legend</strong>
          <span><i className="in-legend-river"/>Major rivers · Natural Earth</span>
          <span><i/>Registered station</span><span><i className="in-legend-historical"/>Historical dataset station</span>
          <span><i className="in-legend-selected"/>Selected station</span>
          <small>{overviewMapSites.length} {overviewMapSites.length === 1 ? 'station' : 'stations'} in view</small>
        </aside>}</div>
        {!showArchive && <div className="in-overview-station"><Card title={overviewMapStation?.name || datasetStation?.name || station?.name || 'Select a monitoring station'} hint={[river, (station || datasetStation)?.state].filter(Boolean).join(' · ') || 'Indian river monitoring'}>
          <nav className="in-overview-links" aria-label="Station analysis"><span aria-current="page">Overview</span>{[['fingerprint',remoteOverview ? 'Trends' : 'Fingerprint'],['findings','Findings'],['evidence','Context']].map(([id,label]) => <button key={id} type="button" onClick={() => remoteOverview && id === 'fingerprint' ? openScoreDetails() : update({view:id})}>{label}</button>)}</nav>
          {remoteOverview ? <div className="in-remote-score-row">
            <div className="in-remote-scene">{current ? <SampleImage observation={current} label="Recorded sample"/>
              : <><ScanLine size={26}/><span>Satellite preview unavailable</span></>}</div>
            <div className="in-remote-gauge" style={{ '--score': Number.isFinite(score) ? `${score}%` : '0%' }}>
              <div><strong>{score?.toFixed(1) ?? '—'}</strong><small>/ 100</small></div>
            </div>
            <div className="in-remote-score-copy"><strong>Water Health Score</strong><small>{scoreName}</small>{fullScore == null && partialScore != null && <small>2 of 4 objectives · BOD and total coliform excluded</small>}
              <ViewButton onClick={openScoreDetails}>View detailed analysis</ViewButton>
            </div>
          </div> : current ? <SampleImage observation={current} label="Latest recorded sample"/> : <p>{datasetStation ? 'Historical measurements are available in Findings.' : 'Select a station from the map or station filter to inspect its evidence.'}</p>}
          {remoteOverview && <h3 className="in-remote-parameter-heading">Key satellite-derived parameters</h3>}
          <div className="in-overview-parameters">
            {(!remoteOverview && datasetStation?.values
              ? [['DO', datasetStation.values[3], 'mg/L'], ['BOD', datasetStation.values[7], 'mg/L']]
              : [['CDOM', null], ['Turbidity', null], ['Chlorophyll-a', null], ['Surface area', null]]
            ).map(([label,value,unit]) => <div key={label}><small>{label}</small><strong>{value == null ? '—' : `${value} ${unit}`}</strong></div>)}
          </div>
          <p className="in-fineprint">{!remoteOverview && datasetStation?.values ? 'Ganga archive · January–October 2025 (date filters do not change this summary).' : 'Satellite parameter values are not available in this overview.'}</p>
          {!remoteOverview && <ViewButton onClick={() => update({view:'findings'})}>View detailed analysis</ViewButton>}
        </Card></div>}
        {showArchive && <div className="in-archive-table"><ViewButton onClick={() => setArchiveOpen(false)}>Back to overview</ViewButton>{showGanga ? <><GangaDatasetTable sites={visibleDatasetSites}/><GangaArchive/></> : <CwcOverview dataset={chemicalDataset} sites={visibleDatasetSites} start={start} end={end} archive/>}</div>}
        {!showArchive && showGanga && <div className="in-map-dashboard-panels" id="india-explore-cards" hidden={!exploreOpen}>
          <div className="in-map-dashboard-summary">
            <Card title="Monitoring network" hint="Ganga dataset · 2022–2025">
              <div className="in-network-number">{visibleDatasetSites.length}<span>dataset stations</span></div>
              <p>2025 covers January through October.</p>
            </Card>
            <Card title="Water-quality observations" hint="Reported DO and BOD · Jan–Oct 2025">
              {visibleDatasetSites.length ? visibleDatasetSites.slice(0, 2).map(site => <p key={site.id}><strong>{site.name}</strong><br/>DO: {site.values[3] ?? 'Not reported'} mg/L · BOD: {site.values[7] ?? 'Not reported'} mg/L</p>) : <Empty>No CSV stations match the selected state.</Empty>}
            </Card>
          </div>
          <Card title="Your river network" hint="Select a dataset station to inspect its measurements">
            <div className="in-station-list">{datasetFiltered.map(site => <button type="button" key={site.id} onClick={() => selectStation(site.id)} aria-pressed={datasetStation?.id === site.id} className={datasetStation?.id === site.id ? 'is-selected' : ''}><span><strong>{site.name}</strong><small>{site.state}</small></span></button>)}</div>
            <p>Station and state filters apply to the CSV records. Date filters apply to AquaLens image observations.</p>
          </Card>
          <button type="button" className="in-button-solid" onClick={() => setArchiveOpen(true)}>Explore more</button>
        </div>}
        {showCwc && !showArchive && <div className="in-map-dashboard-panels" id="india-explore-cards" hidden={!exploreOpen}>
          <CwcOverview dataset={chemicalDataset} sites={visibleDatasetSites} start={start} end={end} onSelect={selectStation}/>
          <button type="button" className="in-button-solid" onClick={() => setArchiveOpen(true)}>Explore more</button>
        </div>}
        {!showGanga && !showCwc && <div className="in-map-dashboard-panels" id="india-explore-cards" hidden={!exploreOpen}>
          <div className="in-map-dashboard-summary">
            <Card title="Monitoring network" hint="Registered locations · India only" className="in-network-card" action={<div className="in-card-icon"><MapPin size={16}/></div>}><div className="in-network-number">{stationsQuery.isPending || stationsQuery.isError ? '—' : filtered.length}<span>{filtered.length === 1 ? 'station' : 'stations'}</span><Waves className="in-network-wave" size={68} aria-hidden="true"/></div><div className="in-network-bottom"><span>{river || rivers.join(" · ")}</span><button onClick={() => setDialog('station')} aria-label="Add Indian monitoring station"><ArrowUpRight size={17}/></button></div></Card>
            <Card className="in-recent-card" title="Recent observations" hint="Original acquired samples" action={<ViewButton onClick={() => update({ view: 'samples' })}>View all</ViewButton>}>{current ? <div className="in-observation-mini"><SampleImage observation={current} label={`Sample #${current.id}`}/><div><Status value={current.classification?.predicted_condition || 'RF unavailable'}/><p>{current.season} · {current.capture_protocol}</p></div></div> : <Empty>{station ? 'No observations in the selected period.' : stationsQuery.isPending ? 'Loading monitoring stations.' : stationsQuery.isError ? 'Monitoring stations could not be loaded.' : filtered.length ? 'Choose a station to inspect its sample archive.' : river === 'Ganga' ? 'No registered AquaLens stations match. Historical water-quality records are available in the Ganga archive.' : 'No registered stations match this search.'}</Empty>}</Card>
          </div>
          <Card title="Your river network" hint="Select a recorded sampling location" action={<span className="in-small-tag">{filtered.length} registered</span>} className="in-river-card">{filtered.length ? <div className="in-station-list">{filtered.map(s => <button key={s.id} onClick={() => selectStation(String(s.id))} className={station?.id === s.id ? 'is-selected' : ''}><div className="in-station-icon"><Waves size={17}/></div><div><strong>{s.name}</strong><small>{s.river} · {s.state}</small></div><ArrowUpRight size={16}/></button>)}</div> : <Empty>No stations registered for this selection. Add a real sampling location to begin.</Empty>}<button className="in-add-station" onClick={() => setDialog('station')}><Plus size={14}/>Register a monitoring station</button></Card>
          <Card className="in-stability-card" title="Visual stability" hint={station ? station.name : 'Source-specific reference comparison'} action={<span className="in-small-tag">Exploratory</span>}><div className="in-stability-value">{number(comparison?.visual_stability_score)}<span>/ 100</span></div><Timeline rows={data?.timeline}/><div className="in-card-foot">{reference ? `${reference.sample_count} reference images · ${reference.season}` : 'A matching station reference is required.'}</div></Card>
          <section className="in-insight-card"><span className="in-insight-label"><Fingerprint size={15}/>SOURCE-SPECIFIC INTELLIGENCE</span><h2>{comparison?.persistent_screening_flag ? 'A repeated change needs review.' : comparison?.status === 'potential_anomaly' ? 'A visual departure needs context.' : current ? 'Every sample adds perspective.' : 'Every river has a story.'}</h2><p>{current ? `Latest sample: ${date(current.timestamp)} IST. ${reference ? 'Compare this observation with its recorded reference conditions.' : 'Build a station reference to begin measuring visual change.'}` : 'Build a reference from real observations, then understand how each river stretch changes over time.'}</p><button className="in-button-white" onClick={() => update({ view: 'findings' })}>View analysis<ArrowUpRight size={14}/></button></section>
        </div>
        }

      </section>}
      {view === 'overview' && exploreOpen && !showArchive && river === 'Mahanadi' && <div className="in-archive-table"><RiverMeasurements river={river}/></div>}
      {view !== 'overview' && <section className={["findings", "evidence"].includes(view) ? "in-findings-layout" : "in-map-dashboard in-archive-split in-page-split"} aria-label={view === "evidence" ? "Context and laboratory evidence" : view === "findings" ? "Findings analytics" : "Monitoring content and river map"}>
        <div className="in-archive-table">
      {view === 'samples' && <SatelliteCatalog/>}
      {view === 'fingerprint' && !station && !datasetStation && <Card title="Choose a station to explore its water fingerprint" hint="Select a river and station using the filters above.">
        <div className="in-detail-grid">
          <div><h3>Satellite surface-water fingerprint</h3><p>For stations with mapped coordinates, NASA OPERA scenes can be used to compare surface-water coverage with earlier usable scenes.</p></div>
          <div><h3>Sample-based visual fingerprint</h3><p>Registered AquaLens stations can show the 20 image descriptors once samples are processed. Comparing deviations requires a matching station reference built from eligible samples.</p></div>
        </div>
      </Card>}
      {view === 'fingerprint' && Number.isFinite(mapStation?.latitude) && Number.isFinite(mapStation?.longitude) && <EarthdataScenes key={mapStation.id} site={mapStation}/>}
      {view === 'fingerprint' && datasetStation && !mapStation && <Card title="Fingerprint unavailable for this archive station"><p>No mapped coordinates are available for satellite analysis. Archive measurements are available under Findings and Context &amp; Lab.</p></Card>}

      {view === 'fingerprint' && station && <div className="in-detail-grid"><FingerprintSummary station={station || datasetStation} current={current} reference={reference} comparison={comparison}/><Card title="Station reference profile" hint="Frozen versions · season and acquisition matched" action={<button className="in-button-solid" disabled={!station} onClick={() => setDialog('baseline')}><Plus size={14}/>Establish reference</button>}>{reference ? <><Status value="provisional reference"/><Meta entries={{'Reference version': `#${reference.id}`, 'Reference images': reference.sample_count, 'Season': reference.season, 'Capture protocol': reference.capture_protocol, 'Period begins': `${date(reference.start)} IST`, 'Period ends': `${date(reference.end)} IST`}}/><p>{reference.notes}</p></> : <Empty>{station ? 'No reference matches the selected observation’s season and capture protocol.' : datasetStation ? 'This dataset station has water-quality measurements only. Select a registered AquaLens station to view an image-based fingerprint.' : 'Select an AquaLens station, then record reference samples.'}</Empty>}<div className="in-method-note"><CircleHelp size={17}/><p>Five distinct eligible samples enable a provisional calculation. Reference count does not establish scientific validity.</p></div>{data?.baselines?.length > 0 && <details><summary>Reference version history ({data.baselines.length})</summary>{data.baselines.map(b => <p key={b.id}>#{b.id} · {b.season} · {b.capture_protocol} · {b.sample_count} samples · {date(b.created_at)} IST</p>)}</details>}</Card><Card className="in-span-all" title="The 20-feature visual signature" hint="Actual RF input schema · individual descriptors have different units"><FeatureTable features={features}/><p className="in-fineprint">An undefined IQR scale is shown as missing. Raw colour, texture and area descriptors are not combined on a shared raw-value axis.</p></Card>{current && <Card className="in-span-all" title="Feature history" hint="Inspect raw values or compare observations against the same frozen reference"><FeatureHistory observations={data?.observations || []} timeline={data?.timeline || []} reference={reference}/></Card>}</div>}
      {view === 'samples' && <><Card title="Observation archive" hint="Images, acquisition metadata and processing traceability" action={<button className="in-button-solid" disabled={!station} onClick={() => setDialog('sample')}><Plus size={14}/>Record sample</button>}>{data?.observations?.length ? <><label className="in-inline-select">Inspect observation<select value={current?.id || ''} onChange={e => update({ observation: e.target.value })}>{data.observations.map(o => <option key={o.id} value={o.id}>#{o.id} · {date(o.timestamp)} IST</option>)}</select></label><div className="in-sample-grid">{data.observations.map(o => <div key={o.id} className={current?.id === o.id ? 'in-sample-selected' : ''}><SampleImage observation={o} label={`Sample #${o.id}`}/><button className="in-text-button" onClick={() => update({ observation: String(o.id) })}>Inspect sample<ArrowUpRight size={14}/></button><Status value={o.processing_status}/></div>)}</div></> : <Empty>{station ? 'The sample archive is empty for this period. Record your first observation.' : 'Select a monitoring station to manage its samples.'}</Empty>}</Card>{current && <Card title={`Acquisition record · Sample #${current.id}`}><Meta entries={{'Captured at': `${date(current.timestamp)} IST`, Camera: current.camera, 'Camera settings': current.camera_settings, Illumination: current.illumination, Preparation: current.preparation, Protocol: current.capture_protocol, Season: current.season, 'Reference eligible': current.eligible ? 'Operator checked' : 'Not selected', 'Processing status': title(current.processing_status), 'Image SHA-256': current.checksum, 'Extractor version': current.feature_extractor_version}}/>{current.processing_error && <p className="in-error">{current.processing_error}</p>}<p>{current.notes}</p></Card>}</>}
      {view === 'findings' && ['Ganga', 'Mahanadi', 'Narmada'].includes(river) && !station && <RiverArchiveFindings river={river} archive={chemicalDataset} sites={datasetFiltered} selected={datasetStation} start={start} end={end} onSelect={selectStation}/>}
      {view === 'findings' && (!['Ganga', 'Mahanadi', 'Narmada'].includes(river) || station) && <FindingsDashboard sites={[...filtered, ...datasetFiltered]} site={datasetStation} station={station} archive={chemicalDataset} gangaSource={gangaDataset.source} data={data} start={start} end={end} onSelect={selectStation} onObservation={id => update({ observation: id })} exportReport={exportReport} busy={busy}>
<><Card title="See what changed" hint="Current, previous and reference images from actual records"><div className="in-three-samples"><SampleImage observation={current} label="Current sample"/><SampleImage observation={data?.previous} label="Previous sample"/><SampleImage observation={data?.reference_observation} label="Reference sample"/></div></Card><div className="in-detail-grid"><Card title="Source-specific change detection" hint="Station-relative exploratory screening">{comparison ? <><Status value={comparison.status}/><Meta entries={{'Mean absolute IQR deviation': number(comparison.anomaly_score), 'Heuristic threshold': comparison.threshold, 'Comparable descriptors': `${comparison.comparable_features} / 20`, 'Repeated-screen flag': comparison.persistent_screening_flag ? '3 consecutive non-reference samples above threshold' : 'Not established'}}/><p>{comparison.is_reference_sample ? 'This image belongs to the reference. Its comparison is descriptive, not an independent anomaly test.' : 'Feature departures identify a change in appearance; contextual and laboratory evidence are needed to interpret it.'}</p><FeatureBars features={features}/></> : <Empty>Select a station observation to compare its visual fingerprint.</Empty>}</Card><Card title="Random Forest classification" hint="Existing model retained · Indian-domain validation not established">{current?.classification ? <><div className="in-classification">{current.classification.predicted_condition}</div><p>{current.classification.disclaimer}</p><Meta entries={{'Model version': current.classification.model_version, 'Probability interpretation': current.classification.probability_note}}/><h3>Global model feature importance</h3><p className="in-fineprint">These model-wide importances do not explain an individual prediction and are not anomaly contributions.</p><div className="in-importance">{Object.entries(current.classification.feature_importances || {}).sort((a, b) => b[1] - a[1]).slice(0, 7).map(([name, value]) => <div key={name}><span>{title(name)}</span><meter min="0" max="1" value={value}/><small>{number(value)}</small></div>)}</div></> : <Empty>{current?.processing_error || 'No RF classification is available for the selected sample.'}</Empty>}</Card></div><Card title="Evidence-based feature findings" hint="Numerical comparisons, without unsupported causal claims">{features.filter(f => f.deviation !== null).length ? features.filter(f => f.deviation !== null).sort((a, b) => Math.abs(b.normalized_deviation || 0) - Math.abs(a.normalized_deviation || 0)).slice(0, 5).map(f => <article className="in-finding" key={f.name}><Activity size={17}/><div><h3>{title(f.name)}</h3><p>Current {number(f.current)} compared with reference median {number(f.baseline?.median)}. Difference: {number(f.deviation)}; IQR-scaled deviation: {number(f.normalized_deviation)}.</p><small>Sample #{current.id} · Reference #{reference?.id} · {current.season} · {current.capture_protocol}</small></div></article>) : <Empty>No matching baseline comparisons are available.</Empty>}</Card></>
      </FindingsDashboard>}
      {remoteOverview && showScoreDetails && !dateError && <section id="remote-score-details" className="in-remote-score-details" aria-label="Detailed laboratory analysis">
        <LaboratoryHealth key={JSON.stringify([river, state, stationId, start, end])} river={river} state={state}
          stationId={stationId} stationName={station?.name || datasetStation?.name} start={start} end={end}/>
      </section>}
      {view === 'evidence' && <ContextLab station={station} site={datasetStation} archive={chemicalDataset} data={data} start={start} end={end} onLab={() => setDialog('laboratory')} onContext={() => setDialog('context')}/>}
      {data?.limitations && view !== 'overview' && <details className="in-limitations"><summary>Methodology & limitations</summary><p>{data.limitations}</p></details>}
        </div>
        {!["findings", "evidence"].includes(view) && <div className="in-map-dashboard-canvas"><StationMap showRivers mapSearch={mapSearch} stations={mapStations} selected={mapStation} onSelect={selectStation}/></div>}
      </section>}
      </>}
      <footer className="in-footer"><span><Waves size={13}/>AquaLens AI · Indian workspace</span><span>Exploratory visual monitoring. Laboratory evidence is required for chemical or safety conclusions.</span></footer>
    </main>
    {dialog && <Dialog title={formTitles[dialog]} close={() => setDialog('')}><DataForm kind={dialog} station={station} analysis={data} close={() => setDialog('')} onSaved={saved}/></Dialog>}
  </div></div>;
}

function FeatureHistory({ observations, timeline, reference }) {
  const [selected, setSelected] = useState('');
  const [scaled, setScaled] = useState(false);
  const names = [...new Set(observations.flatMap(row => Object.keys(row.features || {})))];
  const feature = names.includes(selected) ? selected : names[0];
  const compareToReference = scaled && !!reference;
  const rows = compareToReference
    ? timeline.map(row => ({ timestamp: row.timestamp, value: row.feature_deviations?.[feature] ?? null }))
    : [...observations].reverse().map(row => ({ timestamp: row.timestamp, value: row.features?.[feature] ?? null }));
  const values = rows.map(row => row.value).filter(Number.isFinite);
  const stats = reference?.stats?.[feature];
  if (!feature) return <Empty>No stored feature values in the selected period.</Empty>;
  return <>
    <label className="in-inline-select">Descriptor<select value={feature} onChange={e => setSelected(e.target.value)}>{names.map(name => <option key={name} value={name}>{title(name)}</option>)}</select></label>
    <label className="in-inline-select">Scale<select value={compareToReference ? 'reference' : 'raw'} onChange={e => setScaled(e.target.value === 'reference')}><option value="raw">Raw descriptor</option><option value="reference" disabled={!reference}>Signed deviation in reference IQRs</option></select></label>
    {compareToReference ? <p>{values.length} of {rows.length} observations have a comparable value against reference #{reference.id}. {values.length > 0 && `${values.filter(v => v > 0).length} above, ${values.filter(v => v < 0).length} below, ${values.filter(v => v === 0).length} at the reference median.`} Reference samples and undefined comparisons are excluded.</p> : stats && <p>Reference median: {number(stats.median)} · Middle 50%: {number(stats.q25)}–{number(stats.q75)}.</p>}
    {values.length ? <Timeline metric="value" rows={rows}/> : <Empty>No comparable values for this descriptor and period.</Empty>}
  </>;
}


function GangaDatasetTable({ sites }) {
  return <Card title="Ganga monitoring stations · 2022–2025" hint="Reported DO and BOD measurements. 2025 covers January through October. States are assigned from the locations named in the CSV.">
    <p>Source: {gangaDataset.source}</p>
    <div className="in-table-wrap"><table>
      <thead><tr>{['Station', 'State', ...gangaDataset.headers].map(header => <th key={header}>{header}</th>)}</tr></thead>
      <tbody>{sites.map(site => <tr key={site.id}><th>{site.name}</th><td>{site.state}</td>{site.values.map((value, index) => <td key={index}>{value ?? 'Not reported'}</td>)}</tr>)}</tbody>
    </table></div>
  </Card>;
}

function useGangaArchive(offset, enabled = true) {
  return useQuery({
    enabled,
    queryKey: ['india', 'ganga-archive', offset],
    queryFn: ({ signal }) => get('/india/historical/ganga', { offset }, signal),
    retry: false,
  });
}

function GangaArchive() {
  const [offset, setOffset] = useState(0);
  const query = useGangaArchive(offset);
  const rows = query.data?.records || [];
  const columns = [...new Set(rows.flatMap(Object.keys))];
  return <Card title="Ganga water quality · 2012" hint="Saved historical annual summaries from data.gov.in. Local station and date filters apply only to AquaLens observations.">
    <p><a href="https://www.data.gov.in/resource/water-quality-river-ganga-2012#api" target="_blank" rel="noreferrer">View source and field definitions ↗</a></p>
    {query.isSuccess && <p>Saved snapshot: {query.data.available_total} of {query.data.source_total} source records.</p>}
    {query.isPending && <p role="status">Loading historical records…</p>}
    {query.isError && <p role="alert" className="in-error">{errorText(query.error)} <button onClick={() => query.refetch()}>Retry</button></p>}
    {query.isSuccess && (rows.length ? <div className="in-table-wrap"><table>
      <thead><tr>{columns.map(column => <th key={column}>{query.data.labels?.[column] || column.replaceAll('_', ' ')}</th>)}</tr></thead>
      <tbody>{rows.map((row, index) => <tr key={offset + index}>{columns.map(column => <td key={column}>{row[column] == null || row[column] === '' ? '—' : String(row[column])}</td>)}</tr>)}</tbody>
    </table></div> : <Empty>No records on this page.</Empty>)}
    <div className="in-filter-actions">
      <button className="in-button-outline" disabled={!offset || query.isFetching} onClick={() => setOffset(offset - 10)}>Previous</button>
      <button className="in-button-outline" disabled={!query.data?.has_more || query.isFetching || offset >= 10000} onClick={() => setOffset(offset + 10)}>Next</button>
    </div>
  </Card>;
}

function CwcOverview({ dataset, sites, start, end, archive, onSelect }) {
  const [page, setPage] = useState(0);
  const rows = sites.flatMap(site => site.observations.filter(([date]) =>
    (!start || date.slice(0, 10) >= start) && (!end || date.slice(0, 10) <= end))
    .map(row => ({ site, row }))).sort((a, b) => b.row[0].localeCompare(a.row[0]));
  const pageIndex = Math.min(page, Math.max(0, Math.ceil(rows.length / 20) - 1));
  const isNarmada = dataset === narmada;
  const columns = isNarmada
    ? (archive ? narmada.headers : ['pH', 'Dissolved Oxygen', 'BOD']).map(label => [label, narmada.headers.indexOf(label) + 2])
    : [['pH', 2], ['DO (mg/L)', 3], ['TDS (mg/L)', 4]];
  const visible = archive ? rows.slice(pageIndex * 20, pageIndex * 20 + 20) : rows.slice(0, 3);
  return <>
    {!archive && <Card title="Monitoring network" hint={isNarmada ? "Narmada historical monitoring" : "CWC historical chemical monitoring"}>
      <p>{sites.length} stations · {rows.length} records in the selected period</p>
      <div className="in-station-list">{sites.map(site => <button type="button" key={site.id} onClick={() => onSelect(site.id)}>{site.name} · {isNarmada ? site.state : site.district}</button>)}</div>
    </Card>}
    <Card title={archive ? (isNarmada ? 'Narmada measurement archive' : 'CWC measurement archive') : 'Latest available measurements'} hint={isNarmada ? "Historical CSV readings; units are shown where the source specifies them." : "Historical readings from the Central Water Commission"}>
      {!rows.length ? <Empty>No reported measurements match the selected dates.</Empty> : <div className="in-table-wrap"><table>
        <thead><tr>{['Station', 'Sample date', ...columns.map(([label]) => label)].map(label => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{visible.map(({ site, row }) => <tr key={row[1]}><th scope="row">{site.name}</th><td>{row[0].replace('T', ' ')}</td>{columns.map(([label, index]) => <td key={label}>{row[index] ?? 'Not reported'}</td>)}</tr>)}</tbody>
      </table></div>}
      {archive && rows.length > 20 && <div className="in-filter-actions"><button type="button" disabled={!pageIndex} onClick={() => setPage(pageIndex - 1)}>Previous</button><button type="button" disabled={(pageIndex + 1) * 20 >= rows.length} onClick={() => setPage(pageIndex + 1)}>Next</button></div>}
      <p>Source: {dataset.source}</p>
    </Card>
  </>;
}

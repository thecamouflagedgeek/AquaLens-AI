import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Circle, CircleMarker, Popup, useMap, useMapEvents } from 'react-leaflet';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, BarChart, Bar } from 'recharts';
import { MapPin, ArrowUpRight, Waves } from 'lucide-react';
import { api } from '../api';
import 'leaflet/dist/leaflet.css';
import { RiverLines, riverPositions } from './RiverLayer';

export const seasons = ['Pre-monsoon', 'Monsoon', 'Post-monsoon', 'Winter', 'Unspecified'];
export const rivers = ['Ganga', 'Mahanadi', 'Godavari', 'Narmada'];
export const number = v => typeof v === 'number' && Number.isFinite(v) ? new Intl.NumberFormat('en-IN', { maximumFractionDigits: 3 }).format(v) : '—';
export const date = v => v ? new Date(v).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) : 'Not recorded';
export const title = v => (v || '').replaceAll('_', ' ');
export const errorText = e => {
  const detail = e.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(d => `${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ');
  return e.message || 'Unable to load the Indian monitoring API.';
};
export function Empty({ children = 'No records available yet.', icon: Icon = Waves }) { return <div className="in-empty"><Icon size={25} strokeWidth={1.3}/><p>{children}</p></div>; }
export function Card({ title: heading, hint, action, className = '', children }) { return <section className={`in-card ${className}`}><div className="in-card-head"><div><h2>{heading}</h2>{hint && <p>{hint}</p>}</div>{action}</div>{children}</section>; }
export function Status({ value = 'not available' }) { return <span className={`in-status ${value?.includes('anomaly') ? 'in-status-warn' : ''}`}>{title(value)}</span>; }
export function SampleImage({ observation, label }) {
  const [src, setSrc] = useState(''); const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true, url; const controller = new AbortController(); setSrc(''); setFailed(false);
    if (observation) api.get(`/india/observations/${observation.id}/image`, { responseType: 'blob', signal: controller.signal }).then(res => { url = URL.createObjectURL(res.data); if (active) setSrc(url); else URL.revokeObjectURL(url); }).catch(e => { if (active && e.code !== 'ERR_CANCELED') setFailed(true); });
    return () => { active = false; controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [observation?.id]);
  return <figure className="in-sample">{src && !failed ? <img src={src} alt={`${label} water sample`} onError={() => setFailed(true)}/> : <Empty>{failed ? 'Original image unavailable.' : observation ? 'Loading original image…' : 'No sample recorded.'}</Empty>}<figcaption><strong>{label}</strong><span>{date(observation?.timestamp)} {observation && 'IST'}</span></figcaption></figure>;
}
// Click-to-pick handler. Rendered only while a caller explicitly turns picking on, so the
// map stays inert for every other screen that reuses StationMap.
function MapPicker({ enabled, onPickPoint }) {
  useMapEvents({
    click(event) {
      if (!enabled || !onPickPoint) return;
      onPickPoint({ latitude: event.latlng.lat, longitude: event.latlng.lng });
    },
  });
  return null;
}

function MapFocus({ stations, selected, countryOverview, mapSearch, pickedPoint }) {
  const map = useMap();
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  useEffect(() => { map.invalidateSize(); if (pickedPoint) map.flyTo([pickedPoint.latitude, pickedPoint.longitude], Math.max(map.getZoom(), 11), { animate: !matchMedia('(prefers-reduced-motion: reduce)').matches }); else if (selected) map.flyTo([selected.latitude, selected.longitude], 11, { animate: !matchMedia('(prefers-reduced-motion: reduce)').matches }); else if (mapSearch?.river && riverPositions(mapSearch.river).length) map.fitBounds(riverPositions(mapSearch.river), { padding: [24, 24], maxZoom: 9 }); else if (countryOverview) map.fitBounds([[7, 67], [37, 98]], { padding: [18, 18] }); else if (stations.length) map.fitBounds(stations.map(s => [s.latitude, s.longitude]), { padding: [35, 35], maxZoom: 10 }); else map.setView([22.5, 80.5], 4); }, [map, pickedPoint?.latitude, pickedPoint?.longitude, selected?.id, countryOverview, mapSearch, stations.map(s => s.id).join(',')]);
  return null;
}
export function StationMap({
  stations,
  selected,
  onSelect,
  showRivers = false,
  mapSearch,
  layerControls = false,
  pickMode = false,
  onPickPoint,
  pickedPoint,
  pickBufferM,
}) {
  const [tileError, setTileError] = useState(false);
  const [satellite, setSatellite] = useState(false);
  const [riverLayer, setRiverLayer] = useState(true);
  const [stationLayer, setStationLayer] = useState(true);
  const imageryUrl = import.meta.env.VITE_INDIA_SATELLITE_TILE_URL;
  const imageryLabel = import.meta.env.VITE_INDIA_SATELLITE_LABEL;
  const imageryCredit = import.meta.env.VITE_INDIA_SATELLITE_ATTRIBUTION;
  const canShowImagery = imageryUrl && imageryLabel && imageryCredit;
  const showImagery = canShowImagery && satellite;
  return <div className={`in-map${pickMode ? ' in-map-picking' : ''}`}><MapContainer center={[22.5, 80.5]} zoom={4} scrollWheelZoom={false}>{showImagery ? <TileLayer key="imagery" url={imageryUrl} attribution={imageryCredit} maxNativeZoom={14} eventHandlers={{ tileerror: () => setTileError(true) }}/> : <TileLayer key="osm" eventHandlers={{ tileerror: () => setTileError(true) }} url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'/>}{showRivers && riverLayer && <RiverLines/>}<MapPicker enabled={pickMode} onPickPoint={onPickPoint}/><MapFocus stations={stations} selected={selected} countryOverview={showRivers} mapSearch={mapSearch} pickedPoint={pickedPoint}/>{pickedPoint && <><Circle center={[pickedPoint.latitude, pickedPoint.longitude]} radius={pickBufferM || 300} pathOptions={{ color: '#007d70', weight: 2, fillColor: '#007d70', fillOpacity: 0.12 }}/><CircleMarker center={[pickedPoint.latitude, pickedPoint.longitude]} radius={7} pathOptions={{ color: '#fff', weight: 2, fillColor: '#007d70', fillOpacity: 1 }}/></>}{stationLayer && stations.map(s => <CircleMarker key={s.id} center={[s.latitude, s.longitude]} radius={s.id === selected?.id ? 10 : 6} pathOptions={{ color: '#fff', fillColor: s.historical ? '#007d70' : '#0D47A1', fillOpacity: 1, weight: 2 }} eventHandlers={{ click: () => onSelect(String(s.id)) }}><Popup><strong>{s.name}</strong><p>{s.river} · {s.state}</p>{s.historical && s.river !== 'Ganga' ? <small>{s.river === 'Narmada' ? 'Narmada historical station' : 'CWC historical station'}<br/>{s.coordinate_source}</small> : s.historical ? <small>Historical station · <a href={s.coordinate_source} target="_blank" rel="noreferrer">CPCB coordinates</a><br/>Jan–Oct 2025: DO {s.values[3] ?? 'not reported'} · BOD {s.values[7] ?? 'not reported'} (mg/L)</small> : <small>{s.coordinate_status}<br/>{s.coordinate_source}</small>}<br/><button onClick={() => onSelect(String(s.id))}>Select station</button></Popup></CircleMarker>)}</MapContainer>{layerControls && <fieldset className="in-remote-map-layers"><legend>Map layers</legend>
      <label><input type="checkbox" checked={!!showImagery} disabled={!canShowImagery}
        onChange={event => { setTileError(false); setSatellite(event.target.checked); }}/> {canShowImagery ? imageryLabel : 'Satellite imagery unavailable'}</label>
      <label><input type="checkbox" checked={riverLayer} onChange={event => setRiverLayer(event.target.checked)}/> River network</label>
      <label><input type="checkbox" checked={stationLayer} onChange={event => setStationLayer(event.target.checked)}/> Monitoring stations</label>
    </fieldset>}{!layerControls && canShowImagery && <button type="button" className="in-map-layer-toggle" aria-pressed={!!showImagery} onClick={() => { setTileError(false); setSatellite(value => !value); }}>{showImagery ? 'Back to OpenStreetMap' : imageryLabel}</button>}{tileError && <div className="in-map-error" role="status">{showImagery ? 'Satellite imagery could not be loaded. Switch back to OpenStreetMap.' : 'OpenStreetMap tiles could not be loaded.'}</div>}{!stations.length && <div className="in-map-note"><MapPin size={14}/> Register a station to place its recorded coordinates on the map.</div>}</div>;
}
export function Timeline({ rows = [], metric = 'visual_stability_score' }) {
  if (!rows.some(r => Number.isFinite(r[metric]))) return <Empty>No comparable, non-reference observations are available for this trend.</Empty>;
  return <div className="in-chart in-timeline"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}><CartesianGrid stroke="#e6eff0" strokeDasharray="3 5" vertical={false}/><XAxis dataKey="timestamp" tickFormatter={v => new Date(v).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short' })} tick={{ fontSize: 10 }} tickLine={false} axisLine={false}/><YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false}/><Tooltip labelFormatter={date} formatter={number}/><Line dataKey={metric} name={title(metric)} stroke="#0D47A1" strokeWidth={2.5} dot={{ r: 3, fill: '#0D47A1' }} connectNulls={false}/></LineChart></ResponsiveContainer></div>;
}
export function FeatureBars({ features = [] }) {
  const rows = features.filter(f => Number.isFinite(f.normalized_deviation));
  if (!rows.length) return <Empty>Establish a matching reference profile to compare normalized deviations.</Empty>;
  return <div className="in-chart"><ResponsiveContainer width="100%" height={Math.max(280, rows.length * 24)}><BarChart data={rows} layout="vertical" margin={{ left: 0, right: 20 }}><XAxis type="number" tick={{ fontSize: 10 }}/><YAxis dataKey="name" type="category" width={155} tick={{ fontSize: 10 }} tickFormatter={title}/><Tooltip formatter={number}/><Bar dataKey="normalized_deviation" name="Signed IQR-scaled deviation" fill="#0D47A1" radius={[0, 4, 4, 0]}/></BarChart></ResponsiveContainer></div>;
}
export function FeatureTable({ features = [] }) {
  if (!features.length) return <Empty>Upload a sample to extract the model's actual 20 visual features.</Empty>;
  return <div className="in-table-wrap"><table><thead><tr>{['Feature', 'Current', 'Previous', 'Reference median', 'Reference Q25–Q75', 'Deviation', 'IQR-scaled deviation'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{features.map(f => <tr key={f.name}><th>{title(f.name)}</th><td>{number(f.current)}</td><td>{number(f.previous)}</td><td>{number(f.baseline?.median)}</td><td>{f.baseline ? `${number(f.baseline.q25)} – ${number(f.baseline.q75)}` : '—'}</td><td>{number(f.deviation)}</td><td>{number(f.normalized_deviation)}</td></tr>)}</tbody></table></div>;
}
export function Meta({ entries }) { return <dl className="in-meta">{Object.entries(entries).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v ?? 'Not recorded'}</dd></div>)}</dl>; }
export function ViewButton({ onClick, children }) { return <button className="in-text-button" onClick={onClick}>{children}<ArrowUpRight size={15}/></button>; }

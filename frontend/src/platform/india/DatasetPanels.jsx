import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, get } from '../api';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import { Card, Empty, errorText, number } from './shared';

function useDataset(path, params) {
  return useQuery({ queryKey: ['india', 'datasets', path, params], queryFn: ({ signal }) => get('/india/datasets/' + path, params, signal), retry: false });
}
function Result({ query, children }) {
  if (query.isPending) return <p role="status">Loading dataset…</p>;
  if (query.isError) return <p role="alert">{errorText(query.error)} <button type="button" onClick={() => query.refetch()}>Retry</button></p>;
  return children(query.data);
}
function Table({ headers, rows }) {
  return rows.length ? <div className="in-table-wrap"><table><thead><tr>{headers.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
    <tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell == null || cell === 'NA' ? 'Not reported' : cell}</td>)}</tr>)}</tbody></table></div> : <Empty>No records in this selection.</Empty>;
}

export function CensusCatalog() {
  const [file, setFile] = useState('');
  const [offset, setOffset] = useState(0);
  const query = useDataset('census', { file, offset });
  const files = useDataset('census');
  return <Card title="First Census of Water Bodies" hint="Inventory records. This export has no coordinates for map pins.">
    <Result query={files}>{data => <label>State file <select value={file} onChange={e => { setFile(e.target.value); setOffset(0); }}>
      <option value="">Choose a census file</option>{data.files.map(name => <option key={name}>{name}</option>)}
    </select></label>}</Result>
    {file && <Result query={query}>{data => <><Table {...data}/><button type="button" disabled={!offset} onClick={() => setOffset(offset - 20)}>Previous</button> <button type="button" disabled={!data.has_more} onClick={() => setOffset(offset + 20)}>Next</button></>}</Result>}
  </Card>;
}
export function RiverMeasurements({ river }) {
  const query = useDataset('measurements/' + river.toLowerCase());
  return <Card title={river + ' water-quality records'} hint={river === 'Mahanadi' ? '2014 station summaries' : '2022–2025 reported measurements'}>
    <Result query={query}>{data => <><p>Source: {data.source}</p><Table {...data}/></>}</Result>
  </Card>;
}

function SatelliteSample({ name }) {
  const query = useDataset('satellite/' + encodeURIComponent(name) + '/features');
  const [image, setImage] = useState('');
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let url;
    api.get('/india/datasets/satellite/' + encodeURIComponent(name) + '/image', { responseType: 'blob', signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) { url = URL.createObjectURL(data); setImage(url); } })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [name]);
  const location = query.data?.location;
  const point = location && [location.latitude, location.longitude];
  return <><div className="in-satellite-preview">
    {image && !failed ? <figure className="in-sample"><img src={image} alt={name} onError={() => setFailed(true)}/><figcaption>{name}</figcaption></figure> : <p role="status">{failed ? 'Image could not be loaded.' : 'Loading image…'}</p>}
    {point ? <div className="in-map"><MapContainer key={name} center={point} zoom={13} scrollWheelZoom={false}>
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'/>
      <CircleMarker center={point} radius={7}><Popup>{name}<br/>{location.source}</Popup></CircleMarker>
    </MapContainer><p>{point.join(', ')} · {location.source}</p></div> : query.isSuccess && <Empty>Exact location unavailable. This image has no verified coordinates.</Empty>}
    </div>
    <Result query={query}>{data => <><p>{data.scope}</p><Table headers={['Descriptor', 'Value']} rows={Object.entries(data).filter(([, v]) => Number.isFinite(v)).map(([k, v]) => [k.replaceAll('_', ' '), number(v)])}/></>}</Result>
  </>;
}

export function SatelliteCatalog() {
  const [offset, setOffset] = useState(0);
  const [name, setName] = useState('');
  const query = useDataset('satellite', { offset });
  return <Card className="in-satellite-card" title="Satellite image dataset" hint="Standalone JPEG samples. No site, acquisition date, or segmentation masks were supplied.">
    <Result query={query}>{data => <><p>{data.total} images in Water Bodies Satellite Imagery.</p>
      <label>Image <select value={name} onChange={e => setName(e.target.value)}><option value="">Choose an image</option>{data.items.map(item => <option key={item}>{item}</option>)}</select></label>
      <div className="in-filter-actions"><button type="button" disabled={!offset} onClick={() => { setName(''); setOffset(offset - 20); }}>Previous</button><button type="button" disabled={offset + 20 >= data.total} onClick={() => { setName(''); setOffset(offset + 20); }}>Next</button></div>
    </>}</Result>
    {name && <SatelliteSample key={name} name={name}/>}
    <p>These descriptors cannot be used to calculate a station baseline, anomaly, or Water Health Score.</p>
  </Card>;
}

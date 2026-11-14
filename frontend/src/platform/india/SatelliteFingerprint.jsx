import { useState } from 'react';
import { Card } from './shared';

const bands = ['blue', 'green', 'red'];
export default function SatelliteFingerprint() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  async function load(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setRows([]); setError('');
    try {
      if (file.size > 5_000_000) throw new Error();
      const { features } = JSON.parse(await file.text());
      const records = features.map(f => f.properties);
      if (!records.length || records.some(r => r?.source !== 'COPERNICUS/S2_SR_HARMONIZED' ||
        !r.reach || !r.scene_id || !Number.isFinite(Date.parse(r.captured)) ||
        !Number.isInteger(r.water_pixels) || r.water_pixels < 10 ||
        bands.some(b => !Number.isFinite(r[b]))) ||
        new Set(records.map(r => r.reach)).size !== 1 ||
        new Set(records.map(r => r.captured.slice(0, 10))).size !== records.length) throw new Error();
      setRows(records.sort((a, b) => Date.parse(a.captured) - Date.parse(b.captured)));
    } catch {
      setError('Import a Sentinel-2 GeoJSON export for one reach, with one usable scene per UTC date.');
    }
  }
  const latest = rows.at(-1);
  const season = row => row.captured.slice(5, 7);
  const reference = latest ? rows.slice(0, -1).filter(row => season(row) === season(latest)) : [];
  return <Card title="Sentinel-2 reach fingerprint" hint="Satellite reflectance · separate from the AquaLens camera model">
    <label>Import Earth Engine GeoJSON <input type="file" accept=".geojson,.json" onChange={load}/></label>
    {error && <p role="alert">{error}</p>}
    {latest && <><p>{latest.reach} · {latest.captured} · Scene {latest.scene_id} · {latest.water_pixels} water pixels</p>
    <p>{reference.length} earlier scenes from the same calendar month. Five are required for a provisional baseline.</p>
    <table><thead><tr><th>Band</th><th>Latest reflectance</th><th>Reference median</th><th>Difference</th></tr></thead><tbody>
      {bands.map(b => {
        const values = reference.map(r => r[b]).sort((a, z) => a - z);
        const median = values.length >= 5 ? (values[Math.floor((values.length - 1) / 2)] + values[Math.floor(values.length / 2)]) / 2 : null;
        return <tr key={b}><th scope="row">{b}</th><td>{latest[b].toFixed(4)}</td><td>{median?.toFixed(4) ?? '—'}</td><td>{median === null ? '—' : (latest[b] - median).toFixed(4)}</td></tr>;
      })}
    </tbody></table></>}
    <p>Exploratory surface reflectance only. This does not estimate DO, BOD, pH, or water safety. Imports stay in this browser view until it is closed or refreshed.</p>
  </Card>;
}

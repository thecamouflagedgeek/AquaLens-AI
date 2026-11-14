import React, { useEffect, useRef, useState } from 'react';
import { X, UploadCloud } from 'lucide-react';
import { api } from '../api';
import { rivers, seasons, errorText, date } from './shared';

export function Dialog({ title, close, children }) {
  const dialog = useRef(null);
  useEffect(() => { const element = dialog.current; element.showModal(); return () => element.close(); }, []);
  return <dialog className="in-dialog" ref={dialog} onCancel={e => { e.preventDefault(); close(); }}><div className="in-dialog-heading"><div><span>INDIAN WORKSPACE</span><h2>{title}</h2></div><button aria-label="Close dialog" type="button" onClick={close}><X size={20}/></button></div>{children}</dialog>;
}
export function Field({ label, children, ...props }) { return <label className="in-field"><span>{label}</span>{children || <input {...props}/>}</label>; }
function Select({ name, values, required = true, ...props }) { return <select name={name} required={required} {...props}><option value="">Select…</option>{values.map(v => <option key={v} value={v}>{v}</option>)}</select>; }

export default function DataForm({ kind, station, analysis, close, onSaved }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [fileName, setFileName] = useState('PNG, JPEG or WebP · up to 12 MB');
  const [season, setSeason] = useState(''); const [protocol, setProtocol] = useState('');
  const [selected, setSelected] = useState([]);
  const sampleChoices = (analysis?.observations || []).filter(o => o.eligible && o.season === season && o.capture_protocol === protocol);
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    const form = new FormData(event.currentTarget); const body = Object.fromEntries(form);
    try {
      let path, payload;
      if (kind === 'station') { path = '/india/stations'; payload = { ...body, latitude: Number(body.latitude), longitude: Number(body.longitude) }; }
      if (kind === 'sample') {
        path = `/india/stations/${station.id}/observations`;
        const { image, ...metadata } = body;
        payload = new FormData(); payload.append('image', image);
        payload.append('metadata', JSON.stringify({ ...metadata, timestamp: new Date(body.timestamp).toISOString(), eligible: body.eligible === 'on' }));
      }
      if (kind === 'baseline') { path = `/india/stations/${station.id}/fingerprint`; payload = { ...body, observation_ids: selected, season, capture_protocol: protocol }; }
      if (kind === 'laboratory' || kind === 'context') {
        path = `/india/stations/${station.id}/evidence/${kind}`;
        payload = { ...body, observation_id: body.observation_id ? Number(body.observation_id) : null, value: Number(body.value), timestamp: new Date(body.timestamp).toISOString() };
      }
      if (kind === 'action') { path = `/india/stations/${station.id}/actions`; payload = { ...body, observation_id: analysis?.current?.id || null }; }
      const result = await api.post(path, payload, { timeout: kind === 'sample' ? 120000 : 20000 });
      await onSaved(kind, result.data); close();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  return <form className="in-form" onSubmit={submit}>
    {kind === 'station' && <><p className="in-form-note">Register a real sampling location. Coordinates remain operator-registered with the supplied provenance; no independent verification is implied.</p><Field label="Station / river stretch name" name="name" required maxLength={160}/><div className="in-form-row"><Field label="River"><Select name="river" values={rivers}/></Field><Field label="State / union territory" name="state" required maxLength={80}/></div><div className="in-form-row"><Field label="Latitude" name="latitude" type="number" step="any" min="6" max="38" required/><Field label="Longitude" name="longitude" type="number" step="any" min="68" max="98" required/></div><Field label="Coordinate provenance (survey, GPS record or authoritative source)" name="coordinate_source" required minLength={4} maxLength={500}/></>}
    {kind === 'sample' && <><p className="in-form-note">Original images are retained. Use the same chamber, camera, illumination and preparation for comparable observations. RF outputs remain exploratory for Indian samples.</p><label className="in-file"><UploadCloud size={26}/><strong>Choose a water sample image</strong><span>{fileName}</span><input type="file" name="image" accept="image/png,image/jpeg,image/webp" required onChange={e => setFileName(e.target.files[0]?.name || 'Choose an image')}/></label><div className="in-form-row"><Field label="Sampling time (your device's local timezone)" type="datetime-local" name="timestamp" required/><Field label="Operator-assigned season"><Select name="season" values={seasons}/></Field></div><Field label="Camera model" name="camera" required minLength={2} maxLength={160}/><Field label="Camera settings (exposure, ISO, white balance, resolution)" name="camera_settings" required minLength={2} maxLength={500}/><Field label="Illumination conditions" name="illumination" required minLength={2} maxLength={300}/><Field label="Sample preparation / chamber protocol" name="preparation" required minLength={2} maxLength={500}/><Field label="Capture protocol identifier (use the exact same ID for comparable samples)" name="capture_protocol" required minLength={2} maxLength={300}/><label className="in-checkbox"><input name="eligible" type="checkbox"/>I have checked this sample's acquisition quality and eligibility for a future reference profile.</label><Field label="Notes"><textarea name="notes" maxLength={2000}/></Field></>}
    {kind === 'baseline' && <><p className="in-form-note">Select at least five distinct, quality-checked reference images from one season and capture protocol. This creates a frozen provisional reference version; it does not validate the method.</p><Field label="Reference season"><Select name="season" values={seasons} value={season} onChange={e => { setSeason(e.target.value); setSelected([]); }}/></Field><Field label="Capture protocol"><Select name="capture_protocol" values={[...new Set((analysis?.observations || []).filter(o => o.eligible && o.season === season).map(o => o.capture_protocol))]} value={protocol} onChange={e => { setProtocol(e.target.value); setSelected([]); }}/></Field><div className="in-reference-choices">{sampleChoices.map(o => <label className="in-checkbox" key={o.id}><input type="checkbox" checked={selected.includes(o.id)} onChange={e => setSelected(old => e.target.checked ? [...old, o.id] : old.filter(id => id !== o.id))}/>#{o.id} · {date(o.timestamp)} IST</label>)}{!sampleChoices.length && <p>No eligible samples match this reference context.</p>}</div><small>{selected.length} reference images selected</small><Field label="Reference selection rationale" name="notes" minLength={4} maxLength={2000} required/></>}
    {(kind === 'laboratory' || kind === 'context') && <><p className="in-form-note">Enter actual measured results and their source. Do not enter values inferred from an image. Station-level records remain unpaired unless an observation is selected.</p><Field label="Paired observation (optional)"><select name="observation_id"><option value="">Unpaired station measurement</option>{(analysis?.observations || []).map(o => <option key={o.id} value={o.id}>#{o.id} · {date(o.timestamp)}</option>)}</select></Field><Field label={kind === 'laboratory' ? 'Measured laboratory parameter (e.g. pH, turbidity, DO)' : 'Context parameter (e.g. rainfall, discharge, water level)'} name="parameter" required minLength={2} maxLength={100}/><div className="in-form-row"><Field label="Measured value" name="value" type="number" step="any" required/><Field label="Unit (use dimensionless for pH)" name="unit" required maxLength={50}/></div><Field label="Measurement time (your device's local timezone)" name="timestamp" type="datetime-local" required/><Field label="Provenance / laboratory / instrument / source document" name="provenance" required minLength={4} maxLength={500}/><Field label="Notes / measurement limitations"><textarea name="notes" maxLength={2000}/></Field></>}
    {kind === 'action' && <><p className="in-form-note">Create an evidence-linked monitoring task. Priority is assigned by the operator; no optimized intervention is claimed.</p><Field label="Observed concern" name="concern" required minLength={4} maxLength={300}/><Field label="Supporting evidence / observation / laboratory record"><textarea name="evidence" minLength={4} maxLength={2000} required/></Field><Field label="Suggested follow-up action"><textarea name="suggested_action" minLength={4} maxLength={2000} required/></Field><Field label="Operator-assigned priority"><Select name="priority" values={['Routine', 'Review', 'High']}/></Field></>}
    {error && <p className="in-error" role="alert">{error}</p>}
    <div className="in-form-actions"><button type="button" onClick={close} disabled={busy}>Cancel</button><button className="in-button-solid" disabled={busy || (kind === 'baseline' && selected.length < 5)}>{busy ? 'Saving…' : kind === 'baseline' ? 'Establish reference' : 'Save record'}</button></div>
  </form>;
}

export function ActionCard({ action, refresh }) {
  const [status, setStatus] = useState(action.status); const [remarks, setRemarks] = useState(action.remarks || '');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  return <article className="in-action"><div><span className="in-status">{action.priority} priority</span><h3>{action.concern}</h3></div><dl><dt>Evidence</dt><dd>{action.evidence}</dd><dt>Suggested action</dt><dd>{action.suggested_action}</dd></dl><small>{action.priority_basis} · Observation {action.observation_id || 'not paired'}</small><form className="in-form" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); try { await api.patch(`/india/actions/${action.id}`, { status, remarks }); await refresh(); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } }}><Field label="Follow-up status"><Select values={['Open', 'Reviewed', 'In progress', 'Completed']} value={status} onChange={e => setStatus(e.target.value)}/></Field><Field label="Remarks"><textarea maxLength={2000} value={remarks} onChange={e => setRemarks(e.target.value)}/></Field>{error && <p className="in-error" role="alert">{error}</p>}<button className="in-button-solid" disabled={busy}>{busy ? 'Saving…' : 'Save follow-up'}</button></form><details><summary>Follow-up history ({action.history?.length || 0})</summary>{action.history?.map((h, i) => <p key={i}>{date(h.timestamp)} IST · {h.status} · {h.remarks}</p>)}</details></article>;
}

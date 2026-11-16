import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, get } from '../api';
import { Card, Empty, errorText, number, title } from './shared';

const DEFAULT_BUFFER_M = 300;
const DEFAULT_MONTHS = 24;
// `interrupted` is terminal: the worker thread died with a previous backend process, so polling
// would never resolve. The user retries through the same retrieval button.
const TERMINAL = ['completed', 'failed', 'interrupted'];

const monthName = value =>
  new Date(`${value}-01T00:00:00Z`).toLocaleDateString('en-IN', {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });

const monthRange = (count = DEFAULT_MONTHS) => {
  const today = new Date();
  const end = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - 1, 1));
  const start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - (count - 1), 1));
  const iso = date => `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
  const months = [];
  for (let cursor = start; cursor <= end; cursor = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 1))) {
    months.push(iso(cursor));
  }
  return { startMonth: iso(start), endMonth: iso(end), months };
};

const picture = value => (Number.isFinite(value) ? value.toFixed(4) : '—');
const squareKm = value =>
  Number.isFinite(value)
    ? `${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 4 }).format(value)} km²`
    : '—';

/**
 * Location-driven Sentinel-2 history.
 *
 * Satellite-derived values are deliberately kept in their own panel and are never merged
 * into the camera fingerprint or the Water Health Score. Missing months stay missing:
 * they are plotted as gaps and listed explicitly.
 */
export default function SatelliteHistory({ site, pickMode = false, picked = null, onTogglePick, onClearPick }) {
  const cache = useQueryClient();
  const [threshold, setThreshold] = useState(0);
  const [jobId, setJobId] = useState(null);
  const [custom, setCustom] = useState(null);
  const [customDraft, setCustomDraft] = useState({ latitude: '', longitude: '', buffer: DEFAULT_BUFFER_M });

  // A map-picked point is a buffered area around one coordinate, not a drawn river polygon.
  const fromMap = !!picked && Number.isFinite(picked.latitude) && Number.isFinite(picked.longitude);
  const buffer = fromMap ? picked.buffer ?? DEFAULT_BUFFER_M : custom ? custom.buffer : DEFAULT_BUFFER_M;
  const latitude = fromMap ? picked.latitude : custom ? custom.latitude : site?.latitude;
  const longitude = fromMap ? picked.longitude : custom ? custom.longitude : site?.longitude;
  const name = fromMap
    ? `Map point ${picked.latitude.toFixed(4)}, ${picked.longitude.toFixed(4)}`
    : custom
      ? custom.name
      : site?.name;
  const located = Number.isFinite(latitude) && Number.isFinite(longitude);
  const window = useMemo(() => monthRange(DEFAULT_MONTHS), []);

  useEffect(() => {
    setJobId(null);
  }, [latitude, longitude, buffer, custom, picked]);

  // Selecting a mapped station is a different intent from a map-picked point, so a station
  // selection supersedes the pick instead of being silently outranked by it.
  useEffect(() => {
    if (site?.id) onClearPick?.();
  }, [site?.id]);

  const aoi = useQuery({
    queryKey: ['satellite', 'aoi', name, latitude, longitude, buffer],
    enabled: located,
    retry: false,
    staleTime: Infinity,
    queryFn: async () => {
      const { data } = await api.post('/satellite/aois/resolve', {
        name: name || 'Selected area',
        latitude,
        longitude,
        buffer_m: buffer,
        station_ref: fromMap || custom ? null : site?.id ? `station:${site.id}` : null,
      });
      return data;
    },
  });

  const aoiId = aoi.data?.aoi?.id || null;
  const observations = useQuery({
    queryKey: ['satellite', 'observations', aoiId, window.startMonth, window.endMonth, threshold],
    enabled: !!aoiId,
    retry: false,
    queryFn: ({ signal }) =>
      get(
        `/satellite/aois/${aoiId}/observations`,
        {
          start_month: window.startMonth,
          end_month: window.endMonth,
          ndwi_threshold: threshold,
        },
        signal,
      ),
  });

  const job = useQuery({
    queryKey: ['satellite', 'job', jobId],
    enabled: !!jobId,
    retry: false,
    refetchInterval: query =>
      TERMINAL.includes(query.state.data?.status) ? false : 2500,
    queryFn: ({ signal }) => get(`/satellite/jobs/${jobId}`, undefined, signal),
  });

  useEffect(() => {
    if (job.data && TERMINAL.includes(job.data.status)) {
      cache.invalidateQueries({ queryKey: ['satellite', 'observations', aoiId] });
    }
  }, [job.data?.status, cache, aoiId]);

  const request = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(`/satellite/aois/${aoiId}/fetch`, {
        start_month: window.startMonth,
        end_month: window.endMonth,
        ndwi_threshold: threshold,
      });
      return data;
    },
    onSuccess: data => {
      setJobId(data.job?.id ?? null);
      cache.invalidateQueries({ queryKey: ['satellite', 'observations', aoiId] });
    },
  });

  const payload = observations.data;
  const items = payload?.items || [];
  const availability = payload?.availability;

  const series = useMemo(() => {
    const byMonth = new Map(items.map(item => [item.month, item]));
    return window.months.map(month => {
      const row = byMonth.get(month);
      return {
        month,
        label: monthName(month),
        ndwi: row && Number.isFinite(row.ndwi_mean) ? row.ndwi_mean : null,
        area: row && Number.isFinite(row.water_area_km2) ? row.water_area_km2 : null,
        status: row ? row.status : 'not_fetched',
        scenes: row ? row.scene_count : null,
      };
    });
  }, [items, window.months]);

  const hasSeries = series.some(row => row.ndwi !== null || row.area !== null);
  const busy = request.isPending || (job.data && !TERMINAL.includes(job.data.status));
  const error = aoi.error || observations.error || request.error || job.error;
  const missingMonths = series.filter(row => row.status !== 'ok');

  if (!located && !custom) {
    return (
      <Card
        title="Satellite water history (Sentinel-2)"
        hint="Satellite-derived surface-water indicator · separate from camera and laboratory evidence"
      >
        <Empty>Select a station with mapped coordinates, enter a point, or pick one on the map.</Empty>
        {onTogglePick && (
          <button type="button" className="in-button-outline" aria-pressed={pickMode} onClick={onTogglePick}>
            {pickMode ? 'Cancel map selection' : 'Select location on map'}
          </button>
        )}
        <CustomPointForm draft={customDraft} setDraft={setCustomDraft} onApply={setCustom} />
      </Card>
    );
  }

  return (
    <Card
      title="Satellite water history (Sentinel-2)"
      hint="Satellite-derived surface-water indicator · separate from camera and laboratory evidence"
      action={<span className="in-fingerprint-badge">Exploratory</span>}
    >
      <header>
        <div>
          <h3>{name || 'Selected area of interest'}</h3>
          <p>
            {latitude.toFixed(4)}, {longitude.toFixed(4)} ·{' '}
            {aoi.data?.aoi?.area_km2 != null
              ? `${number(aoi.data.aoi.area_km2)} km² AOI`
              : `${buffer} m buffer`}
          </p>
          {fromMap && (
            <p className="in-fineprint">
              Buffered point: a {buffer} m radius circle around the selected coordinate, not a drawn river
              polygon.
            </p>
          )}
        </div>
        {onTogglePick && (
          <button type="button" className="in-button-outline" aria-pressed={pickMode} onClick={onTogglePick}>
            {pickMode ? 'Cancel map selection' : 'Select location on map'}
          </button>
        )}
      </header>
      {pickMode && (
        <p role="status" className="in-fineprint">
          Click anywhere on the map to choose a location. Station markers keep their own selection.
        </p>
      )}

      <div className="in-filter-actions" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <label>
          NDWI threshold
          <input
            type="number"
            step="0.05"
            min="-1"
            max="1"
            value={threshold}
            onChange={event => setThreshold(Number(event.target.value))}
          />
        </label>
        <button
          type="button"
          className="in-button-solid"
          disabled={busy || !aoiId}
          onClick={() => request.mutate()}
        >
          {busy
            ? 'Retrieving satellite history…'
            : job.data?.status === 'interrupted'
              ? 'Retry interrupted months'
              : hasSeries
                ? 'Fill missing months'
                : 'Retrieve satellite history'}
        </button>
      </div>

      {error && <p role="alert" className="in-error">{errorText(error)}</p>}
      {job.data && (
        <p role="status">
          {title(job.data.status)} · {job.data.months_completed}/{job.data.months_total} month(s) processed
          {job.data.months_skipped ? ` · ${job.data.months_skipped} already stored` : ''}
          {job.data.months_failed ? ` · ${job.data.months_failed} failed` : ''}
        </p>
      )}
      {job.data?.error && <p role="alert" className="in-error">{job.data.error}</p>}
      {aoi.isPending && <p role="status">Resolving area of interest…</p>}
      {observations.isPending && aoiId && <p role="status">Loading stored satellite observations…</p>}

      {payload && !hasSeries && (
        <Empty>
          No satellite observations are stored for this area yet. Retrieve the last {DEFAULT_MONTHS} months to
          build the series.
        </Empty>
      )}

      {hasSeries && (
        <>
          <dl className="in-fingerprint-metrics">
            <div>
              <dt>Months with data</dt>
              <dd>
                {availability ? availability.months_with_data : items.filter(i => i.status === 'ok').length}
                {availability ? ` / ${availability.months_expected}` : ''}
              </dd>
            </div>
            <div>
              <dt>Latest NDWI</dt>
              <dd>{picture([...series].reverse().find(row => row.ndwi !== null)?.ndwi)}</dd>
            </div>
            <div>
              <dt>Latest water area</dt>
              <dd>{squareKm([...series].reverse().find(row => row.area !== null)?.area)}</dd>
            </div>
          </dl>

          <h3>Monthly NDWI (B3, B8) · {window.startMonth} to {window.endMonth}</h3>
          <div className="in-coverage-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 10, right: 12, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#e6eff0" strokeDasharray="3 5" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis domain={[-1, 1]} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
                <Tooltip
                  formatter={value => (Number.isFinite(value) ? Number(value).toFixed(4) : 'No usable imagery')}
                  labelFormatter={label => label}
                />
                <Line
                  dataKey="ndwi"
                  name="NDWI (median composite)"
                  stroke="#0D47A1"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: '#0D47A1' }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <h3>Estimated water surface area</h3>
          <div className="in-coverage-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 10, right: 12, left: -12, bottom: 0 }}>
                <CartesianGrid stroke="#e6eff0" strokeDasharray="3 5" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
                <Tooltip formatter={value => (Number.isFinite(value) ? squareKm(value) : 'No usable imagery')} />
                <Legend />
                <Line
                  dataKey="area"
                  name="Water area (km², NDWI ≥ threshold)"
                  stroke="#007d70"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: '#007d70' }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <p>
            NDWI threshold {threshold} · per-pixel median composite of Sentinel-2 Level-2A scenes · 10 m grid ·
            clouds, cloud shadow, cirrus and snow removed with the SCL band.
          </p>
          <p className="in-fineprint">
            NDWI is a spectral water indicator, not a measurement of dissolved oxygen, BOD, turbidity or chemical
            contamination. Water area from an NDWI threshold is an estimate, not surveyed ground truth. Months with
            no usable imagery are shown as gaps and are not treated as zero water.
          </p>

          {missingMonths.length > 0 && (
            <details>
              <summary>{missingMonths.length} month(s) without usable satellite data</summary>
              <div className="in-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>Status</th>
                      <th>Scenes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {missingMonths.map(row => (
                      <tr key={row.month}>
                        <th scope="row">{row.label}</th>
                        <td>{title(row.status)}</td>
                        <td>{row.scenes ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </>
      )}

      {payload && (
        <p className="in-fineprint">
          {payload.collection} · algorithm {payload.algorithm} v{payload.algorithm_version} · cloud filter{' '}
          {payload.max_cloud_pct}% · stored observations only
        </p>
      )}

              <CustomPointForm
          draft={customDraft}
          setDraft={setCustomDraft}
          onApply={value => {
            // Entering coordinates explicitly supersedes a previously picked map point.
            onClearPick?.();
            setCustom(value);
            setCustomDraft({ ...customDraft, latitude: String(value.latitude), longitude: String(value.longitude) });
          }}
        />
    </Card>
  );
}

function CustomPointForm({ draft, setDraft, onApply }) {
  const lat = Number(draft.latitude);
  const lon = Number(draft.longitude);
  const valid =
    Number.isFinite(lat) && lat >= -90 && lat <= 90 && Number.isFinite(lon) && lon >= -180 && lon <= 180;
  return (
    <details>
      <summary>Use a different point</summary>
      <p>Enter WGS84 coordinates to analyse any location. A buffered area is created around the point.</p>
      <div className="in-detail-grid">
        <label>
          Latitude
          <input
            type="number"
            step="0.0001"
            value={draft.latitude}
            onChange={event => setDraft({ ...draft, latitude: event.target.value })}
          />
        </label>
        <label>
          Longitude
          <input
            type="number"
            step="0.0001"
            value={draft.longitude}
            onChange={event => setDraft({ ...draft, longitude: event.target.value })}
          />
        </label>
        <label>
          Buffer (m)
          <input
            type="number"
            step="50"
            min="50"
            max="50000"
            value={draft.buffer}
            onChange={event => setDraft({ ...draft, buffer: Number(event.target.value) })}
          />
        </label>
      </div>
      <button
        type="button"
        className="in-button-outline"
        disabled={!valid}
        onClick={() =>
          onApply({ name: 'Custom point', latitude: lat, longitude: lon, buffer: Number(draft.buffer) || DEFAULT_BUFFER_M })
        }
      >
        Analyse this point
      </button>
    </details>
  );
}

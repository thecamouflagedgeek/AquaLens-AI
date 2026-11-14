import { LayerGroup, Polyline, Tooltip } from 'react-leaflet';
import riverLines from './india-rivers.json';

// Natural Earth 1:10m rivers and lake centerlines (public domain).
// Named river lines intersecting 7–37° N, 67–98° E, rounded to four decimals.
// https://www.naturalearthdata.com/downloads/10m-physical-vectors/
const attribution = 'River lines: <a href="https://www.naturalearthdata.com/downloads/10m-physical-vectors/">Natural Earth</a>';
const aliases = { Ganges: 'Ganga (Ganges)', 'Mahana Nadi': 'Mahanadi' };
const style = { color: '#2196F3', opacity: 0.85, weight: 2 };

export function riverPositions(river) {
  const sourceName = { Ganga: 'Ganges', Mahanadi: 'Mahana Nadi', Narmada: 'Narmada' }[river];
  return riverLines.filter(([name]) => name.normalize('NFD').replace(/\p{M}/gu, '') === sourceName)
    .flatMap(([, positions]) => positions);
}

export function RiverLines() {
  return (
    <LayerGroup attribution={attribution}>
      {riverLines.map(([name, positions], index) => (
        <Polyline key={index} positions={positions} pathOptions={style}>
          <Tooltip sticky>{aliases[name.normalize('NFD').replace(/\p{M}/gu, '')] || name}</Tooltip>
        </Polyline>
      ))}
    </LayerGroup>
  );
}

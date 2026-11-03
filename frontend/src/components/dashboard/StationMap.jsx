import React, { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapPin } from "lucide-react";

// Fix default Leaflet icon paths
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

export default function StationMap({ stations = [], selectedStationId, onSelectStation }) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markersLayerRef = useRef(null);

  const validStations = stations.filter(
    (s) =>
      s.latitude !== null &&
      s.longitude !== null &&
      !isNaN(s.latitude) &&
      !isNaN(s.longitude) &&
      s.latitude !== 0 &&
      s.longitude !== 0
  );

  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      // Initialize map with neutral center
      const defaultCenter = [46.2, -124.0];
      const map = L.map(mapContainerRef.current, {
        center: defaultCenter,
        zoom: 7,
        zoomControl: true,
        attributionControl: true,
        scrollWheelZoom: false, // Prevent accidental scrolling while navigating dashboard
      });

      // Standard OpenStreetMap Tile Layer (no watermark, no API key required)
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
        maxZoom: 18,
      }).addTo(map);

      markersLayerRef.current = L.layerGroup().addTo(map);
      mapInstanceRef.current = map;

      // Invalidate size once container layout stabilizes
      setTimeout(() => {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.invalidateSize();
        }
      }, 150);
    }

    const map = mapInstanceRef.current;
    const markersLayer = markersLayerRef.current;
    markersLayer.clearLayers();

    if (validStations.length === 0) {
      return;
    }

    const bounds = L.latLngBounds();

    validStations.forEach((st) => {
      const isSelected = st.id === selectedStationId;
      const isDemo = st.is_demo === true;
      const markerColor = isSelected ? "#38bdf8" : isDemo ? "#64748b" : "#14b8a6";

      const customIcon = L.divIcon({
        className: "custom-station-pin-container",
        html: `
          <div style="
            width: ${isSelected ? "20px" : "14px"};
            height: ${isSelected ? "20px" : "14px"};
            background: ${markerColor};
            border: 2px solid #ffffff;
            border-radius: 50%;
            box-shadow: 0 0 8px rgba(0,0,0,0.4);
            cursor: pointer;
            transition: transform 0.2s ease;
          "></div>
        `,
        iconSize: [isSelected ? 20 : 14, isSelected ? 20 : 14],
        iconAnchor: [isSelected ? 10 : 7, isSelected ? 10 : 7],
      });

      const marker = L.marker([st.latitude, st.longitude], { icon: customIcon });

      const popupContent = `
        <div style="font-family: 'DM Sans', sans-serif; font-size: 12px; color: #151820; line-height: 1.4; padding: 2px;">
          <strong style="color: #081623; font-size: 13px; display: block; margin-bottom: 2px;">${st.name}</strong>
          <span style="color: #666; font-size: 11px;">Code: ${st.station_code}</span>
          ${isDemo ? '<span style="display:inline-block; margin-left:4px; padding:1px 4px; background:#e2e8f0; color:#475569; font-size:9px; border-radius:2px; font-weight:600;">DEMO</span>' : ""}
          <br/>
          <span style="color: #333;">Baseline: <strong>${st.baseline_status === "established" ? "Established" : "Not established"}</strong></span>
          ${st.latest_condition ? `<br/><span style="color: #333;">Visual category: <strong>${st.latest_condition}</strong></span>` : ""}
        </div>
      `;

      marker.bindPopup(popupContent);

      marker.on("click", () => {
        if (onSelectStation) onSelectStation(st.id);
      });

      markersLayer.addLayer(marker);
      bounds.extend([st.latitude, st.longitude]);
    });

    if (validStations.length > 0) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 11 });
    }
  }, [stations, selectedStationId, onSelectStation]);

  if (validStations.length === 0) {
    return (
      <div className="map-empty-state">
        <MapPin size={28} className="map-empty-icon" />
        <p className="map-empty-title">No geographic coordinates available</p>
        <span className="map-empty-sub">
          Station location coordinates will appear on this map when registered.
        </span>
      </div>
    );
  }

  return (
    <div className="map-inner-container">
      <div ref={mapContainerRef} className="station-map-leaflet" />
    </div>
  );
}

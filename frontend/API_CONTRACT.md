# Monitoring API integration contract

Status: proposed, NOT confirmed. `backend/main.py` was empty during implementation. No endpoints, session implementation, model outputs, or live monitoring results were available for integration testing.

## Transport and security

Set `VITE_API_BASE_URL` in `frontend/.env`. All calls use Axios with credentials and a 20-second timeout. Backend must configure credentialed CORS for the exact frontend origin. Authentication uses a server-managed HttpOnly session cookie (Secure in production, appropriate SameSite policy), never localStorage tokens. Protect state-changing requests against CSRF server-side (Origin validation or a coordinated CSRF token contract). Bearer-token-only backends require an explicit integration change; login is successful only after `/auth/me` verifies the session.

- `POST /auth/login`: JSON `{ username, password }`; establishes cookie. Do not return credentials for browser persistence.
- `GET /auth/me`: user `{ id, name?, username?, email?, role? }`; 401 when unauthenticated.
- `POST /auth/logout`: invalidates session and expires cookie. The UI reports failure instead of pretending an unsuccessful logout terminated the session.

## Common shapes

Collections are arrays or `{ items: [...] }`. Use null for missing values, never zero as a missing sentinel. All observation lists must be newest first. Timestamps must be ISO 8601 with timezone. Numeric values must be JSON numbers. IDs are strings or numbers. Responses must enforce authorization. Every feature name, classification, anomaly status, forecast horizon, and recommendation priority is supplied by the backend.

- `GET /sources`: collection of `{id,name}`.
- `GET /stations?source_id=`: collection of `{id,name,source_id,source_name,latitude,longitude,region?,state?,district?,latest_classification?,latest_anomaly_status?,latest_health_score?}`. Summary score must be validated when present. Coordinates must be real registered coordinates.
- `GET /stations/{id}`: `{id,name,source_name,location}`; 404 for unknown stations.
- `GET /stations/{id}/observations?from=&to=`: newest-first collection of `{id,timestamp,image_url?,classification?,classification_model?,confidence_interpretation?,processing_status?,acquisition_metadata?}`. Apply dates inclusively in a documented timezone. No classification confidence is displayed without backend interpretation.
- `GET /observations/{id}/health-score`: `{validated,score,change?,reliability?,explanation?,unavailable_reason?,methodology_version?,methodology?,normalization?,anomaly_computation?,transformation?,weights?,thresholds?,limitations?}`. Only explicitly validated finite scores in [0,100] are rendered.
- `GET /observations/{id}/anomaly`: `{status,score?,baseline_status?,key_changes?}`.
- `GET /observations/{id}/features`: `{features:[{name,group?,unit?,current,previous?,baseline?,baseline_range?,deviation?,normalized_deviation?,score_contribution?,history?:[{timestamp,value}]}]}`. Return the actual validated schema; the UI reports the actual feature count and does not fabricate a 20-feature list.
- `GET /stations/{id}/fingerprint?observation_id=`: `{status,observation_count,period?,schema_version?,features:[...]}` using the feature shape above. Normalized deviations must use a documented comparable normalization; unavailable or invalid normalizations should be null.
- `GET /stations/{id}/trends?from=&to=`: `{health_score:[{timestamp,value}],anomaly_score:[{timestamp,value}]}`. Only validated score history should be returned.
- `GET /stations/{id}/findings?from=&to=&observation_id=`: `{findings:[{id,observation,feature,comparison_period,magnitude,interpretation,limitations,evidence_ids}],explanations:[{scope,method,feature,value,evidence_ids}],baseline_image_url?,baseline_image_timestamp?}`. Scope must distinguish global classifier importance from local classification explanations and anomaly attribution.
- `GET /stations/{id}/laboratory-results?observation_id=`: collection of `{id,parameter,value,unit,timestamp,provenance}` paired to the selected observation. An empty collection means no paired measurements.
- `GET /stations/{id}/forecast` without parameter: capabilities `{parameters:[{id,name,unit}],supported_horizons:[string],unavailable_reason?}`.
- `GET /stations/{id}/forecast?parameter=&horizon=&from=&to=`: `{validated,history:[{timestamp,value}],forecast:[{timestamp,value,lower?,upper?}],unit?,model,training_period,horizon,metrics,observation_count,data_sufficiency,uncertainty,interpretation?,unavailable_reason?}`. Intervals are rendered only when both bounds exist. Backend validates allowed horizons and data sufficiency.
- `GET /stations/{id}/recommendations?from=&to=`: `{condition?,deviations?,persistent_anomalies?,laboratory_summary?,trend?,recommendations:[{id,concern,evidence,interpretation,suggested_action,priority,priority_criteria,evidence_source,evidence_ids,status?,can_update?,update_url?,allowed_statuses?:[string]}]}`.
- Optional `PATCH /recommendations/{id}` via backend-provided relative `update_url`: `{status,remarks}`. Recheck authorization and allowed transitions server-side and persist before returning success.

Unavailable capabilities should return an explicit reason or an appropriate HTTP error. The frontend does not replace errors with fabricated monitoring results. OpenStreetMap tiles require internet access and retain attribution.

## Verification

Run `npm install` and `npm run build` from `frontend`. With the backend running, verify cookie login/refresh/expiry, direct protected-route access, logout invalidation, station selection across pages, date filtering, observation selection, actual model feature schema, paired laboratory provenance, forecast capability restrictions and persisted recommendation updates. Test empty collections, null values, 401/403/404/5xx, network failures and reduced-motion/mobile layouts. Hosting must rewrite application routes to `index.html`.

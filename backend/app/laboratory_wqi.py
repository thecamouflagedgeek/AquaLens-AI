"""Coverage-aware CCME WQI using CPCB Class B objectives."""
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from .india_datasets import DATA

VERSION = 'ccme-wqi-1.0-cpcb-b-v1'
OBJECTIVES = {'pH': (6.5, 8.5), 'DO': (5, None), 'BOD': (None, 3), 'Total coliform': (None, 500)}
UNITS = {'pH': 'dimensionless', 'DO': 'mg/L', 'BOD': 'mg/L', 'Total coliform': 'MPN/100 mL'}
COLUMNS = {
    'potentialofhydrogenph': 'pH', 'ph': 'pH',
    'dissolvedoxygenmgl': 'DO', 'domgl': 'DO',
    'biochemicaloxygendemandmgl': 'BOD', 'bodmgl': 'BOD', 'biochemicaloxygendemandbodmgl': 'BOD',
    'totalcoliformmpn100ml': 'Total coliform', 'totalcoliformsmpn100ml': 'Total coliform',
}
IST = timezone(timedelta(hours=5, minutes=30))
LAB_PARAMETERS = {
    'ph': 'pH', 'do': 'DO', 'dissolvedoxygen': 'DO',
    'bod': 'BOD', 'biochemicaloxygendemand': 'BOD',
    'totalcoliform': 'Total coliform', 'totalcoliforms': 'Total coliform',
}
CRITERIA = 'https://cpcb.nic.in/wqm/Designated_Best_Use_Water_Quality_Criteria.pdf'
METHOD = 'https://unstats.un.org/unsd/envaccounting/ceea/archive/Water/CCME_Canada.PDF'


# Exact station-name matches in the CPCB 2021 NWMP river report, Uttar Pradesh.
CPCB_2021_STATIONS = {
    'gangaatkannaujusrajghatup': ('1063', 'Ganga'),
    'gangaatkannaujdsup': ('1066', 'Ganga'),
    'gangaatkanpurdsjajmaupumpingstationup': ('10157', 'Ganga'),
    'gangaatdalmauraibareillyup': ('1147', 'Ganga'),
    'gangaatkalakankarraebareli': ('2498', 'Ganga'),
    'gangaatbithoorkanpurup': ('1146', 'Ganga'),
}
CPCB_2021_METADATA = 'https://cpcb.nic.in/wqm/2021/WQuality_River-Data-2021.pdf'


def normalized(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def number(raw):
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def sampling_time(raw):
    try:
        value = datetime.fromisoformat(raw)
        return value.astimezone(IST).replace(tzinfo=None) if value.tzinfo else value
    except ValueError:
        pass
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y', '%d-%m-%Y %H:%M', '%d-%m-%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


@lru_cache(maxsize=16)
def read_archive(path, modified_ns):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        headers = {normalized(key): key for key in reader.fieldnames or ()}
        columns = {key: COLUMNS[token] for token, key in headers.items() if token in COLUMNS}
        output = []
        for row in reader:
            def field(*names):
                return next((row.get(headers[name], '').strip() for name in names if headers.get(name) and row.get(headers[name])), '')
            name, river, state = field('station', 'stationname'), field('river'), field('state')
            if river.upper() in ('-', 'NA', 'N/A'):
                river = ''
            agency = field('agency').upper()
            timestamp = sampling_time(field('dataacquisitiontime', 'samplingdate', 'sampledate', 'date'))
            if not all((name, state, timestamp)) or agency not in ('CPCB', 'CWC'):
                continue
            latitude, longitude = number(field('latitude')), number(field('longitude'))
            coords = (latitude, longitude) if latitude is not None and longitude is not None and 6 <= latitude <= 38 and 68 <= longitude <= 98 else None
            code = field('stationcode', 'stationid', 'stationidentifier', 'monitoringstationcode')
            if code in ('-', 'NA', 'N/A'):
                code = ''
            mapping = CPCB_2021_STATIONS.get(normalized(name)) if agency == 'CPCB' and state.casefold() == 'uttar pradesh' else None
            if mapping and (not code or code == mapping[0]) and (not river or river.casefold() == mapping[1].casefold()):
                code, river = mapping
                metadata_source = CPCB_2021_METADATA
            else:
                metadata_source = None
            identity = [agency, state.casefold(), river.casefold(), code.casefold()]
            if not code:
                identity.extend([Path(path).name, name.casefold(), coords])
            site = dict(id=hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:16],
                        name=name, river=river, state=state, agency=agency, coordinates=coords, station_code=code or None, metadata_source=metadata_source)
            candidates = defaultdict(set)
            for column, key in columns.items():
                value = number(row.get(column))
                if value is not None and value >= 0 and (key != 'pH' or 0 < value <= 14):
                    candidates[key].add(value)
            readings = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
            output.append((site, timestamp, readings, Path(path).name))
        return output


def excursion(key, value):
    minimum, maximum = OBJECTIVES[key]
    if minimum is not None and value < minimum:
        return minimum / value - 1 if value > 0 else math.inf
    if maximum is not None and value > maximum:
        return value / maximum - 1
    return 0


def calculate(samples):
    # Use complete, unambiguous events. Require four distinct sampling dates.
    complete = [(timestamp, values, sources) for timestamp, values, sources in sorted(samples, key=lambda item: item[0])
                if all(key in values for key in OBJECTIVES)]
    if len({timestamp.date() for timestamp, _, _ in complete}) < 4:
        return None
    breakdown = {}
    excursions = []
    for key, (minimum, maximum) in OBJECTIVES.items():
        readings = [values[key] for _, values, _ in complete]
        failures = [excursion(key, value) for value in readings]
        excursions.extend(failures)
        breakdown[key] = dict(unit=UNITS[key], minimum=minimum, maximum=maximum,
                              latest=readings[-1], failures=sum(value > 0 for value in failures),
                              tests=len(readings))
    scope = 25 * sum(item['failures'] > 0 for item in breakdown.values())
    frequency = 100 * sum(value > 0 for value in excursions) / len(excursions)
    nse = sum(excursions) / len(excursions)
    amplitude = 100 - 100 / (1 + nse)
    score = max(0, min(100, 100 - math.sqrt(scope**2 + frequency**2 + amplitude**2) / math.sqrt(3)))
    return dict(score=round(score, 2), factors=dict(scope=scope, frequency=frequency, amplitude=amplitude),
                parameters=breakdown, sample_count=len(complete), first=complete[0][0].isoformat(),
                last=complete[-1][0].isoformat(), sources=sorted(set().union(*(sources for _, _, sources in complete))))


PARTIAL_VERSION = 'cpcb-b-ph-do-continuous-v2'


def partial_rating(parameter, value):
    lower, upper = OBJECTIVES[parameter]
    if parameter == 'pH':
        # The criterion midpoint is the scoring target; either boundary rates 50.
        midpoint = (lower + upper) / 2
        distance = (value - midpoint) / ((upper - lower) / 2)
        return 100 / (1 + distance**2)
    # Concentration-based rating with diminishing returns; the criterion rates 50.
    return 100 * (value / (value + lower))


def calculate_partial(samples):
    paired = [(time, values, sources) for time, values, sources in samples
              if 'pH' in values and 'DO' in values]
    dates = {time.date() for time, _, _ in paired}
    if len(dates) < 4:
        return None
    parameters = {}
    for key in ('pH', 'DO'):
        readings = [values[key] for _, values, _ in paired]
        failures = sum(excursion(key, value) > 0 for value in readings)
        minimum, maximum = OBJECTIVES[key]
        mean_rating = math.fsum(partial_rating(key, value) for value in readings) / len(readings)
        parameters[key] = dict(unit=UNITS[key], minimum=minimum, maximum=maximum,
                               latest=readings[-1], failures=failures, tests=len(readings),
                               weight=0.5, mean_rating=mean_rating, contribution=0.5 * mean_rating)
    return dict(score=round(sum(item['contribution'] for item in parameters.values()), 2),
                parameters=parameters, sample_count=len(paired), sampling_dates=len(dates),
                first=paired[0][0].isoformat(), last=paired[-1][0].isoformat(),
                sources=sorted(set().union(*(sources for _, _, sources in paired))))


def approved_reading(record):
    key = LAB_PARAMETERS.get(normalized(record.get('parameter', '')))
    if not key:
        return None
    unit = normalized(record.get('unit', ''))
    allowed = {'dimensionless', 'unitless', 'ph'} if key == 'pH' else {normalized(UNITS[key])}
    value = number(record.get('value'))
    if unit not in allowed or value is None or value < 0 or (key == 'pH' and not 0 < value <= 14):
        return None
    return key, value


def approved_laboratory_rows(db):
    from sqlalchemy import select
    from .india_models import IndiaRecord, IndiaStation

    statement = select(IndiaRecord, IndiaStation).join(
        IndiaStation, IndiaRecord.station_id == IndiaStation.id,
    ).where(IndiaRecord.kind == 'laboratory')
    for row, station in db.execute(statement):
        record = json.loads(row.payload)
        approval = record.get('wqi_approval')
        reading = approved_reading(record)
        if not approval or not reading:
            continue
        site = json.loads(station.payload)
        coords = (site['latitude'], site['longitude'])
        yield (
            dict(id=str(station.id), name=site['name'], river=site['river'], state=site['state'],
                 agency='Approved laboratory', coordinates=coords),
            sampling_time(record['timestamp']), dict([reading]),
            record['provenance'] + ' · ' + approval['report_reference'], json.dumps([approval['report_reference'], approval['sample_id']]),
        )


def assessment(river='', station='', start=None, end=None, state='', db=None):
    files = sorted(set(DATA.glob('swq_manual_chemical_parameters_cwc_*.csv'))
                   | set(DATA.glob('swq_*_parameter_manual_cpcb_*.csv'))
                   | set((DATA / 'cpcb').glob('*.csv')))
    sites, events = {}, defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    provenance = defaultdict(set)

    def add(site, timestamp, readings, source, sample_id=''):
        if (river and site['river'].casefold() != river.casefold()) or (state and site['state'].casefold() != state.casefold()):
            return
        key = site['id']
        if station and station != key:
            return
        sites.setdefault(key, site)
        if timestamp is None or (start and timestamp.date() < start) or (end and timestamp.date() > end):
            return
        event_key = (timestamp, sample_id)
        event = events[key][event_key]
        for parameter, value in readings.items():
            event[parameter].add(value)
        provenance[key, event_key].add(source)

    for path in files:
        for row in read_archive(str(path), path.stat().st_mtime_ns):
            add(*row)
    if db is not None:
        for row in approved_laboratory_rows(db):
            add(*row)

    def aggregate(values):
        scores = [item['score'] for item in values if item]
        return round(sum(scores) / len(scores), 2) if scores else None

    result, yearly, partial_yearly = [], defaultdict(list), defaultdict(list)
    for key, site in sites.items():
        if station and station != key:
            continue
        samples = [(event[0], {p: next(iter(v)) for p, v in fields.items() if len(v) == 1}, provenance[key, event])
                   for event, fields in sorted(events[key].items())]
        periods = defaultdict(list)
        for sample in samples:
            periods[sample[0].year].append(sample)
        score = calculate(samples)
        for year, items in periods.items():
            yearly[year].append(calculate(items))
            partial_yearly[year].append(calculate_partial(items))
        available = {parameter for _, values, _ in samples for parameter in values}
        complete_dates = len({timestamp.date() for timestamp, values, _ in samples
                              if OBJECTIVES.keys() <= values.keys()})
        missing = [parameter for parameter in OBJECTIVES if parameter not in available]
        reason = None
        if score is None:
            if not samples:
                reason = 'No dated measurements in the selected period.'
            elif missing:
                reason = 'Missing required measurements: ' + ', '.join(missing) + '.'
            else:
                reason = f'{complete_dates} of 4 required sampling dates have all four unambiguous readings.'
        result.append(dict(site, assessment=score, partial_assessment=calculate_partial(samples), observed_events=len(samples),
                           available_parameters=sorted(available), complete_sampling_dates=complete_dates,
                           parameter_sampling_dates={
                               parameter: len({timestamp.date() for timestamp, values, _ in samples if parameter in values})
                               for parameter in OBJECTIVES
                           },
                           missing_parameters=missing, ineligibility_reason=reason))
    scored = [site['assessment'] for site in result if site['assessment']]
    overall = aggregate(scored) if river or station else None
    partial = [site['partial_assessment'] for site in result if site['partial_assessment']]
    return dict(available_rivers=sorted({site['river'] for site in sites.values() if site['river']}),
                sources=sorted({source for refs in provenance.values() for source in refs}),
                excluded_archives={
                    'Ganga': 'Parliamentary archive contains period summaries of DO and BOD.',
                    'Mahanadi': '2014 CPCB archive contains annual summaries, not individual sampling events.',
                    'Narmada': 'Narmatha archive lacks documented measurement units and official provenance.',
                },
                version=VERSION, criteria=CRITERIA, method=METHOD, water_use='CPCB Class B · organised outdoor bathing',
                score=overall, partial_version=PARTIAL_VERSION,
                partial_coverage=dict(included=['pH', 'DO'], excluded=['BOD', 'Total coliform'],
                                      objectives_used=2, objectives_total=len(OBJECTIVES)),
                partial_score=aggregate(partial) if river or station else None,
                partial_scored_stations=len(partial),
                partial_earliest=min((item['first'] for item in partial), default=None),
                partial_latest=max((item['last'] for item in partial), default=None),
                partial_sources=sorted({source for item in partial for source in item['sources']}),
                partial_trend=[dict(year=year, score=aggregate(values), scored_stations=sum(value is not None for value in values))
                               for year, values in sorted(partial_yearly.items()) if river or station],
                stations=result, scored_stations=len(scored), total_stations=len(result),
                trend=[dict(year=year, score=aggregate(values), scored_stations=sum(value is not None for value in values),
                            observed_stations=len(values)) for year, values in sorted(yearly.items()) if river or station],
                score_sources=sorted({source for item in scored for source in item['sources']}),
                earliest=min((item['first'] for item in scored), default=None),
                latest=max((item['last'] for item in scored), default=None))


def persist_assessment(db, result, **filters):
    from sqlalchemy.exc import IntegrityError
    from .india_models import IndiaLaboratoryAssessment

    payload = json.dumps({'filters': filters, 'assessment': result}, sort_keys=True, default=str)
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    if db.get(IndiaLaboratoryAssessment, fingerprint) is None:
        db.add(IndiaLaboratoryAssessment(fingerprint=fingerprint, payload=payload))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if db.get(IndiaLaboratoryAssessment, fingerprint) is None:
                raise

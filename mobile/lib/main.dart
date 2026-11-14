import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

typedef Record = Map<String, dynamic>;
const base = String.fromEnvironment(
  'AQUALENS_API_URL',
  defaultValue: 'http://10.0.2.2:8000',
);
const origin = '/india/ground';
const storage = FlutterSecureStorage();

void main() {
  runApp(
    MaterialApp(
      title: 'AquaLens Field',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff1367cb)),
        scaffoldBackgroundColor: const Color(0xfff1f7ff),
      ),
      home: const FieldApp(),
    ),
  );
}

class ApiFailure implements Exception {
  final int status;
  final String message;
  ApiFailure(this.status, this.message);
  @override
  String toString() => message;
}

class FieldApi {
  String token = '';
  Map<String, String> get headers => {'Authorization': 'Bearer $token'};
  Uri uri(String path) => Uri.parse(base + path);
  dynamic parse(http.Response response) {
    final body = jsonDecode(response.body);
    if (response.statusCode >= 400) {
      throw ApiFailure(
        response.statusCode,
        body is Map
            ? (body['detail'] ?? 'Request failed').toString()
            : 'Request failed',
      );
    }
    return body;
  }

  Future<dynamic> get(String path) async => parse(
    await http
        .get(uri(path), headers: headers)
        .timeout(const Duration(seconds: 20)),
  );
  Future<Record> login(String user, String password) async =>
      Map<String, dynamic>.from(
        parse(
          await http
              .post(
                uri('/auth/login'),
                headers: {'Content-Type': 'application/json'},
                body: jsonEncode({'username': user, 'password': password}),
              )
              .timeout(const Duration(seconds: 20)),
        ),
      );
  Future<Record> upload(Record row) async {
    final client = http.Client();
    try {
      final req = http.MultipartRequest(
        'POST',
        uri('$origin/stations/${row['station']}/observations'),
      );
      req.headers.addAll(headers);
      req.fields['metadata'] = row['metadata'] as String;
      req.files.add(
        await http.MultipartFile.fromPath('image', row['file'] as String),
      );
      final response = await client
          .send(req)
          .then(http.Response.fromStream)
          .timeout(const Duration(minutes: 2));
      return Map<String, dynamic>.from(parse(response));
    } finally {
      client.close();
    }
  }
}

class FieldApp extends StatefulWidget {
  const FieldApp({super.key});
  @override
  State<FieldApp> createState() => _FieldAppState();
}

class _FieldAppState extends State<FieldApp> {
  final api = FieldApi();
  final username = TextEditingController(),
      password = TextEditingController(),
      search = TextEditingController();
  late Database db;
  Timer? timer;
  String owner = '', message = '', statusFilter = '';
  int page = 0;
  bool ready = false,
      signingIn = false,
      syncing = false,
      capturing = false,
      online = false;
  List<Record> stations = [], history = [], queue = [];
  int? stationFilter;
  DateTimeRange? period;

  @override
  void initState() {
    super.initState();
    unawaited(initialize());
  }

  @override
  void dispose() {
    timer?.cancel();
    username.dispose();
    password.dispose();
    search.dispose();
    super.dispose();
  }

  Future<void> initialize() async {
    try {
      db = await openDatabase(
        '${await getDatabasesPath()}/aqualens-field.db',
        version: 1,
        onCreate: (db, _) async {
          await db.execute(
            'CREATE TABLE uploads(id TEXT PRIMARY KEY, owner TEXT NOT NULL, station INTEGER NOT NULL, file TEXT NOT NULL, metadata TEXT NOT NULL, state TEXT NOT NULL, error TEXT)',
          );
          await db.execute(
            'CREATE TABLE cache(owner TEXT PRIMARY KEY, stations TEXT NOT NULL, history TEXT NOT NULL)',
          );
        },
      );
      api.token = await storage.read(key: 'token') ?? '';
      if (api.token.isNotEmpty) {
        owner = await storage.read(key: 'officer') ?? '';
        await loadLocal();
      }
      timer = Timer.periodic(
        const Duration(seconds: 15),
        (_) => unawaited(sync()),
      );
      if (mounted) setState(() => ready = true);
      unawaited(sync());
    } catch (e) {
      if (mounted) setState(() => message = 'Local storage unavailable: $e');
    }
  }

  List<Record> records(dynamic data) =>
      (data as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
  Future<void> loadLocal() async {
    final cached = await db.query(
      'cache',
      where: 'owner=?',
      whereArgs: [owner],
    );
    if (cached.isNotEmpty) {
      stations = records(jsonDecode(cached.first['stations'] as String));
      history = records(jsonDecode(cached.first['history'] as String));
    }
    await loadQueue();
  }

  Future<void> loadQueue() async {
    queue = (await db.query(
      'uploads',
      where: 'owner=?',
      whereArgs: [owner],
      orderBy: 'rowid DESC',
    )).map(Map<String, dynamic>.from).toList();
    if (mounted) setState(() {});
  }

  Future<void> login() async {
    setState(() {
      signingIn = true;
      message = '';
    });
    try {
      final session = await api.login(username.text.trim(), password.text);
      if (session['role'] != 'officer')
        throw ApiFailure(403, 'Sign in with a field officer account.');
      api.token = session['access_token'] as String;
      owner = session['username'] as String;
      await storage.write(key: 'officer', value: owner);
      await storage.write(key: 'token', value: api.token);
      password.clear();
      await loadLocal();
      unawaited(sync());
    } catch (e) {
      message = e.toString();
    } finally {
      if (mounted) setState(() => signingIn = false);
    }
  }

  Future<void> logout() async {
    if (syncing || capturing) return;
    api.token = '';
    await storage.delete(key: 'token');
    await storage.delete(key: 'officer');
    if (mounted)
      setState(() {
        owner = '';
        stations = [];
        history = [];
        queue = [];
        message = '';
        page = 0;
        online = false;
      });
  }

  Future<void> sync() async {
    if (!ready || syncing || owner.isEmpty) return;
    setState(() => syncing = true);
    try {
      stations = records(await api.get('$origin/stations'));
      for (final row
          in queue.where((r) => r['state'] != 'Failed').reversed.toList()) {
        await update(row, 'Uploading');
        try {
          await api.upload(row);
          await db.delete(
            'uploads',
            where: 'id=? AND owner=?',
            whereArgs: [row['id'], owner],
          );
          try {
            await File(row['file'] as String).delete();
          } on FileSystemException {
            /* Already removed. */
          }
        } on ApiFailure catch (e) {
          if (e.status == 401) {
            await update(row, 'Pending');
            rethrow;
          }
          await update(row, e.status >= 500 ? 'Pending' : 'Failed', e.message);
          if (e.status >= 500) rethrow;
        } catch (e) {
          await update(row, 'Pending');
          rethrow;
        }
        await loadQueue();
      }
      history = records(await api.get('$origin/mine'));
      await db.insert('cache', {
        'owner': owner,
        'stations': jsonEncode(stations),
        'history': jsonEncode(history),
      }, conflictAlgorithm: ConflictAlgorithm.replace);
      online = true;
      message = '';
    } catch (e) {
      online = false;
      message = e is ApiFailure
          ? e.message
          : 'Offline or server unreachable. Pending captures are retained.';
      if (e is ApiFailure && e.status == 401) {
        await storage.delete(key: 'token');
        api.token = '';
        owner = '';
        stations = [];
        history = [];
        queue = [];
        page = 0;
      }
    } finally {
      if (mounted) setState(() => syncing = false);
    }
  }

  Future<void> update(Record row, String state, [String? error]) async {
    await db.update(
      'uploads',
      {'state': state, 'error': error},
      where: 'id=? AND owner=?',
      whereArgs: [row['id'], owner],
    );
    await loadQueue();
  }

  Future<void> capture() async {
    if (capturing) return;
    setState(() => capturing = true);
    try {
      if (stations.isEmpty)
        throw StateError(
          'Connect once to load registered monitoring stations.',
        );
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied)
        permission = await Geolocator.requestPermission();
      if (permission != LocationPermission.always &&
          permission != LocationPermission.whileInUse)
        throw StateError(
          'Enable location permission to capture a geotagged sample.',
        );
      final gps = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 20),
        ),
      );
      final shot = await ImagePicker().pickImage(
        source: ImageSource.camera,
        preferredCameraDevice: CameraDevice.rear,
      );
      final captured = DateTime.now().toUtc();
      if (shot == null || !mounted) return;
      if (captured.difference(gps.timestamp.toUtc()).abs() >
              const Duration(minutes: 2) ||
          gps.accuracy <= 0 ||
          gps.accuracy > 1000)
        throw StateError(
          'GPS fix is stale or too imprecise. Retake with a fresh fix.',
        );
      if (gps.latitude < 6 ||
          gps.latitude > 38 ||
          gps.longitude < 68 ||
          gps.longitude > 98)
        throw StateError(
          'Capture coordinates are outside the India workspace bounds.',
        );
      final size = await File(shot.path).length();
      if (size == 0 || size > 12 * 1024 * 1024)
        throw StateError('Capture must be nonempty and at most 12 MB.');
      final nearby = [...stations]
        ..sort((a, b) => distance(gps, a).compareTo(distance(gps, b)));
      if (!mounted) return;
      final details = await Navigator.of(context).push<Record>(
        MaterialPageRoute(
          builder: (_) => CaptureReview(
            image: shot.path,
            gps: gps,
            captured: captured,
            stations: nearby,
          ),
        ),
      );
      if (details == null) return;
      final id = const Uuid().v4();
      final dir = await getApplicationDocumentsDirectory();
      final file = await File(shot.path).copy('${dir.path}/$id.jpg');
      final station = details.remove('station');
      try {
        await db.insert('uploads', {
          'id': id,
          'owner': owner,
          'station': station,
          'file': file.path,
          'state': 'Pending',
          'metadata': jsonEncode({
            ...details,
            'capture_id': id,
            'timestamp': captured.toIso8601String(),
            'latitude': gps.latitude,
            'longitude': gps.longitude,
            'accuracy_m': gps.accuracy,
          }),
        });
      } catch (_) {
        await file.delete();
        rethrow;
      }
      await loadQueue();
      if (mounted) setState(() => page = 2);
      unawaited(sync());
    } catch (e) {
      if (mounted) setState(() => message = e.toString());
    } finally {
      if (mounted) setState(() => capturing = false);
    }
  }

  String stationName(dynamic id) =>
      stations
          .where((s) => s['id'] == id)
          .map((s) => '${s['river']} · ${s['name']}')
          .firstOrNull ??
      'Station #$id';
  String showTime(Object? time) =>
      time?.toString().replaceFirst('T', ' ') ?? 'Unavailable';

  @override
  Widget build(BuildContext context) {
    if (!ready)
      return Scaffold(
        body: Center(
          child: message.isEmpty
              ? const CircularProgressIndicator()
              : Text(message),
        ),
      );
    if (owner.isEmpty)
      return Scaffold(
        body: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(
                      Icons.water_drop_outlined,
                      size: 58,
                      color: Color(0xff1367cb),
                    ),
                    const Text(
                      'AquaLens Field',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const Text(
                      'Field officer sign in',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    TextField(
                      controller: username,
                      decoration: const InputDecoration(
                        labelText: 'Username',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: password,
                      obscureText: true,
                      decoration: const InputDecoration(
                        labelText: 'Password',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 14),
                    FilledButton(
                      onPressed: signingIn ? null : login,
                      child: Text(signingIn ? 'Signing in…' : 'Sign in'),
                    ),
                    if (message.isNotEmpty) Text(message),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
    return Scaffold(
      appBar: AppBar(
        title: const Text('AquaLens Field'),
        actions: [
          IconButton(
            onPressed: syncing ? null : sync,
            icon: const Icon(Icons.sync),
            tooltip: 'Synchronize',
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (message.isNotEmpty)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(message),
              ),
            ),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 200),
            child: KeyedSubtree(
              key: ValueKey(page),
              child: switch (page) {
                0 => home(),
                1 => capturePage(),
                2 => historyPage(),
                _ => profile(),
              },
            ),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: page,
        onDestinationSelected: (i) => setState(() => page = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.camera_alt_outlined),
            label: 'Capture',
          ),
          NavigationDestination(icon: Icon(Icons.history), label: 'History'),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            label: 'Profile',
          ),
        ],
      ),
    );
  }

  Widget home() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Container(
        padding: const EdgeInsets.all(22),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          gradient: const LinearGradient(
            colors: [Color(0xff073777), Color(0xff1679d7)],
          ),
        ),
        child: Text(
          'Welcome, $owner\nField monitoring · India',
          style: const TextStyle(
            color: Colors.white,
            fontSize: 23,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      Wrap(
        children: [
          metric('Observations', history.length),
          metric(
            'Analyzed',
            history.where((r) => r['processing_status'] == 'completed').length,
          ),
          metric('Awaiting sync', queue.length),
        ],
      ),
      FilledButton.icon(
        onPressed: capturing ? null : capture,
        icon: const Icon(Icons.camera_alt_outlined),
        label: const Text('New observation'),
      ),
      OutlinedButton(
        onPressed: () => setState(() => page = 2),
        child: const Text('My observations'),
      ),
      Card(
        child: ExpansionTile(
          title: const Text('Monitoring stations'),
          subtitle: const Text(
            'Registered India stations available to your account',
          ),
          children: stations.isEmpty
              ? [const ListTile(title: Text('No stations available.'))]
              : stations
                    .map(
                      (s) => ListTile(
                        title: Text(stationName(s['id'])),
                        subtitle: Text(
                          '${s['state']} · ${s['latitude']}, ${s['longitude']}',
                        ),
                      ),
                    )
                    .toList(),
        ),
      ),
      const Card(
        child: ExpansionTile(
          title: Text('Capture guidelines'),
          children: [
            ListTile(
              title: Text(
                'Use a consistent sample chamber, camera setup and lighting. Keep the sample in focus and avoid glare. A photograph cannot establish chemical safety.',
              ),
            ),
          ],
        ),
      ),
    ],
  );
  Widget metric(String name, int count) => Card(
    child: Padding(
      padding: const EdgeInsets.all(13),
      child: Text('$count\n$name'),
    ),
  );
  Widget capturePage() => Card(
    child: ListTile(
      leading: const Icon(Icons.camera_alt_outlined),
      title: const Text('Capture water sample'),
      subtitle: const Text(
        'Camera and GPS are required. Captures can be queued offline.',
      ),
      trailing: FilledButton(
        onPressed: capturing ? null : capture,
        child: Text(capturing ? 'Opening…' : 'Capture'),
      ),
    ),
  );
  Widget profile() => Card(
    child: ListTile(
      title: Text(owner),
      subtitle: Text('Field officer · ${online ? 'Connected' : 'Offline'}'),
      trailing: TextButton(
        onPressed: syncing || capturing ? null : logout,
        child: const Text('Sign out'),
      ),
    ),
  );
  Widget historyPage() {
    final filtered = history.where((row) {
      final time = DateTime.tryParse(row['timestamp'].toString())?.toLocal();
      return stationName(row['station_id'])
              .toLowerCase()
              .contains(search.text.toLowerCase()) &&
          (stationFilter == null || row['station_id'] == stationFilter) &&
          (statusFilter.isEmpty || row['processing_status'] == statusFilter) &&
          (period == null ||
              (time != null &&
                  !time.isBefore(period!.start) &&
                  time.isBefore(period!.end.add(const Duration(days: 1)))));
    });
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final row in queue)
          Card(
            child: ListTile(
              leading: Image.file(
                File(row['file'] as String),
                width: 50,
                height: 50,
                fit: BoxFit.cover,
              ),
              title: Text(stationName(row['station'])),
              subtitle: Text(
                '${row['state']}${row['error'] == null ? '' : ' · ${row['error']}'}',
              ),
              trailing: row['state'] == 'Failed'
                  ? TextButton(
                      onPressed: syncing
                          ? null
                          : () async {
                              await update(row, 'Pending');
                              await sync();
                            },
                      child: const Text('Retry'),
                    )
                  : null,
            ),
          ),
        TextField(
          controller: search,
          onChanged: (_) => setState(() {}),
          decoration: const InputDecoration(
            labelText: 'Search river or station',
            prefixIcon: Icon(Icons.search),
          ),
        ),
        DropdownButton<int>(
          value: stations.any((s) => s['id'] == stationFilter)
              ? stationFilter
              : null,
          hint: const Text('All locations'),
          isExpanded: true,
          onChanged: (v) => setState(() => stationFilter = v),
          items: [
            const DropdownMenuItem<int>(child: Text('All locations')),
            for (final s in stations)
              DropdownMenuItem(
                value: s['id'] as int,
                child: Text(stationName(s['id'])),
              ),
          ],
        ),
        DropdownButton<String>(
          value: statusFilter,
          onChanged: (v) => setState(() => statusFilter = v ?? ''),
          items: const [
            DropdownMenuItem(value: '', child: Text('All analysis states')),
            DropdownMenuItem(value: 'completed', child: Text('Completed')),
            DropdownMenuItem(
              value: 'features_extracted',
              child: Text('Features extracted only'),
            ),
          ],
        ),
        Wrap(
          children: [
            TextButton(
              onPressed: () async {
                final now = DateTime.now();
                final picked = await showDateRangePicker(
                  context: context,
                  firstDate: DateTime(1900),
                  lastDate: now,
                );
                if (picked != null && mounted) setState(() => period = picked);
              },
              child: Text(
                period == null
                    ? 'Filter dates'
                    : '${period!.start.toString().split(" ").first} – ${period!.end.toString().split(" ").first}',
              ),
            ),
            if (period != null)
              TextButton(
                onPressed: () => setState(() => period = null),
                child: const Text('Clear dates'),
              ),
          ],
        ),
        if (filtered.isEmpty)
          const Padding(
            padding: EdgeInsets.all(12),
            child: Text('No uploaded observations match.'),
          ),
        for (final row in filtered)
          Card(
            child: ListTile(
              leading: online
                  ? Image.network(
                      '$base$origin/mine/${row['id']}/image',
                      headers: api.headers,
                      width: 50,
                      height: 50,
                      fit: BoxFit.cover,
                      errorBuilder: (_, e, s) =>
                          const Icon(Icons.image_not_supported_outlined),
                    )
                  : const Icon(Icons.image_outlined),
              title: Text(stationName(row['station_id'])),
              subtitle: Text(
                '${showTime(row['timestamp'])} · ${row['processing_status']}',
              ),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => ObservationDetail(
                    api: api,
                    row: row,
                    station: stationName(row['station_id']),
                    online: online,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

double distance(Position gps, Record station) => Geolocator.distanceBetween(
  gps.latitude,
  gps.longitude,
  (station['latitude'] as num).toDouble(),
  (station['longitude'] as num).toDouble(),
);

class CaptureReview extends StatefulWidget {
  final String image;
  final Position gps;
  final DateTime captured;
  final List<Record> stations;
  const CaptureReview({
    super.key,
    required this.image,
    required this.gps,
    required this.captured,
    required this.stations,
  });
  @override
  State<CaptureReview> createState() => _CaptureReviewState();
}

class _CaptureReviewState extends State<CaptureReview> {
  final form = GlobalKey<FormState>();
  final inputs = {
    for (final k in [
      'camera',
      'camera_settings',
      'illumination',
      'preparation',
      'capture_protocol',
      'notes',
    ])
      k: TextEditingController(),
  };
  late String river;
  late int station;
  String season = 'Unspecified', sampleType = 'Surface water sample';
  @override
  void initState() {
    super.initState();
    river = widget.stations.first['river'] as String;
    station = widget.stations.first['id'] as int;
  }

  @override
  void dispose() {
    for (final c in inputs.values) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('New observation')),
    body: Form(
      key: form,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: Image.file(
              File(widget.image),
              height: 230,
              fit: BoxFit.contain,
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Discard / retake'),
          ),
          Text(
            'Captured (UTC): ${widget.captured.toIso8601String()}\nGPS: ${widget.gps.latitude}, ${widget.gps.longitude} · ±${widget.gps.accuracy.round()} m',
          ),
          const Text(
            'Nearest registered station is suggested. Confirm the actual sampling location.',
          ),
          DropdownButtonFormField<String>(
            value: river,
            decoration: const InputDecoration(labelText: 'River'),
            items: [
              for (final r
                  in widget.stations.map((s) => s['river'] as String).toSet())
                DropdownMenuItem(value: r, child: Text(r)),
            ],
            onChanged: (v) {
              if (v != null)
                setState(() {
                  river = v;
                  station =
                      widget.stations.firstWhere((s) => s['river'] == v)['id']
                          as int;
                });
            },
          ),
          DropdownButton<int>(
            value: station,
            isExpanded: true,
            onChanged: (v) {
              if (v != null) setState(() => station = v);
            },
            items: [
              for (final s in widget.stations.where((s) => s['river'] == river))
                DropdownMenuItem(
                  value: s['id'] as int,
                  child: Text(
                    '${s['name']} · ${distance(widget.gps, s).round()} m',
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
          ),
          DropdownButtonFormField<String>(
            value: sampleType,
            decoration: const InputDecoration(labelText: 'Sample type'),
            items: [
              for (final type in [
                'Surface water sample',
                'Collected chamber sample',
                'Other',
              ])
                DropdownMenuItem(value: type, child: Text(type)),
            ],
            onChanged: (v) => setState(() => sampleType = v!),
          ),
          DropdownButtonFormField<String>(
            value: season,
            decoration: const InputDecoration(labelText: 'Season'),
            items: [
              for (final s in [
                'Unspecified',
                'Pre-monsoon',
                'Monsoon',
                'Post-monsoon',
                'Winter',
              ])
                DropdownMenuItem(value: s, child: Text(s)),
            ],
            onChanged: (v) => setState(() => season = v!),
          ),
          for (final field in inputs.entries)
            TextFormField(
              controller: field.value,
              decoration: InputDecoration(
                labelText: field.key.replaceAll('_', ' '),
              ),
              maxLength: switch (field.key) {
                'camera' => 160,
                'illumination' || 'capture_protocol' => 300,
                'notes' => 2000,
                _ => 500,
              },
              validator: (v) =>
                  field.key != 'notes' && (v?.trim().length ?? 0) < 2
                  ? 'Required for reproducible analysis'
                  : null,
            ),
          FilledButton(
            onPressed: () {
              if (form.currentState!.validate())
                Navigator.pop(context, {
                  for (final e in inputs.entries) e.key: e.value.text.trim(),
                  'station': station,
                  'season': season,
                  'sample_type': sampleType,
                });
            },
            child: const Text('Save to upload queue'),
          ),
        ],
      ),
    ),
  );
}

class ObservationDetail extends StatefulWidget {
  final FieldApi api;
  final Record row;
  final String station;
  final bool online;
  const ObservationDetail({
    super.key,
    required this.api,
    required this.row,
    required this.station,
    required this.online,
  });
  @override
  State<ObservationDetail> createState() => _ObservationDetailState();
}

class _ObservationDetailState extends State<ObservationDetail> {
  late final Future<dynamic> analysis = widget.online
      ? widget.api.get('$origin/mine/${widget.row['id']}/analysis')
      : Future.value(null);
  @override
  Widget build(BuildContext context) {
    final row = widget.row, gps = widget.row['ground'] as Map;
    final classifier = row['classification'] as Map?;
    return Scaffold(
      appBar: AppBar(title: const Text('Observation results')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            widget.station,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          if (widget.online)
            Image.network(
              '$base$origin/mine/${row['id']}/image',
              headers: widget.api.headers,
              height: 240,
              fit: BoxFit.contain,
              errorBuilder: (_, e, s) =>
                  const Text('Original image is unavailable.'),
            ),
          Text(
            'Capture: ${row['timestamp']}\nUploaded: ${gps['uploaded_at']}\nGPS: ${gps['latitude']}, ${gps['longitude']}\nOfficer: ${gps['officer']}\nAnalysis: ${row['processing_status']}',
          ),
          Card(
            child: ListTile(
              title: Text(
                'Visual appearance: ${classifier?['predicted_condition'] ?? 'Unavailable'}',
              ),
              subtitle: Text(
                row['processing_error']?.toString() ??
                    classifier?['probability_note']?.toString() ??
                    'No calibrated confidence is available.',
              ),
            ),
          ),
          const ListTile(
            title: Text('Water Health Score: unavailable'),
            subtitle: Text(
              'Visual appearance does not establish chemical quality or water safety.',
            ),
          ),
          ExpansionTile(
            title: const Text('Detailed analysis'),
            children: [
              Text(
                'Extractor: ${row['feature_extractor_version']} · Model: ${classifier?['model_version'] ?? 'Unavailable'}',
              ),
              FutureBuilder(
                future: analysis,
                builder: (context, snapshot) {
                  final payload = snapshot.data as Map?;
                  final comparison = payload?['comparison'] as Map?;
                  final features = comparison?['features'] as List? ?? [];
                  return Column(
                    children: [
                      Text(
                        snapshot.connectionState == ConnectionState.waiting
                            ? 'Loading reference comparison…'
                            : 'Fingerprint: ${comparison?['status'] ?? 'Unavailable — needs connectivity, verified location and a matching station reference'}',
                      ),
                      for (final entry
                          in (row['features'] as Map? ?? {}).entries)
                        ListTile(
                          title: Text(
                            entry.key.toString().replaceAll('_', ' '),
                          ),
                          trailing: Text(entry.value.toString()),
                          subtitle: Text(
                            features
                                    .where((f) => f['name'] == entry.key)
                                    .map(
                                      (f) =>
                                          'Reference median: ${f['baseline']?['median'] ?? '—'} · Signed IQR deviation: ${f['normalized_deviation'] ?? '—'}',
                                    )
                                    .firstOrNull ??
                                'No comparable reference',
                          ),
                        ),
                      const Text(
                        'Feature measurements describe the image. The classifier does not provide per-image feature attributions.',
                      ),
                    ],
                  );
                },
              ),
            ],
          ),
        ],
      ),
    );
  }
}

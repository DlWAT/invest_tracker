import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

import 'models.dart';

class AppDatabase {
  static Database? _db;
  static Future<Database>? _dbFuture;

  static const String _select = '''
    SELECT l.*,
      CASE WHEN f.source IS NOT NULL THEN 1 ELSE 0 END AS is_favorite,
      (SELECT ph.price_php FROM price_history ph
        WHERE ph.source = l.source AND ph.external_id = l.external_id
        ORDER BY ph.seen_at DESC LIMIT 1 OFFSET 1) AS price_prev
    FROM listings l
    LEFT JOIN favorites f ON f.source = l.source AND f.external_id = l.external_id
  ''';

  static Future<Database> get _instance {
    if (_db != null) return Future.value(_db!);
    if (_dbFuture != null) return _dbFuture!;
    final f = _open();
    _dbFuture = f;
    return f;
  }

  static Future<Database> _open() async {
    final dir = await getApplicationDocumentsDirectory();
    final path = p.join(dir.path, 'listings.db');
    if (!await File(path).exists()) {
      final data = await rootBundle.load('assets/listings.db');
      final bytes =
          data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
      await File(path).writeAsBytes(bytes, flush: true);
    }
    final db = await openDatabase(path);
    _db = db;
    return db;
  }

  static Future<List<Listing>> listings({
    String? search,
    String? type,
    String? zone,
    bool favoritesOnly = false,
    String sort = 'newest',
    int page = 1,
    int perPage = 24,
  }) async {
    final db = await _instance;
    final where = <String>[];
    final args = <Object?>[];
    if (search != null && search.trim().isNotEmpty) {
      where.add(
          '(l.title LIKE ? OR l.location_text LIKE ? OR l.description LIKE ? OR l.agent LIKE ?)');
      final like = '%${search.trim()}%';
      args.addAll([like, like, like, like]);
    }
    if (type != null && type.isNotEmpty) {
      where.add('l.property_type = ?');
      args.add(type);
    }
    if (zone != null && zone.isNotEmpty) {
      where.add('l.zone_id = ?');
      args.add(zone);
    }
    if (favoritesOnly) where.add('f.source IS NOT NULL');
    final whereSql = where.isEmpty ? '' : ' WHERE ${where.join(' AND ')}';
    final rows = await db.rawQuery(
      '$_select$whereSql ORDER BY ${_sortSql(sort)} LIMIT ? OFFSET ?',
      [...args, perPage, (page - 1) * perPage],
    );
    return rows.map(Listing.fromMap).toList();
  }

  static Future<int> count({
    String? search,
    String? type,
    String? zone,
    bool favoritesOnly = false,
  }) async {
    final db = await _instance;
    final where = <String>[];
    final args = <Object?>[];
    if (search != null && search.trim().isNotEmpty) {
      where.add(
          '(l.title LIKE ? OR l.location_text LIKE ? OR l.description LIKE ? OR l.agent LIKE ?)');
      final like = '%${search.trim()}%';
      args.addAll([like, like, like, like]);
    }
    if (type != null && type.isNotEmpty) {
      where.add('l.property_type = ?');
      args.add(type);
    }
    if (zone != null && zone.isNotEmpty) {
      where.add('l.zone_id = ?');
      args.add(zone);
    }
    if (favoritesOnly) where.add('f.source IS NOT NULL');
    final whereSql = where.isEmpty ? '' : ' WHERE ${where.join(' AND ')}';
    final res = await db.rawQuery(
      'SELECT COUNT(*) AS c FROM listings l '
      'LEFT JOIN favorites f ON f.source = l.source AND f.external_id = l.external_id'
      '$whereSql',
      args,
    );
    return Sqflite.firstIntValue(res) ?? 0;
  }

  static Future<Listing?> detail(String source, String externalId) async {
    final db = await _instance;
    final rows = await db.rawQuery(
      '$_select WHERE l.source = ? AND l.external_id = ?',
      [source, externalId],
    );
    return rows.isEmpty ? null : Listing.fromMap(rows.first);
  }

  static Future<List<PricePoint>> priceHistory(
      String source, String externalId) async {
    final db = await _instance;
    final rows = await db.query(
      'price_history',
      where: 'source = ? AND external_id = ?',
      whereArgs: [source, externalId],
      orderBy: 'seen_at ASC',
    );
    return rows
        .map((r) => PricePoint(
            pricePhp: r['price_php'] as int?, seenAt: r['seen_at'] as String?))
        .toList();
  }

  static Future<bool> isFavorite(String source, String externalId) async {
    final db = await _instance;
    final rows = await db.query(
      'favorites',
      where: 'source = ? AND external_id = ?',
      whereArgs: [source, externalId],
      limit: 1,
    );
    return rows.isNotEmpty;
  }

  static Future<void> toggleFavorite(String source, String externalId) async {
    final db = await _instance;
    final existing = await db.query(
      'favorites',
      where: 'source = ? AND external_id = ?',
      whereArgs: [source, externalId],
    );
    if (existing.isEmpty) {
      await db.insert('favorites', {
        'source': source,
        'external_id': externalId,
        'created_at': DateTime.now().toUtc().toIso8601String(),
      });
    } else {
      await db.delete(
        'favorites',
        where: 'source = ? AND external_id = ?',
        whereArgs: [source, externalId],
      );
    }
  }

  static Future<Map<String, int>> stats() async {
    final db = await _instance;
    Future<int> q(String sql) async =>
        Sqflite.firstIntValue(await db.rawQuery(sql)) ?? 0;
    final total = await q('SELECT COUNT(*) FROM listings');
    final favorites = await q('SELECT COUNT(*) FROM favorites');
    final drops = await q('''
      SELECT COUNT(*) FROM listings l WHERE
        (SELECT COUNT(*) FROM price_history ph
          WHERE ph.source = l.source AND ph.external_id = l.external_id) >= 2
        AND (SELECT ph.price_php FROM price_history ph
              WHERE ph.source = l.source AND ph.external_id = l.external_id
              ORDER BY ph.seen_at DESC LIMIT 1)
          < (SELECT ph.price_php FROM price_history ph
              WHERE ph.source = l.source AND ph.external_id = l.external_id
              ORDER BY ph.seen_at DESC LIMIT 1 OFFSET 1)
    ''');
    final zones = await q(
        'SELECT COUNT(DISTINCT zone_id) FROM listings WHERE zone_id IS NOT NULL');
    return {
      'total': total,
      'favorites': favorites,
      'drops': drops,
      'zones': zones,
    };
  }

  static Future<List<String>> distinct(String column, String table) async {
    final db = await _instance;
    final rows = await db.rawQuery(
        'SELECT DISTINCT $column AS v FROM $table WHERE $column IS NOT NULL ORDER BY $column ASC');
    return rows.map((r) => r['v'].toString()).toList();
  }

  static String _sortSql(String sort) {
    switch (sort) {
      case 'price_asc':
        return 'l.price_php ASC';
      case 'price_desc':
        return 'l.price_php DESC';
      case 'psqm_asc':
        return 'l.price_per_sqm IS NULL, l.price_per_sqm ASC';
      case 'psqm_desc':
        return 'l.price_per_sqm IS NULL, l.price_per_sqm DESC';
      case 'area_desc':
        return 'l.area_sqm IS NULL, l.area_sqm DESC';
      case 'beds_desc':
        return 'l.beds IS NULL, l.beds DESC';
      case 'newest':
      default:
        return 'l.first_seen DESC';
    }
  }
}

import 'dart:convert';

class Listing {
  final String source;
  final String externalId;
  final String? url;
  final String? title;
  final int? pricePhp;
  final double? pricePerSqm;
  final int? beds;
  final int? baths;
  final double? areaSqm;
  final String? propertyType;
  final String? locationText;
  final String? province;
  final String? zoneId;
  final List<String> amenities;
  final List<String> images;
  final String? agent;
  final bool isFeatured;
  final bool hasVirtualTour;
  final double? latitude;
  final double? longitude;
  final String? description;
  final String? firstSeen;
  final String? lastSeen;
  final bool isFavorite;
  final int? pricePrev;

  Listing({
    required this.source,
    required this.externalId,
    this.url,
    this.title,
    this.pricePhp,
    this.pricePerSqm,
    this.beds,
    this.baths,
    this.areaSqm,
    this.propertyType,
    this.locationText,
    this.province,
    this.zoneId,
    this.amenities = const [],
    this.images = const [],
    this.agent,
    this.isFeatured = false,
    this.hasVirtualTour = false,
    this.latitude,
    this.longitude,
    this.description,
    this.firstSeen,
    this.lastSeen,
    this.isFavorite = false,
    this.pricePrev,
  });

  bool get hasDrop =>
      pricePrev != null && pricePhp != null && pricePhp! < pricePrev!;

  String get thumb => images.isNotEmpty ? images.first : '';

  factory Listing.fromMap(Map<String, dynamic> m) {
    return Listing(
      source: m['source'] as String,
      externalId: m['external_id'] as String,
      url: m['url'] as String?,
      title: m['title'] as String?,
      pricePhp: m['price_php'] as int?,
      pricePerSqm: (m['price_per_sqm'] as num?)?.toDouble(),
      beds: m['beds'] as int?,
      baths: m['baths'] as int?,
      areaSqm: (m['area_sqm'] as num?)?.toDouble(),
      propertyType: m['property_type'] as String?,
      locationText: m['location_text'] as String?,
      province: m['province'] as String?,
      zoneId: m['zone_id'] as String?,
      amenities: _list(m['amenities']),
      images: _list(m['images']),
      agent: m['agent'] as String?,
      isFeatured: (m['is_featured'] as int? ?? 0) == 1,
      hasVirtualTour: (m['has_virtual_tour'] as int? ?? 0) == 1,
      latitude: (m['latitude'] as num?)?.toDouble(),
      longitude: (m['longitude'] as num?)?.toDouble(),
      description: m['description'] as String?,
      firstSeen: m['first_seen'] as String?,
      lastSeen: m['last_seen'] as String?,
      isFavorite: (m['is_favorite'] as int? ?? 0) == 1,
      pricePrev: m['price_prev'] as int?,
    );
  }

  static List<String> _list(dynamic v) {
    if (v == null) return const [];
    try {
      final decoded = jsonDecode(v as String);
      if (decoded is List) {
        return decoded.map((e) => e.toString()).toList();
      }
    } catch (_) {}
    return const [];
  }
}

class PricePoint {
  final int? pricePhp;
  final String? seenAt;

  PricePoint({this.pricePhp, this.seenAt});
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../db.dart';
import '../format.dart';
import '../i18n.dart';
import '../models.dart';
import '../widgets.dart';

class DetailScreen extends StatefulWidget {
  final Listing listing;

  const DetailScreen({super.key, required this.listing});

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  Listing? _listing;
  List<PricePoint> _history = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final l = await AppDatabase.detail(
        widget.listing.source, widget.listing.externalId);
    final h = await AppDatabase.priceHistory(
        widget.listing.source, widget.listing.externalId);
    if (mounted) {
      setState(() {
        _listing = l ?? widget.listing;
        _history = h;
        _loading = false;
      });
    }
  }

  Future<void> _toggleFav() async {
    final l = _listing!;
    await AppDatabase.toggleFavorite(l.source, l.externalId);
    _load();
  }

  void _copyUrl() {
    final url = _listing?.url ?? '';
    Clipboard.setData(ClipboardData(text: url));
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(I18n.t('copied'))));
  }

  @override
  Widget build(BuildContext context) {
    final l = _listing;
    return Scaffold(
      appBar: AppBar(
        title: Text(l?.title ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
        actions: [
          IconButton(
            icon: Icon(
              l?.isFavorite == true ? Icons.star : Icons.star_border,
              color: l?.isFavorite == true ? const Color(0xFFf5c451) : null,
            ),
            tooltip: l?.isFavorite == true
                ? I18n.t('fav_remove')
                : I18n.t('fav_add'),
            onPressed: l == null ? null : _toggleFav,
          ),
        ],
      ),
      body: _loading || l == null
          ? const Center(child: CircularProgressIndicator())
          : _body(l),
    );
  }

  Widget _body(Listing l) {
    return ListView(
      children: [
        if (l.thumb.isNotEmpty)
          AspectRatio(
            aspectRatio: 16 / 10,
            child: Image.network(
              l.thumb,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => Container(
                color: const Color(0xFF0d1219),
                child: const Icon(Icons.photo, color: Color(0xFF38434f)),
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(fmtPhp(l.pricePhp),
                  style: const TextStyle(
                      fontSize: 24, fontWeight: FontWeight.bold)),
              const SizedBox(height: 2),
              Text(fmtEur(l.pricePhp),
                  style: const TextStyle(color: Colors.grey, fontSize: 13)),
              if (l.hasDrop)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    '${I18n.t('prev_price')} ${fmtPhp(l.pricePrev)}',
                    style: const TextStyle(
                        color: Color(0xFFfca5a5), fontSize: 13),
                  ),
                ),
              const SizedBox(height: 10),
              Text(l.locationText ?? l.province ?? '',
                  style: const TextStyle(color: Colors.grey)),
              const SizedBox(height: 10),
              Wrap(
                spacing: 14,
                runSpacing: 6,
                children: [
                  if (l.beds != null) _spec('${l.beds} ${I18n.t('beds')}'),
                  if (l.baths != null) _spec('${l.baths} ${I18n.t('baths')}'),
                  if (l.areaSqm != null) _spec('${l.areaSqm!.round()} m²'),
                  if (l.pricePerSqm != null)
                    _spec('${l.pricePerSqm!.round()} ₱/m²'),
                  if (l.zoneId != null) _spec(l.zoneId!),
                ],
              ),
              const SizedBox(height: 20),
              Text(I18n.t('detail_price_history'),
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              PriceChart(points: _history),
              const SizedBox(height: 20),
              if (l.agent != null && l.agent!.isNotEmpty) ...[
                Text(I18n.t('detail_agent'),
                    style: const TextStyle(
                        fontSize: 13, color: Colors.grey)),
                Text(l.agent!, style: const TextStyle(fontSize: 14)),
                const SizedBox(height: 12),
              ],
              if (l.description != null && l.description!.isNotEmpty) ...[
                Text(I18n.t('detail_description'),
                    style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w600)),
                const SizedBox(height: 6),
                Text(l.description!, style: const TextStyle(fontSize: 13)),
              ],
              if (l.url != null && l.url!.isNotEmpty) ...[
                const SizedBox(height: 20),
                Row(
                  children: [
                    Expanded(
                      child: Text(l.url!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: Color(0xFF34d399), fontSize: 12)),
                    ),
                    IconButton(
                      icon: const Icon(Icons.copy, size: 18),
                      tooltip: I18n.t('copy'),
                      onPressed: _copyUrl,
                    ),
                  ],
                ),
              ],
              const SizedBox(height: 20),
            ],
          ),
        ),
      ],
    );
  }

  Widget _spec(String text) => Text(
        text,
        style: const TextStyle(
            fontSize: 13, color: Color(0xFFc3cdd7)),
      );
}

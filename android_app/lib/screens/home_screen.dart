import 'package:flutter/material.dart';

import '../db.dart';
import '../i18n.dart';
import '../models.dart';
import '../widgets.dart';
import 'detail_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, int>? _stats;
  List<Listing> _recent = [];
  List<Listing> _drops = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final stats = await AppDatabase.stats();
      final recent = await AppDatabase.listings(sort: 'newest', perPage: 8);
      final sample = await AppDatabase.listings(sort: 'newest', perPage: 200);
      final drops = sample.where((l) => l.hasDrop).take(8).toList();
      if (mounted) {
        setState(() {
          _stats = stats;
          _recent = recent;
          _drops = drops;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open(Listing l) async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => DetailScreen(listing: l)),
    );
    _load();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    final stats = _stats ?? {};
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 8),
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _statCard('${stats['total'] ?? 0}', I18n.t('home_stat_listings')),
              _statCard('${stats['favorites'] ?? 0}', I18n.t('home_stat_favorites')),
              _statCard('${stats['drops'] ?? 0}', I18n.t('home_stat_drops')),
              _statCard('${stats['zones'] ?? 0}', I18n.t('home_stat_zones')),
            ],
          ),
        ),
        _section(I18n.t('home_recent'), _recent, _open),
        _section(I18n.t('home_big_drops'), _drops, _open),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget _statCard(String value, String label) {
    return Container(
      width: 150,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF131a24),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF1b2531)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value,
              style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF34d399))),
          const SizedBox(height: 4),
          Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12)),
        ],
      ),
    );
  }

  Widget _section(String title, List<Listing> items, void Function(Listing) onTap) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 8),
          child: Text(title,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        ),
        if (items.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(I18n.t('no_results'),
                style: const TextStyle(color: Colors.grey)),
          )
        else
          ...items.map((l) => ListingCard(
                listing: l,
                onTap: () => onTap(l),
                onFavorite: () => _toggleFav(l),
              )),
      ],
    );
  }

  Future<void> _toggleFav(Listing l) async {
    await AppDatabase.toggleFavorite(l.source, l.externalId);
    _load();
  }
}

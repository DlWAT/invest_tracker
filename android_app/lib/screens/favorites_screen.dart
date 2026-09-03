import 'package:flutter/material.dart';

import '../db.dart';
import '../i18n.dart';
import '../models.dart';
import '../widgets.dart';
import 'detail_screen.dart';

class FavoritesScreen extends StatefulWidget {
  const FavoritesScreen({super.key});

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  List<Listing> _items = [];
  int _total = 0;
  int _page = 1;
  static const _perPage = 24;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  Future<void> _load({bool reset = false}) async {
    if (reset) setState(() { _page = 1; _loading = true; });
    try {
      final total = await AppDatabase.count(favoritesOnly: true);
      final items = await AppDatabase.listings(
        favoritesOnly: true,
        sort: 'newest',
        page: _page,
        perPage: _perPage,
      );
      if (mounted) {
        setState(() {
          _total = total;
          _items = reset ? items : [..._items, ...items];
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
    _load(reset: true);
  }

  Future<void> _toggleFav(Listing l) async {
    await AppDatabase.toggleFavorite(l.source, l.externalId);
    _load(reset: true);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_items.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(I18n.t('fav_empty'),
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.grey)),
        ),
      );
    }
    return ListView.builder(
      itemCount: _items.length + (_items.length < _total ? 1 : 0),
      itemBuilder: (context, i) {
        if (i >= _items.length) {
          return Center(
            child: TextButton(
              onPressed: () { _page++; _load(); },
              child: Text(I18n.t('load_more')),
            ),
          );
        }
        final l = _items[i];
        return ListingCard(
          listing: l,
          onTap: () => _open(l),
          onFavorite: () => _toggleFav(l),
        );
      },
    );
  }
}

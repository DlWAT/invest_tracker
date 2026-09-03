import 'dart:async';

import 'package:flutter/material.dart';

import '../db.dart';
import '../i18n.dart';
import '../models.dart';
import '../widgets.dart';
import 'detail_screen.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _searchCtrl = TextEditingController();
  Timer? _debounce;
  String _sort = 'newest';
  String? _type;
  String? _zone;
  List<String> _types = [];
  List<String> _zones = [];
  List<Listing> _items = [];
  int _total = 0;
  int _page = 1;
  static const _perPage = 24;
  bool _loading = true;

  final _sorts = <String, String>{
    'newest': 'sort_newest',
    'price_asc': 'sort_price_asc',
    'price_desc': 'sort_price_desc',
    'psqm_asc': 'sort_psqm_asc',
    'psqm_desc': 'sort_psqm_desc',
    'area_desc': 'sort_area_desc',
    'beds_desc': 'sort_beds_desc',
  };

  @override
  void initState() {
    super.initState();
    _loadFacets();
    _load(reset: true);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadFacets() async {
    final types = await AppDatabase.distinct('property_type', 'listings');
    final zones = await AppDatabase.distinct('zone_id', 'listings');
    if (mounted) setState(() { _types = types; _zones = zones; });
  }

  Future<void> _load({bool reset = false}) async {
    if (reset) setState(() { _page = 1; _loading = true; });
    try {
      final total = await AppDatabase.count(
        search: _searchCtrl.text,
        type: _type,
        zone: _zone,
      );
      final items = await AppDatabase.listings(
        search: _searchCtrl.text,
        type: _type,
        zone: _zone,
        sort: _sort,
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

  void _onSearchChanged() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () => _load(reset: true));
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
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _searchCtrl,
                  onChanged: (_) => _onSearchChanged(),
                  decoration: InputDecoration(
                    hintText: I18n.t('search_hint'),
                    prefixIcon: const Icon(Icons.search),
                    isDense: true,
                    filled: true,
                    fillColor: const Color(0xFF0f141c),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: const BorderSide(color: Color(0xFF232e3c)),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Row(
            children: [
              Expanded(child: _sortDropdown()),
              const SizedBox(width: 8),
              Expanded(child: _typeDropdown()),
              const SizedBox(width: 8),
              Expanded(child: _zoneDropdown()),
            ],
          ),
        ),
        Expanded(child: _buildList()),
      ],
    );
  }

  Widget _sortDropdown() => DropdownButtonFormField<String>(
        value: _sort,
        decoration: InputDecoration(
          labelText: I18n.t('sort'),
          isDense: true,
          filled: true,
          fillColor: const Color(0xFF0f141c),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
        ),
        items: _sorts.entries
            .map((e) => DropdownMenuItem(value: e.key, child: Text(I18n.t(e.value))))
            .toList(),
        onChanged: (v) { setState(() => _sort = v ?? 'newest'); _load(reset: true); },
      );

  Widget _typeDropdown() => DropdownButtonFormField<String?>(
        value: _type,
        decoration: InputDecoration(
          labelText: I18n.t('filter_type'),
          isDense: true,
          filled: true,
          fillColor: const Color(0xFF0f141c),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
        ),
        items: [
          DropdownMenuItem<String?>(value: null, child: Text(I18n.t('filter_all'))),
          ..._types.map((t) => DropdownMenuItem<String?>(value: t, child: Text(t))),
        ],
        onChanged: (v) { setState(() => _type = v); _load(reset: true); },
      );

  Widget _zoneDropdown() => DropdownButtonFormField<String?>(
        value: _zone,
        decoration: InputDecoration(
          labelText: I18n.t('filter_zone'),
          isDense: true,
          filled: true,
          fillColor: const Color(0xFF0f141c),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
        ),
        items: [
          DropdownMenuItem<String?>(value: null, child: Text(I18n.t('filter_all'))),
          ..._zones.map((z) => DropdownMenuItem<String?>(value: z, child: Text(z))),
        ],
        onChanged: (v) { setState(() => _zone = v); _load(reset: true); },
      );

  Widget _buildList() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_items.isEmpty) {
      return Center(
        child: Text(I18n.t('no_results'), style: const TextStyle(color: Colors.grey)),
      );
    }
    return ListView.builder(
      itemCount: _items.length + (_items.length < _total ? 1 : 0),
      itemBuilder: (context, i) {
        if (i >= _items.length) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Center(
              child: TextButton(
                onPressed: () { _page++; _load(); },
                child: Text(I18n.t('load_more')),
              ),
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

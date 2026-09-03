import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'i18n.dart';
import 'screens/favorites_screen.dart';
import 'screens/home_screen.dart';
import 'screens/search_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  I18n.lang = prefs.getString('lang') ?? 'fr';
  runApp(const InvestTrackerApp());
}

class InvestTrackerApp extends StatefulWidget {
  const InvestTrackerApp({super.key});

  @override
  State<InvestTrackerApp> createState() => _InvestTrackerAppState();
}

class _InvestTrackerAppState extends State<InvestTrackerApp> {
  int _tab = 0;

  void _toggleLang() {
    setState(() => I18n.toggle());
    SharedPreferences.getInstance()
        .then((p) => p.setString('lang', I18n.lang));
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: I18n.t('app_title'),
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0a0e14),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF10b981),
          secondary: Color(0xFF8b5cf6),
          surface: Color(0xFF131a24),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0a0e14),
          elevation: 0,
        ),
        navigationBarTheme: NavigationBarThemeData(
          backgroundColor: const Color(0xFF0f141c),
          indicatorColor: const Color(0xFF10b981).withOpacity(0.2),
        ),
      ),
      home: Scaffold(
        appBar: AppBar(
          title: Text(I18n.t('app_title')),
          actions: [
            TextButton(
              onPressed: _toggleLang,
              child: Text(
                I18n.lang.toUpperCase(),
                style: const TextStyle(
                  color: Color(0xFF34d399),
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
        body: IndexedStack(
          index: _tab,
          children: [
            HomeScreen(),
            SearchScreen(),
            FavoritesScreen(),
          ],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (i) => setState(() => _tab = i),
          destinations: [
            NavigationDestination(
              icon: const Icon(Icons.home_outlined),
              selectedIcon: const Icon(Icons.home),
              label: I18n.t('tab_home'),
            ),
            NavigationDestination(
              icon: const Icon(Icons.search),
              label: I18n.t('tab_search'),
            ),
            NavigationDestination(
              icon: const Icon(Icons.star_outline),
              selectedIcon: const Icon(Icons.star),
              label: I18n.t('tab_favorites'),
            ),
          ],
        ),
      ),
    );
  }
}

/// ShelfFinder for Android: find where a product goes, on the shop floor.
library;

import 'package:flutter/material.dart';

import 'app_state.dart';
import 'screens/import_sheet.dart';
import 'screens/layouts_screen.dart';
import 'screens/search_screen.dart';
import 'screens/settings_screen.dart';
import 'theme.dart' as palette;

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ShelfFinderApp());
}

class ShelfFinderApp extends StatefulWidget {
  const ShelfFinderApp({super.key, this.state});

  /// Injected by tests; the app builds its own otherwise.
  final AppState? state;

  @override
  State<ShelfFinderApp> createState() => _ShelfFinderAppState();
}

class _ShelfFinderAppState extends State<ShelfFinderApp> {
  late final AppState _state = widget.state ?? AppState();
  late final Future<void> _started = _state.start();

  @override
  Widget build(BuildContext context) {
    // The scope sits *above* MaterialApp on purpose: a pushed route is built
    // under the app's Navigator, so a scope inside `home` would not be visible
    // to it and every screen opened from a result would fail to build.
    return AppScope(
      state: _state,
      child: MaterialApp(
        title: 'ShelfFinder',
        debugShowCheckedModeBanner: false,
        theme: palette.buildTheme(),
        home: FutureBuilder<void>(
          future: _started,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Scaffold(
                body: Center(child: CircularProgressIndicator()),
              );
            }
            return const HomeShell();
          },
        ),
      ),
    );
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _tab = 0;
  bool _importing = false;

  Future<void> _import() async {
    if (_importing) return;
    final state = AppScope.of(context);
    final choice = await askHowToImport(context);
    if (choice == null || !mounted) return;

    setState(() => _importing = true);
    try {
      await ImportRunner(context, state).run(choice);
      if (mounted && state.layouts.isNotEmpty) setState(() => _tab = 0);
    } finally {
      if (mounted) setState(() => _importing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      SearchScreen(onImportRequested: _import),
      LayoutsScreen(onImportRequested: _import),
      const SettingsScreen(),
    ];

    return Scaffold(
      body: IndexedStack(index: _tab, children: screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (index) => setState(() => _tab = index),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.search_outlined),
            selectedIcon: Icon(Icons.search),
            label: 'Search',
          ),
          NavigationDestination(
            icon: Icon(Icons.layers_outlined),
            selectedIcon: Icon(Icons.layers),
            label: 'Layouts',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Settings',
          ),
        ],
      ),
    );
  }
}

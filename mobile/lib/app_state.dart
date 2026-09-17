/// App-wide state: the library on the device, and the few settings there are.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data/library_store.dart';
import 'data/models.dart';
import 'data/search.dart';
import 'theme.dart' as palette;

class AppState extends ChangeNotifier {
  AppState({LibraryStore? store}) : _store = store;

  LibraryStore? _store;
  bool ready = false;
  int highlightColour = palette.argbOf(palette.highlight);
  int dimLevel = 55;
  String? defaultLayoutId;

  LibraryStore get store => _store!;
  List<Layout> get layouts => _store?.layouts ?? const [];
  ProductIndex get index => store.index;
  Color get highlight => palette.colourFromArgb(highlightColour);

  Future<void> start() async {
    if (ready) return;
    if (_store == null) {
      final documents = await getApplicationDocumentsDirectory();
      _store = LibraryStore(Directory(p.join(documents.path, 'shelffinder')));
    }
    await _store!.load();
    final preferences = await SharedPreferences.getInstance();
    highlightColour =
        preferences.getInt('highlight_colour') ??
            palette.argbOf(palette.highlight);
    dimLevel = preferences.getInt('dim_level') ?? 55;
    defaultLayoutId = preferences.getString('default_layout');
    ready = true;
    notifyListeners();
  }

  Future<void> setHighlightColour(Color colour) async {
    highlightColour = palette.argbOf(colour);
    final preferences = await SharedPreferences.getInstance();
    await preferences.setInt('highlight_colour', highlightColour);
    notifyListeners();
  }

  Future<void> setDimLevel(int value) async {
    dimLevel = value;
    final preferences = await SharedPreferences.getInstance();
    await preferences.setInt('dim_level', value);
    notifyListeners();
  }

  Future<void> setDefaultLayout(String? layoutId) async {
    defaultLayoutId = layoutId;
    final preferences = await SharedPreferences.getInstance();
    if (layoutId == null) {
      await preferences.remove('default_layout');
    } else {
      await preferences.setString('default_layout', layoutId);
    }
    notifyListeners();
  }

  Future<PackImportResult> importPack(File file) async {
    final result = await store.importPack(file);
    notifyListeners();
    return result;
  }

  Future<void> deleteLayout(String layoutId) async {
    await store.deleteLayout(layoutId);
    if (defaultLayoutId == layoutId) await setDefaultLayout(null);
    notifyListeners();
  }
}

class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child})
      : super(notifier: state);

  static AppState of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'No AppScope above this widget');
    return scope!.notifier!;
  }
}

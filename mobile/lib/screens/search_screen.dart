/// The screen a worker lives on: type a code, get a place to walk to.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_state.dart';
import '../data/search.dart';
import '../theme.dart' as palette;
import '../widgets/result_tile.dart';
import 'viewer_screen.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.onImportRequested});

  final VoidCallback onImportRequested;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final TextEditingController _field = TextEditingController();
  final FocusNode _focus = FocusNode();
  Timer? _debounce;
  SearchResult? _result;
  String? _scopeLayoutId;
  bool _scopeChosen = false;

  @override
  void dispose() {
    _debounce?.cancel();
    _field.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _onChanged(String text) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 150), () => _run(text));
  }

  void _run(String text) {
    final state = AppScope.of(context);
    setState(() {
      _result = state.index.search(text, layoutId: _scopeLayoutId);
    });
  }

  void _open(SearchHit hit) {
    _focus.unfocus();
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ViewerScreen(
        page: hit.page,
        layout: hit.layout,
        product: hit.product,
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    if (!_scopeChosen && state.defaultLayoutId != null) {
      _scopeLayoutId = state.defaultLayoutId;
      _scopeChosen = true;
    }
    final result = _result;

    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _field,
                  focusNode: _focus,
                  autofocus: state.layouts.isNotEmpty,
                  keyboardType: const TextInputType.numberWithOptions(
                      signed: false, decimal: false),
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  textInputAction: TextInputAction.search,
                  style: const TextStyle(
                    fontSize: 30,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 4,
                  ),
                  decoration: InputDecoration(
                    hintText: 'Product code',
                    prefixIcon: const Icon(Icons.search, color: palette.textDim),
                    suffixIcon: _field.text.isEmpty
                        ? null
                        : IconButton(
                            icon: const Icon(Icons.close),
                            color: palette.textDim,
                            onPressed: () {
                              _field.clear();
                              setState(() => _result = null);
                            },
                          ),
                  ),
                  onChanged: (text) {
                    setState(() {});
                    _onChanged(text);
                  },
                  onSubmitted: (_) {
                    final hits = _result?.hits ?? const [];
                    if (hits.isNotEmpty) _open(hits.first);
                  },
                ),
                if (state.layouts.length > 1) ...[
                  const SizedBox(height: 10),
                  _ScopeChips(
                    selected: _scopeLayoutId,
                    onChanged: (layoutId) {
                      setState(() {
                        _scopeLayoutId = layoutId;
                        _scopeChosen = true;
                      });
                      _run(_field.text);
                    },
                  ),
                ],
              ],
            ),
          ),
          if (result != null && !result.tooShort)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 4),
              child: Text(
                result.message,
                style: const TextStyle(fontSize: 13, color: palette.textDim),
              ),
            ),
          Expanded(child: _body(state, result)),
        ],
      ),
    );
  }

  Widget _body(AppState state, SearchResult? result) {
    if (state.layouts.isEmpty) {
      return _Empty(
        icon: Icons.inbox_outlined,
        title: 'No layouts yet',
        message: 'Photograph a sheet, or import a pack from the desktop app, '
            'then search any product code.',
        action: FilledButton.icon(
          onPressed: widget.onImportRequested,
          icon: const Icon(Icons.add),
          label: const Text('Add layout sheets'),
        ),
      );
    }
    if (result == null || result.tooShort) {
      return const _Empty(
        icon: Icons.keyboard_outlined,
        title: 'Type three digits or more',
        message: 'The last digits of the code are usually enough - '
            'ShelfFinder matches the end of the code first.',
      );
    }
    if (result.hits.isEmpty && result.suggestions.isEmpty) {
      return _Empty(
        icon: Icons.search_off_outlined,
        title: 'No product ending in ${result.digits}',
        message: 'Check the digits, or search a shorter part of the code.',
      );
    }

    final showing = result.hits.isNotEmpty ? result.hits : result.suggestions;
    final suggesting = result.hits.isEmpty;
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      itemCount: showing.length + (suggesting ? 1 : 0),
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        if (suggesting && index == 0) {
          return const Padding(
            padding: EdgeInsets.only(bottom: 4),
            child: Text(
              'Nothing matched exactly. These are one slip away:',
              style: TextStyle(color: palette.textDim, fontSize: 13),
            ),
          );
        }
        final hit = showing[index - (suggesting ? 1 : 0)];
        return ResultTile(
          hit: hit,
          showReason: suggesting,
          onTap: () => _open(hit),
        );
      },
    );
  }
}

class _ScopeChips extends StatelessWidget {
  const _ScopeChips({required this.selected, required this.onChanged});

  final String? selected;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return SizedBox(
      height: 38,
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: [
          _chip(context, 'All layouts', null),
          for (final layout in state.layouts)
            _chip(context, layout.title, layout.id),
        ],
      ),
    );
  }

  Widget _chip(BuildContext context, String label, String? layoutId) {
    final isSelected = selected == layoutId;
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: ChoiceChip(
        label: Text(label),
        selected: isSelected,
        onSelected: (_) => onChanged(layoutId),
        showCheckmark: false,
        backgroundColor: palette.panel,
        selectedColor: palette.accent.withValues(alpha: 0.2),
        side: BorderSide(
            color: isSelected ? palette.accent : palette.border),
        labelStyle: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: isSelected ? palette.accent : palette.textDim,
        ),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty({
    required this.icon,
    required this.title,
    required this.message,
    this.action,
  });

  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 36),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 46, color: palette.textFaint),
              const SizedBox(height: 16),
              Text(title,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      fontSize: 19, fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Text(message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      color: palette.textDim, fontSize: 14, height: 1.45)),
              if (action != null) ...[
                const SizedBox(height: 22),
                action!,
              ],
            ],
          ),
        ),
      );
}

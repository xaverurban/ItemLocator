/// A short settings screen: how the highlight looks, and what to search first.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../theme.dart' as palette;

const List<(String, Color)> highlightChoices = [
  ('Yellow', Color(0xFFFFD400)),
  ('Cyan', Color(0xFF29E0E3)),
  ('Lime', Color(0xFF9CFF3D)),
  ('Orange', Color(0xFFFF8A2B)),
  ('Pink', Color(0xFFFF4FA3)),
];

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);

    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
        children: [
          const Text('Settings',
              style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800)),
          const SizedBox(height: 20),
          const _SectionTitle('Highlight colour'),
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              for (final (label, colour) in highlightChoices)
                _ColourChoice(
                  label: label,
                  colour: colour,
                  selected: palette.argbOf(colour) == state.highlightColour,
                  onTap: () => state.setHighlightColour(colour),
                ),
            ],
          ),
          const SizedBox(height: 24),
          const _SectionTitle('Dim the rest of the page'),
          Row(
            children: [
              Expanded(
                child: Slider(
                  value: state.dimLevel.toDouble(),
                  max: 90,
                  divisions: 18,
                  activeColor: palette.accent,
                  onChanged: (value) => state.setDimLevel(value.round()),
                ),
              ),
              SizedBox(
                width: 48,
                child: Text('${state.dimLevel}%',
                    textAlign: TextAlign.end,
                    style: const TextStyle(color: palette.textDim)),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const _SectionTitle('Search by default in'),
          const SizedBox(height: 8),
          _LayoutChoice(
            label: 'All layouts',
            selected: state.defaultLayoutId == null,
            onTap: () => state.setDefaultLayout(null),
          ),
          for (final layout in state.layouts)
            _LayoutChoice(
              label: layout.title,
              selected: state.defaultLayoutId == layout.id,
              onTap: () => state.setDefaultLayout(layout.id),
            ),
          const SizedBox(height: 28),
          const Divider(),
          const SizedBox(height: 16),
          const Text(
            'ShelfFinder reads layout packs exported by the desktop app. '
            'Everything stays on this phone - nothing is uploaded, and it works '
            'with no signal at all.',
            style: TextStyle(color: palette.textDim, fontSize: 13, height: 1.5),
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
        text.toUpperCase(),
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.9,
          color: palette.textDim,
        ),
      );
}

class _ColourChoice extends StatelessWidget {
  const _ColourChoice({
    required this.label,
    required this.colour,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final Color colour;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(palette.radius),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: palette.panel,
            borderRadius: BorderRadius.circular(palette.radius),
            border: Border.all(
                color: selected ? colour : palette.border,
                width: selected ? 2 : 1),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 18,
                height: 18,
                decoration: BoxDecoration(color: colour, shape: BoxShape.circle),
              ),
              const SizedBox(width: 10),
              Text(label,
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight: selected ? FontWeight.w700 : FontWeight.w500)),
            ],
          ),
        ),
      );
}

class _LayoutChoice extends StatelessWidget {
  const _LayoutChoice({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(palette.radius),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            decoration: BoxDecoration(
              color: palette.panel,
              borderRadius: BorderRadius.circular(palette.radius),
              border: Border.all(
                  color: selected ? palette.accent : palette.border),
            ),
            child: Row(
              children: [
                Icon(
                  selected
                      ? Icons.radio_button_checked
                      : Icons.radio_button_unchecked,
                  size: 20,
                  color: selected ? palette.accent : palette.textFaint,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(label.isEmpty ? 'Untitled layout' : label,
                      style: const TextStyle(fontSize: 15)),
                ),
              ],
            ),
          ),
        ),
      );
}

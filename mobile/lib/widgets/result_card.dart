/// The result card: big numbers, readable at arm's length on the shop floor.
library;

import 'package:flutter/material.dart';

import '../data/locate.dart';
import '../theme.dart' as palette;

class ResultCard extends StatelessWidget {
  const ResultCard({super.key, required this.location, this.compact = false});

  final Location location;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        _Header(location: location),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _Stat(
                value: '${location.bayIndex}',
                caption: 'BAY',
                detail: 'of ${location.bayCount} in customer-flow order',
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _Stat(
                value: '${location.shelfFromTop}',
                caption: 'SHELF FROM TOP',
                detail: location.shelfFromBottom > 0
                    ? '${location.shelfFromBottom} from bottom'
                    : null,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _Stat(
                value: '${location.positionLeft}',
                caption: 'POSITION FROM LEFT',
                detail: location.positionCount > 0
                    ? '${location.positionRight} from right of '
                        '${location.positionCount}'
                    : null,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _Stat(
                value: location.cases?.toString() ?? '-',
                caption: 'CASES',
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _Caption('SHELF'),
              const SizedBox(height: 6),
              Text(location.notchLabel,
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w600)),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _Caption('NEIGHBOURS'),
              const SizedBox(height: 8),
              _NeighbourLine(
                arrow: '←',
                text: location.neighbourLeft?.describe() ??
                    'nothing to the left',
                known: location.neighbourLeft != null,
              ),
              const SizedBox(height: 6),
              _NeighbourLine(
                arrow: '→',
                text: location.neighbourRight?.describe() ??
                    'nothing to the right',
                known: location.neighbourRight != null,
              ),
            ],
          ),
        ),
        if (location.needsChecking) ...[
          const SizedBox(height: 12),
          _Warning(location: location),
        ],
        if (!compact) ...[
          const SizedBox(height: 12),
          const Text(
            'Ambient layouts: the first visible notch above the plinth is '
            'notch 4. Chiller layouts: the first visible notch above the base '
            'is notch 1.',
            style: TextStyle(fontSize: 12, color: palette.textFaint, height: 1.4),
          ),
        ],
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.location});

  final Location location;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            location.code.isEmpty ? '(no code)' : location.code,
            style: const TextStyle(
              fontSize: 34,
              fontWeight: FontWeight.w800,
              letterSpacing: 1,
              height: 1.1,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            location.name.isEmpty ? '(name not read)' : location.name,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
          ),
          const SizedBox(height: 6),
          Text(location.pageLabel,
              style: const TextStyle(fontSize: 13, color: palette.textDim)),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.value, required this.caption, this.detail});

  final String value;
  final String caption;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value,
              style: const TextStyle(
                  fontSize: 32, fontWeight: FontWeight.w800, height: 1.1)),
          const SizedBox(height: 2),
          _Caption(caption),
          if (detail != null) ...[
            const SizedBox(height: 4),
            Text(detail!,
                style: const TextStyle(fontSize: 12, color: palette.textDim)),
          ],
        ],
      ),
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: palette.panel,
          borderRadius: BorderRadius.circular(palette.radius),
          border: Border.all(color: palette.border),
        ),
        child: child,
      );
}

class _Caption extends StatelessWidget {
  const _Caption(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
        text,
        style: const TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.8,
          color: palette.textDim,
        ),
      );
}

class _NeighbourLine extends StatelessWidget {
  const _NeighbourLine(
      {required this.arrow, required this.text, required this.known});

  final String arrow;
  final String text;
  final bool known;

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(arrow,
              style: const TextStyle(
                  fontSize: 15, fontWeight: FontWeight.w700, color: palette.accent)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                fontSize: 14,
                color: known ? palette.textPrimary : palette.textFaint,
              ),
            ),
          ),
        ],
      );
}

class _Warning extends StatelessWidget {
  const _Warning({required this.location});

  final Location location;

  @override
  Widget build(BuildContext context) {
    final notes = <String>[
      if (location.product.confidence < 0.72) 'read with low confidence',
      if (location.product.tags.contains('unreadable'))
        'the label could not be read',
      if (location.product.name.isEmpty) 'no name was read',
      if (location.bay?.shelvesInherited ?? false)
        'bay ${location.bayIndex} has no notch line of its own, so it uses the '
            'shelves of the bay before it',
    ];
    if (notes.isEmpty) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: palette.amber.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(palette.radius),
        border: Border.all(color: palette.amber.withValues(alpha: 0.45)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.warning_amber_rounded, size: 18, color: palette.amber),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Check this one on the sheet: ${notes.join('; ')}.',
              style: const TextStyle(fontSize: 13, color: palette.amber),
            ),
          ),
        ],
      ),
    );
  }
}

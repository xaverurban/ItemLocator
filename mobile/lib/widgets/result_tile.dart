/// One row in the search results, with the digits you typed picked out.
library;

import 'package:flutter/material.dart';

import '../data/locate.dart';
import '../data/search.dart';
import '../theme.dart' as palette;

class ResultTile extends StatelessWidget {
  const ResultTile({
    super.key,
    required this.hit,
    required this.onTap,
    this.showReason = false,
  });

  final SearchHit hit;
  final VoidCallback onTap;
  final bool showReason;

  @override
  Widget build(BuildContext context) {
    final (before, matched, after) = hit.highlight();
    final card = locate(hit.product, hit.page, hit.layout);

    return Material(
      color: palette.panel,
      borderRadius: BorderRadius.circular(palette.radius),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(palette.radius),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(palette.radius),
            border: Border.all(color: palette.border),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (showReason && hit.reason.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text(
                          hit.reason,
                          style: const TextStyle(
                              fontSize: 11,
                              color: palette.amber,
                              fontWeight: FontWeight.w600),
                        ),
                      ),
                    RichText(
                      text: TextSpan(
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w700,
                          color: palette.textPrimary,
                          letterSpacing: 0.5,
                        ),
                        children: [
                          TextSpan(text: before),
                          TextSpan(
                            text: matched,
                            style: const TextStyle(color: palette.highlight),
                          ),
                          TextSpan(text: after),
                        ],
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      hit.product.name.isEmpty
                          ? '(name not read)'
                          : hit.product.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 14),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${card.pageLabel} · bay ${card.bayIndex} · '
                      'shelf ${card.shelfFromTop} · position ${card.positionLeft}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12, color: palette.textDim),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: palette.textFaint),
            ],
          ),
        ),
      ),
    );
  }
}

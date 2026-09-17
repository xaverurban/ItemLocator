/// The look: the same dark palette as the desktop app, tuned for a phone.
library;

import 'package:flutter/material.dart';

const Color background = Color(0xFF0F1115);
const Color panel = Color(0xFF171A21);
const Color panelRaised = Color(0xFF1E222B);
const Color border = Color(0xFF2A2F3A);
const Color textPrimary = Color(0xFFE6E9EF);
const Color textDim = Color(0xFF8B93A7);
const Color textFaint = Color(0xFF5C6479);
const Color accent = Color(0xFF5B8CFF);
const Color highlight = Color(0xFFFFD400);
const Color amber = Color(0xFFF2B441);

const double radius = 14;

/// Colour packing that does not depend on the deprecated `Color.value`.
int argbOf(Color colour) =>
    ((colour.a * 255).round() << 24) |
    ((colour.r * 255).round() << 16) |
    ((colour.g * 255).round() << 8) |
    (colour.b * 255).round();

Color colourFromArgb(int argb) => Color(argb);

ThemeData buildTheme() {
  final base = ThemeData.dark(useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: background,
    colorScheme: base.colorScheme.copyWith(
      primary: accent,
      secondary: highlight,
      surface: panel,
      surfaceContainerHighest: panelRaised,
      onSurface: textPrimary,
      outline: border,
    ),
    textTheme: base.textTheme.apply(
      bodyColor: textPrimary,
      displayColor: textPrimary,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: background,
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
      elevation: 0,
    ),
    cardTheme: CardTheme(
      color: panel,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(radius),
        side: const BorderSide(color: border),
      ),
      margin: EdgeInsets.zero,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: panelRaised,
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius),
        borderSide: const BorderSide(color: border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius),
        borderSide: const BorderSide(color: border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(radius),
        borderSide: const BorderSide(color: accent, width: 2),
      ),
      hintStyle: const TextStyle(color: textFaint),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: panel,
      surfaceTintColor: Colors.transparent,
      indicatorColor: accent.withValues(alpha: 0.18),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: states.contains(WidgetState.selected) ? accent : textDim,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected) ? accent : textDim,
        ),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: accent,
        foregroundColor: const Color(0xFF0B1020),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radius),
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: textPrimary,
        side: const BorderSide(color: border),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radius),
        ),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: panelRaised,
      contentTextStyle: const TextStyle(color: textPrimary),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
    ),
    dividerTheme: const DividerThemeData(color: border, space: 1, thickness: 1),
  );
}

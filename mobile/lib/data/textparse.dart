/// The text rules, the same ones the desktop uses, ported for on-phone reading.
///
/// Every pattern here has to survive OCR: missing spaces, letters standing in
/// for digits, and the odd misread consonant.
library;

const int minCodeDigits = 4;
const int maxCodeDigits = 9;

const Map<String, String> _digitConfusions = {
  'O': '0', 'o': '0', 'Q': '0', 'D': '0',
  'I': '1', 'l': '1', 'i': '1', '|': '1', '!': '1',
  'Z': '2', 'z': '2', 'A': '4', 'S': '5', 's': '5',
  'G': '6', 'b': '6', 'T': '7', 'B': '8', 'g': '9', 'q': '9',
};

/// Letters that stand in for digits when they touch one, or stand alone.
const Map<String, String> _numericLookalikes = {
  'O': '0', 'o': '0', 'Q': '0', 'l': '1', 'I': '1', '|': '1',
  'S': '5', 's': '5', 'Z': '2',
};

const List<String> _noiseSnippets = [
  'customer flow', 'start of customer', 'contact layoutmanagement',
  'queries/suggestions', 'ambient layouts', 'chiller layouts',
  'first visible notch', 'above the plinth', 'above the base', 'unstoppable',
];

final RegExp _notchPattern = RegExp(
  r'n\s*[o0]\s*[t7]\s*c\s*h[:;.,=\s]*(\d{1,3})'
  r'(?:[:;.,=\s]*d\s*[e3]\s*[pn]\s*[t7]\s*h[:;.,=\s]*(\d{1,3}(?:[.,]\d{1,2})?)\s*c?\s*m?)?'
  r'(?:[:;.,=\s]*s\s*[l1i]\s*[o0]\s*[pn]\s*[e3][:;.,=\s]*(-?\d{1,3}(?:[.,]\d{1,2})?))?',
  caseSensitive: false,
);
final RegExp _casesPattern =
    RegExp(r'c\s*[a4]\s*[s5]\s*[e3]\s*[s5]?[:;.,=\s]*(\d{1,3})', caseSensitive: false);
final RegExp _pagePattern =
    RegExp(r'(\d{1,2})\s*(?:of|/)\s*(\d{1,2})', caseSensitive: false);
final RegExp _sizePattern =
    RegExp(r'(\d{1,2}(?:[.,]\d)?)\s*m\b', caseSensitive: false);
final RegExp _markerPattern = RegExp(r'^[A-Z]{2,5}$');

class NotchInfo {
  const NotchInfo(this.notch, this.depthCm, this.slope, this.raw);

  final int notch;
  final double? depthCm;
  final double? slope;
  final String raw;

  bool get complete => depthCm != null && slope != null;
}

/// Turn letters standing in for digits into digits, leaving words alone.
String foldNumberLetters(String text) {
  final characters = text.split('');
  for (var index = 0; index < characters.length; index++) {
    final replacement = _numericLookalikes[characters[index]];
    if (replacement == null) continue;
    final before = index > 0 ? text[index - 1] : '';
    final after = index + 1 < text.length ? text[index + 1] : '';
    final touchesDigit = _isDigit(before) || _isDigit(after);
    final standsAlone = !_isLetter(before) && !_isLetter(after);
    if (touchesDigit || standsAlone) characters[index] = replacement;
  }
  return characters.join();
}

bool _isDigit(String character) =>
    character.isNotEmpty && RegExp(r'\d').hasMatch(character);
bool _isLetter(String character) =>
    character.isNotEmpty && RegExp(r'[A-Za-z]').hasMatch(character);

bool isNoise(String text) {
  final lowered = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  return _noiseSnippets.any(lowered.contains);
}

bool isMarker(String text) {
  final stripped = text.trim();
  return _markerPattern.hasMatch(stripped) &&
      !const ['OF', 'CM', 'IE'].contains(stripped.toUpperCase());
}

/// The product code, if this line is one - digits only, misreads folded.
String? codeCandidate(String text) {
  final stripped = text.trim().replaceAll(RegExp(r'^[.,:;|\-_ ]+|[.,:;|\-_ ]+$'), '');
  if (stripped.isEmpty || stripped.length > maxCodeDigits + 3) return null;
  if (casesOf(stripped) != null || notchOf(stripped) != null) return null;

  for (final character in stripped.split('')) {
    if (!_isDigit(character) && !_digitConfusions.containsKey(character)) return null;
  }
  final digits = stripped
      .split('')
      .map((character) => _digitConfusions[character] ?? character)
      .where(_isDigit)
      .join();
  if (digits.length < minCodeDigits || digits.length > maxCodeDigits) return null;
  if (digits.length != stripped.length) return null;

  final actualDigits = stripped.split('').where(_isDigit).length;
  if (actualDigits < stripped.length * 0.4) return null;
  return digits;
}

NotchInfo? notchOf(String text) {
  if (isNoise(text)) return null;
  final match = _notchPattern.firstMatch(foldNumberLetters(text));
  if (match == null) return null;

  final depth = match.group(2);
  final slope = match.group(3);
  if (depth == null && slope == null) {
    final compact = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    // "...is notch 4" in the footer note is not a shelf line.
    if (compact.length > 26 || !compact.toLowerCase().startsWith('n')) return null;
  }
  return NotchInfo(
    int.parse(match.group(1)!),
    depth == null ? null : double.parse(depth.replaceAll(',', '.')),
    slope == null ? null : double.parse(slope.replaceAll(',', '.')),
    text.trim(),
  );
}

int? casesOf(String text) {
  final match = _casesPattern.firstMatch(foldNumberLetters(text));
  return match == null ? null : int.parse(match.group(1)!);
}

/// "1 of 2" -> (1, 2)
(int, int)? pageNumberOf(String text) {
  final match = _pagePattern.firstMatch(text);
  if (match == null) return null;
  final page = int.parse(match.group(1)!);
  final total = int.parse(match.group(2)!);
  if (page < 1 || total < 1 || page > total || total > 40) return null;
  return (page, total);
}

/// "IE Household 4.5m" -> ("IE Household", "4.5m")
(String, String) headerOf(String text) {
  final cleaned = text.replaceAll(RegExp(r'\s+'), ' ').trim();
  final match = _sizePattern.firstMatch(cleaned);
  if (match == null) return (cleaned, '');
  final size = '${match.group(1)!.replaceAll(',', '.')}m';
  final name = cleaned.substring(0, match.start).trim().replaceAll(RegExp(r'[-,]+$'), '');
  return (name, size);
}

String cleanName(List<String> parts) {
  final cleaned = parts
      .map((part) => part.replaceAll(RegExp(r'\s+'), ' ').trim())
      .map((part) => part.replaceAll(RegExp(r'^[.,;|]+|[.,;|]+$'), '').trim())
      .where((part) => part.isNotEmpty);
  return cleaned.join(' ').replaceAll(RegExp(r'\s{2,}'), ' ').trim();
}

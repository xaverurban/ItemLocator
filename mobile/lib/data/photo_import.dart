/// Reading a photographed sheet on the phone, with no help from the desktop.
library;

import 'dart:io';

import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';
import 'package:image/image.dart' as img;
import 'package:path/path.dart' as p;

import 'models.dart';
import 'photo_parser.dart';
import 'rules_scan.dart';

/// Progress while a photo is being read, for the bar and the status line.
class PhotoImportProgress {
  const PhotoImportProgress(this.index, this.total, this.stage, [this.name = '']);

  final int index;
  final int total;
  final String stage;
  final String name;

  double get fraction => total <= 0 ? 0 : (index + 0.5) / total;
}

class PhotoImportResult {
  PhotoImportResult(this.layout, this.warnings);

  final Layout layout;
  final List<String> warnings;

  int get productCount => layout.productCount;
}

typedef ProgressCallback = void Function(PhotoImportProgress progress);

/// Reads sheets with on-device OCR. Nothing is uploaded and no signal is needed.
class PhotoImporter {
  PhotoImporter({required this.imagesDirectory, TextRecognizer? recognizer})
      : _recognizer =
            recognizer ?? TextRecognizer(script: TextRecognitionScript.latin);

  final Directory imagesDirectory;
  final TextRecognizer _recognizer;

  Future<void> dispose() => _recognizer.close();

  Future<List<OcrLine>> _read(String path) async {
    final recognised = await _recognizer.processImage(InputImage.fromFilePath(path));
    final lines = <OcrLine>[];
    for (final block in recognised.blocks) {
      for (final line in block.lines) {
        final box = line.boundingBox;
        lines.add(OcrLine(
          line.text,
          BBox(box.left, box.top, box.width, box.height),
          confidence: 0.9,
        ));
      }
    }
    return lines;
  }

  /// Read a photo, turning it upright first if it needs it.
  Future<PhotoParseResult?> readSheet(File photo, String pageId,
      {ProgressCallback? progress, int index = 0, int total = 1}) async {
    final name = p.basename(photo.path);
    progress?.call(PhotoImportProgress(index, total, 'reading', name));

    var workingPath = photo.path;
    var lines = await _read(workingPath);
    var decoded = img.decodeImage(await photo.readAsBytes());
    if (decoded == null) return null;

    // Which way up is decided by the shape of the text boxes, not by what the
    // text says: OCR reads a line lying on its side perfectly well.
    if (textDirectionScore(lines) < 0.8 || lines.isEmpty) {
      progress?.call(PhotoImportProgress(index, total, 'turning it upright', name));
      var best = lines;
      var bestScore = textDirectionScore(lines);
      var bestImage = decoded;
      for (final angle in [90, 180, 270]) {
        final turned = img.copyRotate(decoded, angle: angle);
        final candidatePath = p.join(imagesDirectory.path, '$pageId.turn$angle.jpg');
        await File(candidatePath).writeAsBytes(img.encodeJpg(turned, quality: 90));
        final candidate = await _read(candidatePath);
        final score = textDirectionScore(candidate);
        if (score > bestScore) {
          bestScore = score;
          best = candidate;
          bestImage = turned;
          workingPath = candidatePath;
        } else {
          await File(candidatePath).delete();
        }
      }
      lines = best;
      decoded = bestImage;
    }

    // Upside down? Read the page's own habits: notch numbers count down a page.
    final height = decoded.height.toDouble();
    if (upsideDownScore(lines, height) > 0) {
      progress?.call(PhotoImportProgress(index, total, 'turning it the right way up', name));
      final turned = img.copyRotate(decoded, angle: 180);
      final candidatePath = p.join(imagesDirectory.path, '$pageId.flip.jpg');
      await File(candidatePath).writeAsBytes(img.encodeJpg(turned, quality: 90));
      lines = await _read(candidatePath);
      decoded = turned;
      if (workingPath != photo.path) await File(workingPath).delete();
      workingPath = candidatePath;
    }

    progress?.call(PhotoImportProgress(index, total, 'working out the shelves', name));
    // The printed bay dividers matter: a page where only the first bay prints
    // its notch lines still has its bay lines, and without them everything
    // lands in bay 1.
    final scan = scanRules(decoded);
    final result = parsePhotoText(
      lines,
      width: decoded.width.toDouble(),
      height: decoded.height.toDouble(),
      pageId: pageId,
      verticalRules: scan.verticals,
    );

    // Keep the upright copy at a size worth zooming into, and no larger.
    final stored = File(p.join(imagesDirectory.path, '$pageId.jpg'));
    final longest = decoded.width > decoded.height ? decoded.width : decoded.height;
    final scaled = longest > 2200
        ? img.copyResize(decoded,
            width: decoded.width > decoded.height ? 2200 : null,
            height: decoded.height >= decoded.width ? 2200 : null)
        : decoded;
    await stored.writeAsBytes(img.encodeJpg(scaled, quality: 84));
    if (workingPath != photo.path) {
      final temporary = File(workingPath);
      if (await temporary.exists()) await temporary.delete();
    }

    // The boxes were measured on the full-size image; scale them with it.
    final factor = scaled.width / decoded.width;
    result.page.imagePath = stored.path;
    return PhotoParseResult(
      page: _scaledPage(result.page, factor, scaled.width.toDouble(),
          scaled.height.toDouble(), stored.path),
      layoutName: result.layoutName,
      layoutSize: result.layoutSize,
      warnings: result.warnings,
    );
  }

  PlanogramPage _scaledPage(PlanogramPage page, double factor, double width,
      double height, String imagePath) {
    if (factor == 1) {
      page.imagePath = imagePath;
      return page;
    }
    BBox? scale(BBox? box) => box == null
        ? null
        : BBox(box.x * factor, box.y * factor, box.w * factor, box.h * factor);

    return PlanogramPage(
      id: page.id,
      number: page.number,
      totalPages: page.totalPages,
      size: [width, height],
      warnings: page.warnings,
      imagePath: imagePath,
      bays: [
        for (final bay in page.bays)
          Bay(
            index: bay.index,
            xRange: [bay.left * factor, bay.right * factor],
            shelvesInherited: bay.shelvesInherited,
            shelves: [
              for (final shelf in bay.shelves)
                Shelf(
                  indexFromTop: shelf.indexFromTop,
                  yRange: [shelf.top * factor, shelf.bottom * factor],
                  notch: shelf.notch,
                  depthCm: shelf.depthCm,
                  slope: shelf.slope,
                  inherited: shelf.inherited,
                ),
            ],
          ),
      ],
      products: [
        for (final product in page.products)
          Product(
            code: product.code,
            name: product.name,
            cases: product.cases,
            bbox: scale(product.bbox),
            imageBbox: scale(product.imageBbox),
            bay: product.bay,
            shelf: product.shelf,
            positionLeft: product.positionLeft,
            positionRight: product.positionRight,
            confidence: product.confidence,
            tags: product.tags,
          ),
      ],
    );
  }
}

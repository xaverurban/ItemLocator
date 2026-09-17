"""The page viewer: zoom, pan, and a highlight that dims the rest of the sheet."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (QEasingCurve, QPointF, QRectF, QVariantAnimation, Qt, Signal)
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF, QWheelEvent)
from PySide6.QtWidgets import (QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsPolygonItem,
                               QGraphicsScene, QGraphicsView, QSizePolicy)

from ..core.imaging import map_box
from ..core.models import BBox, Page, Product
from . import theme

MIN_SCALE = 0.05
MAX_SCALE = 14.0
ZOOM_MS = 190


def _polygon(points) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in points])


def _box_points(box: BBox) -> list[tuple[float, float]]:
    return [(box.x, box.y), (box.x2, box.y), (box.x2, box.y2), (box.x, box.y2)]


def _padded(box: Optional[BBox], fraction: float = 0.10, least: float = 6.0) -> Optional[BBox]:
    """A little breathing room around a label, so the outline does not clip the text."""
    if box is None:
        return None
    margin_x = max(box.w * fraction, least)
    margin_y = max(box.h * fraction, least)
    return BBox(box.x - margin_x, box.y - margin_y,
                box.w + 2 * margin_x, box.h + 2 * margin_y)


class PageViewer(QGraphicsView):
    """Shows one page, with an optional product highlighted."""

    productClicked = Signal(object)          # Product or None
    viewChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setBackgroundBrush(QBrush(QColor(theme.BACKGROUND)))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.grabGesture(Qt.GestureType.PinchGesture)

        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._dim_item: Optional[QGraphicsPathItem] = None
        self._glow_items: list[QGraphicsPolygonItem] = []
        self._highlight_item: Optional[QGraphicsPolygonItem] = None
        self._shelf_item: Optional[QGraphicsPolygonItem] = None
        self._bay_item: Optional[QGraphicsPolygonItem] = None

        self._page: Optional[Page] = None
        self._product: Optional[Product] = None
        self._showing_original = False
        self._animation: Optional[QVariantAnimation] = None

        self.highlight_colour = QColor(theme.DEFAULT_HIGHLIGHT)
        self.dim_level = 50
        self._empty = True

    # -- content ----------------------------------------------------------
    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def showing_original(self) -> bool:
        return self._showing_original

    def clear_page(self) -> None:
        self._scene.clear()
        self._pixmap_item = None
        self._dim_item = None
        self._glow_items = []
        self._highlight_item = self._shelf_item = self._bay_item = None
        self._page = None
        self._product = None
        self._empty = True

    def show_page(self, page: Page, image_path: str, original: bool = False,
                  keep_view: bool = False) -> bool:
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if pixmap.isNull():
            self.clear_page()
            return False

        previous = self.mapToScene(self.viewport().rect()).boundingRect()
        same_page = keep_view and self._page is not None and self._page.id == page.id

        self._scene.clear()
        self._glow_items = []
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._page = page
        self._showing_original = original
        self._empty = False

        self._build_overlay_items()
        if self._product is not None:
            self.highlight(self._product, animate=False, zoom=False)
        if same_page and previous.isValid():
            self.fitInView(previous, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.fit_page()
        return True

    def _build_overlay_items(self) -> None:
        self._dim_item = QGraphicsPathItem()
        self._dim_item.setBrush(QBrush(QColor(0, 0, 0, 0)))
        self._dim_item.setPen(QPen(Qt.PenStyle.NoPen))
        self._dim_item.setZValue(10)
        self._scene.addItem(self._dim_item)

        def outline(colour: QColor, width: float, z: float, dashed: bool = False):
            item = QGraphicsPolygonItem()
            pen = QPen(colour, width)
            pen.setCosmetic(True)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            if dashed:
                pen.setStyle(Qt.PenStyle.DashLine)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            item.setZValue(z)
            item.setVisible(False)
            self._scene.addItem(item)
            return item

        faint = QColor(self.highlight_colour)
        faint.setAlpha(110)
        self._bay_item = outline(QColor(theme.DEFAULT_ACCENT), 1.5, 11, dashed=True)
        self._shelf_item = outline(faint, 1.5, 12, dashed=True)
        for index, (width, alpha) in enumerate(((11.0, 45), (7.0, 80), (4.0, 130))):
            glow_colour = QColor(self.highlight_colour)
            glow_colour.setAlpha(alpha)
            self._glow_items.append(outline(glow_colour, width, 13 + index))
        self._highlight_item = outline(QColor(self.highlight_colour), 2.4, 20)

    # -- highlighting -----------------------------------------------------
    def set_highlight_colour(self, colour: str) -> None:
        self.highlight_colour = QColor(colour)
        if self._page is not None:
            self._build_overlay_items_refresh()

    def set_dim_level(self, percent: int) -> None:
        self.dim_level = max(0, min(90, int(percent)))
        if self._product is not None:
            self.highlight(self._product, animate=False, zoom=False)

    def _build_overlay_items_refresh(self) -> None:
        for item in [self._dim_item, self._highlight_item, self._shelf_item,
                     self._bay_item, *self._glow_items]:
            if item is not None:
                self._scene.removeItem(item)
        self._glow_items = []
        self._build_overlay_items()
        if self._product is not None:
            self.highlight(self._product, animate=False, zoom=False)

    def _map(self, box: Optional[BBox]) -> Optional[list[tuple[float, float]]]:
        """Box corners in the coordinates of whatever image is on screen."""
        if box is None or self._page is None:
            return None
        points = _box_points(box)
        if self._showing_original and self._page.transform:
            return map_box(self._page.transform,
                           (box.x, box.y, box.x2, box.y2), inverse=True)
        return points

    def clear_highlight(self) -> None:
        self._product = None
        for item in [self._highlight_item, self._shelf_item, self._bay_item,
                     *self._glow_items]:
            if item is not None:
                item.setVisible(False)
        if self._dim_item is not None:
            self._dim_item.setPath(QPainterPath())
            self._dim_item.setBrush(QBrush(QColor(0, 0, 0, 0)))

    def highlight(self, product: Optional[Product], animate: bool = True,
                  zoom: bool = True) -> None:
        if product is None or self._page is None or self._pixmap_item is None:
            self.clear_highlight()
            return

        self._product = product
        # Highlight the product itself - its label - not the whole shelf run.
        # The shelf and bay get their own faint outlines below for context.
        target_box = _padded(product.bbox or product.image_bbox)
        points = self._map(target_box)
        if points is None:
            self.clear_highlight()
            return

        polygon = _polygon(points)
        if self._highlight_item is not None:
            self._highlight_item.setPolygon(polygon)
            self._highlight_item.setVisible(True)
        for item in self._glow_items:
            item.setPolygon(polygon)
            item.setVisible(True)

        shelf = self._page.shelf_of(product)
        bay = self._page.bay_of(product)
        if shelf is not None and bay is not None and self._shelf_item is not None:
            band = BBox.from_xyxy(bay.x_range[0], shelf.y_range[0],
                                  bay.x_range[1], shelf.y_range[1])
            mapped = self._map(band)
            if mapped:
                self._shelf_item.setPolygon(_polygon(mapped))
                self._shelf_item.setVisible(True)
        elif self._shelf_item is not None:
            self._shelf_item.setVisible(False)

        if bay is not None and self._bay_item is not None:
            page_height = self._page.size[1] or self._pixmap_item.pixmap().height()
            column = BBox.from_xyxy(bay.x_range[0], 0, bay.x_range[1], page_height)
            mapped = self._map(column)
            if mapped:
                self._bay_item.setPolygon(_polygon(mapped))
                self._bay_item.setVisible(True)
        elif self._bay_item is not None:
            self._bay_item.setVisible(False)

        # Dim everything except the product: one path, filled even-odd.
        if self._dim_item is not None:
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            path.addRect(self._scene.sceneRect())
            path.addPolygon(polygon)
            self._dim_item.setPath(path)
            alpha = int(255 * self.dim_level / 100.0)
            self._dim_item.setBrush(QBrush(QColor(8, 9, 12, alpha)))

        if zoom:
            self.zoom_to(polygon.boundingRect(), animate=animate)

    # -- navigation -------------------------------------------------------
    def fit_page(self) -> None:
        if self._pixmap_item is None:
            return
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.viewChanged.emit()

    def zoom_to(self, rect: QRectF, animate: bool = True, margin: float = 1.35,
                min_fraction: float = 0.28) -> None:
        """Frame ``rect`` with a little context around it.

        The frame never shrinks below a fraction of the page, so a small label
        does not zoom in so far that the shelf around it disappears.
        """

        if self._pixmap_item is None or not rect.isValid():
            return
        page = self._scene.sceneRect()
        least_width = page.width() * min_fraction
        least_height = page.height() * min_fraction
        target = QRectF(rect)
        target.setWidth(max(rect.width() * margin, least_width))
        target.setHeight(max(rect.height() * margin, least_height))
        target.moveCenter(rect.center())
        target = target.intersected(self._scene.sceneRect().adjusted(-40, -40, 40, 40))

        if not animate:
            self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
            self.viewChanged.emit()
            return

        start = self.mapToScene(self.viewport().rect()).boundingRect()
        animation = QVariantAnimation(self)
        animation.setDuration(ZOOM_MS)
        animation.setStartValue(start)
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.valueChanged.connect(
            lambda value: self.fitInView(value, Qt.AspectRatioMode.KeepAspectRatio))
        animation.finished.connect(self.viewChanged.emit)
        animation.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
        self._animation = animation

    def current_scale(self) -> float:
        return float(self.transform().m11())

    def zoom_by(self, factor: float) -> None:
        scale = self.current_scale()
        if scale * factor < MIN_SCALE or scale * factor > MAX_SCALE:
            return
        self.scale(factor, factor)
        self.viewChanged.emit()

    # -- events -----------------------------------------------------------
    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap_item is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self.zoom_by(1.0015 ** delta)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.fit_page()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton or self._page is None:
            return
        # A drag is a pan, not a click.
        if (event.position() - self._press_position).manhattanLength() > 6:
            return
        scene_point = self.mapToScene(event.position().toPoint())
        point = (scene_point.x(), scene_point.y())
        if self._showing_original and self._page.transform:
            from ..core.imaging import map_points
            point = map_points(self._page.transform, [point])[0]
        self.productClicked.emit(point)

    def mousePressEvent(self, event) -> None:
        self._press_position = event.position()
        super().mousePressEvent(event)

    def event(self, event):
        if event.type() == event.Type.Gesture:
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if pinch is not None:
                self.zoom_by(pinch.scaleFactor())
                return True
        return super().event(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._empty:
            return
        self.viewChanged.emit()

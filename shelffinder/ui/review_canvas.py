"""The interactive page on the review screen: boxes and lines you can drag."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsLineItem, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView)

from ..core.models import BBox, Page, Product
from . import theme

HANDLE = 9.0                    # size of the corner grip, in scene pixels
MIN_BOX = 12.0


class ProductBox(QGraphicsRectItem):
    """One product's label box: drag the middle to move, the corner to resize."""

    def __init__(self, product: Product, canvas: "ReviewCanvas") -> None:
        box = product.bbox or BBox(0, 0, 40, 30)
        super().__init__(QRectF(box.x, box.y, box.w, box.h))
        self.product = product
        self._canvas = canvas
        self._resizing = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(20)
        self.refresh()

    # -- looks ------------------------------------------------------------
    def refresh(self) -> None:
        from ..core.editing import needs_checking

        if self.isSelected():
            colour = QColor(theme.DEFAULT_HIGHLIGHT)
            width = 3.0
        elif needs_checking(self.product):
            colour = QColor(theme.AMBER)
            width = 2.0
        elif self.product.manually_edited:
            colour = QColor(theme.GREEN)
            width = 2.0
        else:
            colour = QColor(theme.DEFAULT_ACCENT)
            width = 1.6
        pen = QPen(colour, width)
        pen.setCosmetic(True)
        self.setPen(pen)
        fill = QColor(colour)
        fill.setAlpha(36 if self.isSelected() else 0)
        self.setBrush(QBrush(fill))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.refresh()
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor(theme.DEFAULT_HIGHLIGHT), 0))
            painter.setBrush(QBrush(QColor(theme.DEFAULT_HIGHLIGHT)))
            painter.drawRect(self._handle_rect())

    def _handle_rect(self) -> QRectF:
        rect = self.rect()
        return QRectF(rect.right() - HANDLE, rect.bottom() - HANDLE, HANDLE, HANDLE)

    # -- geometry ---------------------------------------------------------
    def scene_box(self) -> BBox:
        rect = self.rect()
        origin = self.pos()
        return BBox(rect.x() + origin.x(), rect.y() + origin.y(), rect.width(), rect.height())

    def mousePressEvent(self, event) -> None:
        if self._handle_rect().contains(event.pos()):
            self._resizing = True
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resizing:
            rect = QRectF(self.rect())
            rect.setBottomRight(QPointF(max(event.pos().x(), rect.left() + MIN_BOX),
                                        max(event.pos().y(), rect.top() + MIN_BOX)))
            self.setRect(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        was_resizing = self._resizing
        self._resizing = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        super().mouseReleaseEvent(event)
        if was_resizing or self.pos() != QPointF(0, 0):
            self._canvas.boxMoved.emit(self.product, self.scene_box())


class GuideLine(QGraphicsLineItem):
    """A bay divider or a shelf rule, draggable along one axis."""

    def __init__(self, canvas: "ReviewCanvas", vertical: bool, position: float,
                 span: tuple[float, float], bay_index: int = 0, edge_index: int = 0) -> None:
        super().__init__()
        self._canvas = canvas
        self.vertical = vertical
        self.bay_index = bay_index
        self.edge_index = edge_index
        self.span = span
        self.setZValue(15)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.SizeHorCursor if vertical
                       else Qt.CursorShape.SizeVerCursor)
        colour = QColor(theme.DEFAULT_ACCENT) if vertical else QColor(theme.GREEN)
        pen = QPen(colour, 2.0)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.place(position)

    def place(self, position: float) -> None:
        if self.vertical:
            self.setLine(position, self.span[0], position, self.span[1])
        else:
            self.setLine(self.span[0], position, self.span[1], position)
        self.setPos(0, 0)

    def position(self) -> float:
        line = self.line()
        offset = self.pos()
        return line.x1() + offset.x() if self.vertical else line.y1() + offset.y()

    def mouseMoveEvent(self, event) -> None:
        # Only along its own axis: a shelf rule stays level.
        delta = event.scenePos() - event.lastScenePos()
        if self.vertical:
            self.moveBy(delta.x(), 0)
        else:
            self.moveBy(0, delta.y())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self._canvas.guideMoved.emit(self)


class ReviewCanvas(QGraphicsView):
    """The page, with everything on it editable."""

    boxMoved = Signal(object, object)          # product, new BBox
    guideMoved = Signal(object)                # GuideLine
    selectionChanged = Signal(object)          # Product or None
    drawFinished = Signal(object)              # BBox for a new product

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(theme.BACKGROUND)))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

        self._page: Optional[Page] = None
        self._boxes: list[ProductBox] = []
        self._guides: list[GuideLine] = []
        self._drawing_from: Optional[QPointF] = None
        self._draw_preview: Optional[QGraphicsRectItem] = None
        self.drawing_mode = False
        self._fitted = False
        self._scene.selectionChanged.connect(self._selection_changed)

    # -- content ----------------------------------------------------------
    def show_page(self, page: Page, image_path: str) -> bool:
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        self._scene.clear()
        self._boxes = []
        self._guides = []
        self._page = page
        if pixmap.isNull():
            return False

        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.rebuild()
        self._fitted = False
        self.fit_page()
        return True

    def rebuild(self) -> None:
        """Redraw every box and line from the page as it now stands."""
        if self._page is None:
            return
        selected = self.selected_product()
        for item in self._boxes + self._guides:
            self._scene.removeItem(item)
        self._boxes = []
        self._guides = []

        height = self._scene.sceneRect().height()
        width = self._scene.sceneRect().width()

        edges: list[float] = []
        for bay in self._page.bays:
            edges.extend([bay.x_range[0], bay.x_range[1]])
        for index, position in enumerate(sorted(set(round(edge, 2) for edge in edges))):
            if position <= 1 or position >= width - 1:
                continue
            guide = GuideLine(self, vertical=True, position=position, span=(0, height),
                              edge_index=index)
            self._scene.addItem(guide)
            self._guides.append(guide)

        for bay in self._page.bays:
            shelf_edges = sorted({round(edge, 2) for shelf in bay.shelves
                                  for edge in shelf.y_range})
            for index, position in enumerate(shelf_edges):
                guide = GuideLine(self, vertical=False, position=position,
                                  span=(bay.x_range[0], bay.x_range[1]),
                                  bay_index=bay.index, edge_index=index)
                self._scene.addItem(guide)
                self._guides.append(guide)

        for product in self._page.products:
            if product.bbox is None:
                continue
            box = ProductBox(product, self)
            self._scene.addItem(box)
            self._boxes.append(box)
            if selected is not None and product.id == selected.id:
                box.setSelected(True)

    def bay_edges(self) -> list[float]:
        inner = sorted(guide.position() for guide in self._guides if guide.vertical)
        return [0.0] + inner + [float(self._scene.sceneRect().width())]

    def shelf_edges(self, bay_index: int) -> list[float]:
        return sorted(guide.position() for guide in self._guides
                      if not guide.vertical and guide.bay_index == bay_index)

    # -- selection --------------------------------------------------------
    def selected_product(self) -> Optional[Product]:
        for box in self._boxes:
            if box.isSelected():
                return box.product
        return None

    def select_product(self, product: Optional[Product]) -> None:
        for box in self._boxes:
            box.setSelected(product is not None and box.product.id == product.id)
            box.refresh()
        if product is not None:
            for box in self._boxes:
                if box.product.id == product.id:
                    self.ensureVisible(box, 80, 80)

    def _selection_changed(self) -> None:
        self.selectionChanged.emit(self.selected_product())

    # -- drawing a new box ------------------------------------------------
    def start_drawing(self) -> None:
        self.drawing_mode = True
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def stop_drawing(self) -> None:
        self.drawing_mode = False
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.unsetCursor()
        if self._draw_preview is not None:
            self._scene.removeItem(self._draw_preview)
            self._draw_preview = None

    def mousePressEvent(self, event) -> None:
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drawing_from = self.mapToScene(event.position().toPoint())
            self._draw_preview = self._scene.addRect(
                QRectF(self._drawing_from, self._drawing_from),
                QPen(QColor(theme.DEFAULT_HIGHLIGHT), 2))
            self._draw_preview.setZValue(30)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drawing_mode and self._drawing_from is not None:
            corner = self.mapToScene(event.position().toPoint())
            self._draw_preview.setRect(QRectF(self._drawing_from, corner).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.drawing_mode and self._drawing_from is not None:
            corner = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._drawing_from, corner).normalized()
            self._drawing_from = None
            self.stop_drawing()
            if rect.width() >= MIN_BOX and rect.height() >= MIN_BOX:
                self.drawFinished.emit(BBox(rect.x(), rect.y(), rect.width(), rect.height()))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -- navigation -------------------------------------------------------
    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            factor = 1.0015 ** delta
            scale = self.transform().m11() * factor
            if 0.05 < scale < 14:
                self.scale(factor, factor)
        event.accept()

    def fit_page(self) -> None:
        if self._scene.sceneRect().isValid():
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The first fit has to wait for the widget to have its real size, or the
        # page ends up a postage stamp in the middle of the view.
        if not self._fitted:
            self.fit_page()
            self._fitted = True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._fitted:
            self.fit_page()

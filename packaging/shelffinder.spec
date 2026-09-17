# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for ShelfFinder (one folder, so it starts quickly).

    pyinstaller packaging/shelffinder.spec --noconfirm
"""

import os

from PyInstaller.utils.hooks import (collect_data_files, collect_dynamic_libs,
                                     collect_submodules)

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# The OCR models ship inside the wheel; without them the app would try to work
# with no recogniser at all.
datas = collect_data_files("rapidocr_onnxruntime", include_py_files=False)
datas += collect_data_files("pypdfium2_raw", include_py_files=False)
binaries = collect_dynamic_libs("onnxruntime")

hiddenimports = [
    "rapidocr_onnxruntime",
    "onnxruntime",
    "onnxruntime.capi._pybind_state",
    "pillow_heif",
    "pypdfium2",
    "shelffinder.selftest",
]
# PyInstaller's bundled hooks trail new NumPy releases, and a missing private
# submodule only shows up at run time ("No module named numpy._core._exceptions"),
# so take the whole package.
hiddenimports += collect_submodules("numpy")

# Qt modules this app never touches - leaving them out keeps the folder sane.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtQuick3D",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtWebSockets", "PySide6.QtPdf",
    "matplotlib", "scipy", "pandas", "tkinter", "pytest", "IPython", "notebook",
    # onnxruntime ships benchmark and training tooling we never call; it drags in
    # pkg_resources, whose PyInstaller runtime hook then fails on a missing
    # backports module.
    "onnxruntime.transformers", "onnxruntime.training", "onnxruntime.tools",
    "pkg_resources", "setuptools", "jaraco", "backports",
    "numpy.distutils", "numpy.f2py", "numpy.testing", "numpy._pyinstaller",
]

analysis = Analysis(
    [os.path.join(ROOT, "packaging", "entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(analysis.pure)

def _exe(name: str, console: bool):
    return EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=console,
        disable_windowed_traceback=False,
        icon=None,
    )


# Two front ends over one set of libraries: the normal windowed app, and a
# console build that prints what went wrong (and runs --selftest in CI).
app_exe = _exe("ShelfFinder", console=False)
console_exe = _exe("ShelfFinder-console", console=True)

COLLECT(
    app_exe,
    console_exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ShelfFinder",
)

# Native distribution notice

Retro Web UI GUI is MIT-licensed application code. The native archives also
contain a CPython 3.12 runtime and dynamically loaded Qt for Python libraries.
Those components remain under their own licenses; no commercial Qt license is
claimed by this project.

## Qt for Python / PySide6 / Shiboken6 / Qt 6

The release builder pins PySide6 6.11.2 (including PySide6 Essentials,
PySide6 Addons, and Shiboken6) and distributes the Qt libraries under the
LGPL-3.0-only option advertised by the upstream wheel metadata. The libraries
are kept as separate shared-library files so an interface-compatible modified
Qt build can replace them. Retro Web UI does not restrict reverse engineering
for debugging such a replacement. The application does not modify the Qt or
PySide source.

The complete GPLv3 and LGPLv3 license texts accompany every native archive as
`GPL-3.0-only.txt` and `LGPL-3.0-only.txt`.

Corresponding upstream source and Qt's third-party attribution files are
available from:

- https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.11.2
- https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/
- https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/
- https://doc.qt.io/qtforpython-6/licenses.html

Keep this notice with the shared libraries. If an official source mirror moves,
the Git tag and release archive above identify the exact corresponding source.

## CPython and native support libraries

The executable contains CPython 3.12 and selected standard-library extension
modules. `PYTHON-3.12-LICENSE.txt` contains the Python Software Foundation
license and the notices shipped by CPython for incorporated components.

Depending on the operating-system build, the archive may also contain separate
OpenSSL, XZ/liblzma, and mpdecimal libraries. Their presence and exact paths are
recorded in the generated `NATIVE_COMPONENTS.json` shipped in that archive.
The applicable texts are included as `OPENSSL-LICENSE.txt`,
`XZ-UTILS-COPYING.txt`, and `MPDECIMAL-LICENSE.txt`. System libraries named in
the native report are prerequisites and are not redistributed by Retro Web UI.

## Build tools

Nuitka, Pillow, ordered-set, zstandard, and patchelf are build-time tools. They
are not intentionally shipped as application packages. Nuitka-compiled helper
code, if present in the generated executable, is covered by the Apache-2.0
Nuitka runtime terms recorded in the upstream Nuitka distribution.

The machine-readable component inventory is evidence of archive contents, not
a substitute for the accompanying license texts.

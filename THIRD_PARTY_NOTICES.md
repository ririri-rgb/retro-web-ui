# Third-party notices

No third-party source code, fonts, icons, Windows assets, or binary dependencies are vendored in this repository. Some documentation screenshots are rendered from the two temporary upstream checkouts described below.

The documentation links to OpenAI, Microsoft, framework, historical software, and independent OSS sources as research references. Linked material remains under its respective owner's terms and is not redistributed here.

98.css, XP.css, 7.css, React95, and other retro UI libraries were evaluated as architecture and interoperability references. Their code and assets are not copied into this project. If a future contribution vendors or derives third-party material, it must record the exact project, version/commit, source URL, license, files used, modifications, and required attribution in this file.

## Optional GUI and deployment tools

The source distribution declares PySide6 as an optional dependency but does not
vendor its binaries. Qt for Python/PySide6 is available under LGPLv3/GPLv3 or a
Qt commercial license; redistributors of a native GUI artifact must select and
comply with the applicable Qt terms and included third-party notices. See
[Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html).

`deployment/pysidedeploy.spec` names Nuitka as a deployment-time compiler. It is
not installed by the package and no Nuitka output is committed. Nuitka is
licensed under the Apache License 2.0; a distributor that uses the spec must
retain the required notices in its build artifacts.

## TodoMVC documentation screenshot

`screenshots/todomvc-windows-98.png` shows the rendered `examples/javascript-es6` application from [tastejs/todomvc](https://github.com/tastejs/todomvc) commit `ff43b02e59dfa604386bb382034b2cd07c2bcd8a`, modified in a temporary checkout with this project's Windows 98 CSS and semantic markup mapping. The upstream source is not included. TodoMVC is MIT licensed:

The desktop-GUI engineering record also includes
`screenshots/gui/todomvc-before.png` and
`screenshots/gui/todomvc-after-windows-xp.png` from the same pinned checkout.
They are documentation evidence only; no TodoMVC source is included.

Copyright (c) Addy Osmani, Sindre Sorhus, Pascal Hartig, Stephen Sawchuk.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## naive-ui-admin documentation screenshot

`screenshots/real-oss-naive-ui-admin-japanese-freeware.png` shows the login surface from [jekip/naive-ui-admin](https://github.com/jekip/naive-ui-admin) commit `3a469f1aca0b1b9d47d7c9e771c26dce058ea345`, modified in a temporary checkout with this project's Japanese Freeware 2000s theme and semantic markup mapping. The upstream source is not included. naive-ui-admin is MIT licensed:

Copyright (c) 2021-present Naive Ui Admin

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

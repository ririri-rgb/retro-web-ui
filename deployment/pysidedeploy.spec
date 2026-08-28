[app]
title = Retro Web UI GUI
project_dir = .
input_file = retro_web_ui_gui/launcher.py
exec_directory = dist/native
project_file =
icon =

[python]
python_path =
packages = Nuitka==4.1.1
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]
qml_files =
excluded_qml_plugins =
modules = Widgets,Core,Gui
plugins = platformthemes,accessiblebridge,generic,iconengines,platforms,imageformats,platforminputcontexts,styles

[android]
wheel_pyside =
wheel_shiboken =
plugins =

[nuitka]
macos.permissions =
mode = standalone
extra_args = --quiet --output-filename=retro-web-ui-gui --noinclude-qt-translations --static-libpython=no --include-package=retro_web_ui --include-package-data=retro_web_ui

[buildozer]
mode = debug
recipe_dir =
jars_dir =
ndk_path =
sdk_path =
local_libs =
arch =

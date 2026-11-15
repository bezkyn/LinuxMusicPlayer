import os, re, shutil, subprocess, sys, glob
APPDIR = sys.argv[1]
SP = glob.glob(f"{APPDIR}/opt/python3.12/lib/python3.12/site-packages")[0]
PQ = f"{SP}/PyQt6"; QT = f"{PQ}/Qt6"; LIB = f"{QT}/lib"
KEEP_MODS = {"QtCore", "QtGui", "QtWidgets", "QtDBus", "QtSvg", "QtMultimedia", "QtNetwork"}
KEEP_PLUGIN_DIRS = {"platforms", "platformthemes", "platforminputcontexts", "imageformats",
                    "iconengines", "xcbglintegrations", "wayland-decoration-client",
                    "wayland-graphics-integration-client", "wayland-shell-integration",
                    "egldeviceintegrations", "multimedia", "tls", "networkinformation"}
# 1) módulos Python do PyQt6 que não usamos
for f in glob.glob(f"{PQ}/Qt*.abi3.so") + glob.glob(f"{PQ}/Qt*.pyi"):
    if os.path.basename(f).split(".")[0] not in KEEP_MODS:
        os.remove(f)
# 2) pastas de plugins, QML, QScintilla
for d in os.listdir(f"{QT}/plugins"):
    if d not in KEEP_PLUGIN_DIRS:
        shutil.rmtree(f"{QT}/plugins/{d}")
for d in ("qml", "qsci"):
    shutil.rmtree(f"{QT}/{d}", ignore_errors=True)
for f in glob.glob(f"{QT}/translations/*.qm"):
    if not os.path.basename(f).startswith("qtbase_"):
        os.remove(f)
# 3) bibliotecas do Qt: só o que os módulos e plugins mantidos usam (fecho do ldd)
roots = glob.glob(f"{PQ}/*.so") + glob.glob(f"{QT}/plugins/**/*.so", recursive=True)
need, todo = set(), list(roots)
env = dict(os.environ, LD_LIBRARY_PATH=LIB)
while todo:
    so = todo.pop()
    out = subprocess.run(["ldd", so], capture_output=True, text=True, env=env).stdout
    for m in re.finditer(r"=>\s+(\S+)", out):
        p = os.path.realpath(m.group(1))
        if p.startswith(os.path.realpath(LIB)) and p not in need:
            need.add(p); todo.append(p)
removed = 0
for f in os.listdir(LIB):
    p = os.path.realpath(f"{LIB}/{f}")
    if os.path.isfile(p) and p not in need and ".so" in f:
        os.remove(f"{LIB}/{f}"); removed += 1
print("Qt libs mantidas:", sorted(os.path.basename(x) for x in need))
print("Qt libs removidas:", removed)
# 4) partes do Python que não usamos
py = f"{APPDIR}/opt/python3.12/lib/python3.12"
for d in ("test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "pydoc_data"):
    shutil.rmtree(f"{py}/{d}", ignore_errors=True)
for f in glob.glob(f"{py}/lib-dynload/_tkinter*"):
    os.remove(f)
shutil.rmtree(f"{APPDIR}/usr/share/tcltk", ignore_errors=True)
for d in glob.glob(f"{SP}/pip*"):
    shutil.rmtree(d, ignore_errors=True)
for f in glob.glob(f"{APPDIR}/usr/bin/pip*") + glob.glob(f"{APPDIR}/opt/python3.12/bin/pip*"):
    os.remove(f)

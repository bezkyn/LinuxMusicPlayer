#!/usr/bin/env bash
# Monta o Linux-Music-Player-<versão>-x86_64.AppImage.
#
# O AppImage leva tudo dentro: um Python 3.12 portátil (projeto python-appimage,
# manylinux2014), PyQt6/Qt 6 com o som (FFmpeg) e o mutagen. Depois o script
# enxugar.py tira o que o programa não usa.
#
# Uso:  packaging/build-appimage.sh          (o resultado vai para dist/)
# Precisa de: bash, curl, python3, ldd. Não precisa de FUSE.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
VERSAO="${VERSAO:-$(python3 "$RAIZ/packaging/versao.py")}"
OBRA="${OBRA:-$RAIZ/build/appimage}"
DIST="$RAIZ/dist"
SAIDA="$DIST/Linux-Music-Player-$VERSAO-x86_64.AppImage"
export APPIMAGE_EXTRACT_AND_RUN=1          # roda AppImages sem FUSE (CI, contêineres)

echo "==> Linux Music Player $VERSAO"
rm -rf "${OBRA:?}"
mkdir -p "$OBRA" "$DIST"
cd "$OBRA"

# 1. Python portátil (a versão 3.12 mais nova do python-appimage)
echo "==> Baixando o Python 3.12 portátil"
URL_PY="$(curl -fsSL ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} \
    https://api.github.com/repos/niess/python-appimage/releases/tags/python3.12 \
  | python3 -c '
import json, re, sys
assets = json.load(sys.stdin)["assets"]
ok = [a for a in assets if re.fullmatch(r"python3\.12\.\d+-cp312-cp312-manylinux2014_x86_64\.AppImage", a["name"])]
ok.sort(key=lambda a: int(a["name"].split("-")[0].split(".")[2]))
print(ok[-1]["browser_download_url"])')"
echo "    $URL_PY"
curl -fsSL -o python.AppImage "$URL_PY"
chmod +x python.AppImage
./python.AppImage --appimage-extract >/dev/null
mv squashfs-root AppDir

# o que é do Python e não do player
rm -f AppDir/AppRun AppDir/.DirIcon AppDir/*.desktop AppDir/*.png AppDir/*.svg
rm -rf AppDir/usr/share/applications AppDir/usr/share/metainfo AppDir/usr/share/icons

# 2. PyQt6 e mutagen
echo "==> Instalando PyQt6 e mutagen"
PY="$OBRA/AppDir/opt/python3.12/bin/python3.12"
env -u PYTHONPATH -u PYTHONHOME "$PY" -s -m pip install --no-cache-dir --no-compile --disable-pip-version-check \
    -r "$RAIZ/packaging/requisitos-appimage.txt"

# 3. Enxugar: só os módulos, plugins e bibliotecas do Qt que o programa usa
echo "==> Enxugando"
python3 "$RAIZ/packaging/appimage/enxugar.py" "$OBRA/AppDir"
find AppDir -name __pycache__ -type d -prune -exec rm -rf {} +

# 4. O programa
echo "==> Copiando o programa"
APP="AppDir/usr/share/linux-music-player"
mkdir -p "$APP"
cp "$RAIZ/linux-music-player.py" "$RAIZ/LEIA-ME.txt" "$RAIZ/LICENCA-ICONES-PHOSPHOR.txt" "$APP/"
cp "$RAIZ/packaging/icons/hicolor/256x256/apps/linux-music-player.png" "$APP/linux-music-player.png"
cp -r "$RAIZ/fontes" "$APP/"
[ -f "$RAIZ/LICENSE" ] && cp "$RAIZ/LICENSE" "$APP/"
install -m 755 "$RAIZ/packaging/appimage/AppRun" AppDir/AppRun
# o atalho de dentro do AppImage se chama "reprodutor" (o Gear Lever já usa esse nome)
sed -e 's/^Exec=.*/Exec=reprodutor %F/' -e '/^TryExec=/d' -e 's/^Icon=.*/Icon=reprodutor/' \
    "$RAIZ/packaging/linux-music-player.desktop" > AppDir/reprodutor.desktop
echo "X-AppImage-Version=$VERSAO" >> AppDir/reprodutor.desktop
cp "$RAIZ/packaging/icons/hicolor/256x256/apps/linux-music-player.png" AppDir/reprodutor.png
cp AppDir/reprodutor.png AppDir/.DirIcon
for d in "$RAIZ"/packaging/icons/hicolor/*/; do
    s="$(basename "$d")"
    mkdir -p "AppDir/usr/share/icons/hicolor/$s/apps"
    for f in "$d"apps/*; do
        cp "$f" "AppDir/usr/share/icons/hicolor/$s/apps/reprodutor.${f##*.}"
    done
done
chmod -R a+rX AppDir

# 5. Montar
echo "==> Montando o AppImage"
if [ -n "${APPIMAGETOOL:-}" ]; then
    TOOL="$APPIMAGETOOL"
else
    curl -fsSL -o appimagetool.AppImage \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool.AppImage
    TOOL="$OBRA/appimagetool.AppImage"
fi
rm -f "$SAIDA"
ARCH=x86_64 VERSION="$VERSAO" "$TOOL" ${APPIMAGETOOL_ARGS:-} --comp zstd AppDir "$SAIDA"
echo "==> Pronto: $SAIDA ($(du -h "$SAIDA" | cut -f1))"

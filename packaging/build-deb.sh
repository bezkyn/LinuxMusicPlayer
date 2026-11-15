#!/usr/bin/env bash
# Monta o linux-music-player_<versão>_all.deb (Debian 12+, Ubuntu 24.04+, Mint 22+).
#
# O .deb é pequeno: leva só o programa, a fonte Inter e os ícones. O Python, o
# PyQt6 e o mutagen vêm dos pacotes da própria distribuição (Depends).
#
# Uso:  packaging/build-deb.sh          (o resultado vai para dist/)
# Precisa de: dpkg-deb (pacote dpkg) e python3.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
VERSAO="${VERSAO:-$(python3 "$RAIZ/packaging/versao.py")}"
MANTENEDOR="${MANTENEDOR:-Linux Music Player <linux-music-player@users.noreply.github.com>}"
SITE="${SITE:-}"
OBRA="$RAIZ/build/deb"
DIST="$RAIZ/dist"
PKG="$OBRA/linux-music-player_${VERSAO}_all"
SAIDA="$DIST/linux-music-player_${VERSAO}_all.deb"

echo "==> linux-music-player $VERSAO (.deb)"
rm -rf "${OBRA:?}"
mkdir -p "$PKG/DEBIAN" "$DIST"

# programa
APP="$PKG/usr/share/linux-music-player"
install -d "$APP" "$APP/fontes"
install -m 644 "$RAIZ/linux-music-player.py" "$RAIZ/LEIA-ME.txt" "$APP/"
install -m 644 "$RAIZ/packaging/icons/hicolor/256x256/apps/linux-music-player.png" "$APP/linux-music-player.png"
install -m 644 "$RAIZ"/fontes/* "$APP/fontes/"

# comando
install -d "$PKG/usr/bin"
cat > "$PKG/usr/bin/linux-music-player" <<'SH'
#!/bin/sh
exec /usr/bin/python3 /usr/share/linux-music-player/linux-music-player.py "$@"
SH
chmod 755 "$PKG/usr/bin/linux-music-player"

# atalho no menu e ícones
install -D -m 644 "$RAIZ/packaging/linux-music-player.desktop" \
    "$PKG/usr/share/applications/linux-music-player.desktop"
for d in "$RAIZ"/packaging/icons/hicolor/*/; do
    s="$(basename "$d")"
    install -d "$PKG/usr/share/icons/hicolor/$s/apps"
    install -m 644 "$d"apps/* "$PKG/usr/share/icons/hicolor/$s/apps/"
done

# documentação e licenças
DOC="$PKG/usr/share/doc/linux-music-player"
install -d "$DOC"
install -m 644 "$RAIZ/README.md" "$DOC/"
{
    echo "Linux Music Player${SITE:+ — $SITE}"
    echo
    if [ -f "$RAIZ/LICENSE" ]; then
        echo "---- Linux Music Player ----"
        cat "$RAIZ/LICENSE"
        echo
    fi
    echo "---- Ícones Phosphor (embutidos em linux-music-player.py) ----"
    cat "$RAIZ/LICENCA-ICONES-PHOSPHOR.txt"
    echo
    echo "---- Fonte Inter (pasta fontes/) ----"
    cat "$RAIZ/fontes/OFL.txt"
} > "$DOC/copyright"
chmod 644 "$DOC/copyright"

# controle
TAM="$(du -sk "$PKG/usr" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<EOF
Package: linux-music-player
Version: $VERSAO
Section: sound
Priority: optional
Architecture: all
Maintainer: $MANTENEDOR
Installed-Size: $TAM
Depends: python3 (>= 3.9), python3-pyqt6, python3-pyqt6.qtmultimedia, python3-pyqt6.qtsvg, python3-mutagen
EOF
[ -n "$SITE" ] && echo "Homepage: $SITE" >> "$PKG/DEBIAN/control"
cat >> "$PKG/DEBIAN/control" <<'EOF'
Description: tocador de músicas com biblioteca, capas e listas
 Organiza as pastas de música por artista, álbum, gênero e pasta, com a capa
 de cada arquivo, notas em estrelas, listas .m3u8, lista atual com aleatório e
 repetir, e integração com o Plasma/GNOME pelo MPRIS (teclas de mídia, widget
 de mídia, tela de bloqueio, KDE Connect). Temas LMP 1 (claro), LMP 2 (escuro)
 e Do sistema.
EOF

find "$PKG" -type d -exec chmod 755 {} +
rm -f "$SAIDA"
dpkg-deb --root-owner-group --build "$PKG" "$SAIDA"
echo "==> Pronto: $SAIDA ($(du -h "$SAIDA" | cut -f1))"

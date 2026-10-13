#!/bin/sh
# Package + install a webOS app from a source dir. Runs ON the TV.
# Usage: sh install-app.sh <srcdir> <appid> [version] [install|remove] [title]
# srcdir holds appinfo.json, index.html, packageinfo.json, assets/.
ID=${2:-com.lukemulvaney.bar}
VER=${3:-1.0.0}
ACTION=${4:-install}
TITLE=${5:-$ID}
SRC=${1:-/tmp/lgtv-bar/barapp}
APPDIR=/media/developer/apps/usr/palm/applications/$ID
PKGDIR=/media/developer/apps/usr/palm/packages/$ID

if [ "$ACTION" = "remove" ]; then
  RLOG=$(mktemp /tmp/app-rm.XXXXXX) || exit 0
  luna-send -i -w 60000 luna://com.webos.appInstallService/dev/remove \
    "{\"id\":\"$ID\",\"subscribe\":true}" > "$RLOG" 2>&1 &
  rpid=$!
  n=0
  while [ "$n" -lt 20 ]; do
    [ -d "$APPDIR" ] || break
    grep -q 'errorText\|failed' "$RLOG" 2>/dev/null && break
    sleep 1; n=$((n + 1))
  done
  kill "$rpid" 2>/dev/null
  rm -rf "$APPDIR" "$PKGDIR" 2>/dev/null
  rm -f "$RLOG"
  echo "removed $ID"
  exit 0
fi

[ -f "$SRC/appinfo.json" ] || { echo "app files not found in $SRC"; exit 1; }
command -v luna-send >/dev/null 2>&1 || { echo "no luna-send"; exit 1; }

WORK=$(mktemp -d /tmp/app-pkg.XXXXXX) || exit 1
trap 'rm -rf "$WORK"' EXIT

APP="$WORK/data/usr/palm/applications/$ID"
PKG="$WORK/data/usr/palm/packages/$ID"
mkdir -p "$APP/assets" "$PKG"
cp "$SRC/appinfo.json" "$SRC/index.html" "$APP/" || exit 1
cp "$SRC/packageinfo.json" "$PKG/" || exit 1
cp "$SRC/assets/icon80.png" "$SRC/assets/icon130.png" "$APP/assets/" 2>/dev/null

printf '2.0\n' > "$WORK/debian-binary"
cat > "$WORK/control" <<CTRL
Package: $ID
Version: $VER
Architecture: all
Maintainer: lukemulvaney
Description: $TITLE
CTRL

( cd "$WORK" && tar -cf control.tar ./control && gzip -nf control.tar )
( cd "$WORK/data" && tar -cf ../data.tar ./usr && gzip -nf ../data.tar )

IPK="$WORK/${ID}_${VER}_all.ipk"
printf '!<arch>\n' > "$IPK"
ar_add() {
  f="$WORK/$1"; sz=$(wc -c < "$f")
  printf '%-16s%-12d%-6d%-6d%-8s%-10d`\n' "$1" 0 0 0 100644 "$sz" >> "$IPK"
  cat "$f" >> "$IPK"
  [ $((sz % 2)) -eq 1 ] && printf '\n' >> "$IPK"
  return 0
}
ar_add debian-binary
ar_add control.tar.gz
ar_add data.tar.gz

LOG="$WORK/install.log"
luna-send -i -w 60000 luna://com.webos.appInstallService/dev/install \
  "{\"id\":\"$ID\",\"ipkUrl\":\"$IPK\",\"subscribe\":true}" > "$LOG" 2>&1 &
lpid=$!
n=0
while [ "$n" -lt 25 ]; do
  grep -q '"state":"installed"' "$LOG" 2>/dev/null && break
  grep -q 'errorText\|install failed' "$LOG" 2>/dev/null && break
  sleep 1; n=$((n + 1))
done
kill "$lpid" 2>/dev/null

if grep -q '"state":"installed"' "$LOG" 2>/dev/null; then
  echo "installed OK: $ID"
else
  echo "INSTALL FAILED:"; cat "$LOG"
  exit 1
fi

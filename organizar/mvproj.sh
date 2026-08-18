D="$HOME/Desktop"; P="$HOME/.claude/projects"
setopt null_glob 2>/dev/null || shopt -s nullglob 2>/dev/null || true
enc(){ printf '%s' "$1" | sed 's/[\/_.]/-/g'; }
mvproj(){
  src="$1"; dst="$2"
  [ -e "$D/$src" ] || { echo "SKIP (no existe): $src"; return 0; }
  [ -e "$D/$dst" ] && { echo "SKIP (destino ocupado): $dst"; return 0; }
  mkdir -p "$(dirname "$D/$dst")"
  mv "$D/$src" "$D/$dst" || { echo "FALLO mv: $src"; return 1; }
  o=$(enc "$D/$src"); n=$(enc "$D/$dst"); moved=0
  for d in "$P/$o" "$P/$o"-*; do
    [ -d "$d" ] || continue
    b=$(basename "$d"); s="${b#"$o"}"
    [ -e "$P/$n$s" ] && { echo "  ! colisión: $n$s"; continue; }
    mv "$d" "$P/$n$s" && moved=$((moved+1))
  done
  echo "OK  $src → $dst   (sesiones renombradas: $moved)"
}

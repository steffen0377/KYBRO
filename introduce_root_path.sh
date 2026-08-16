#!/bin/bash
# Fuehrt ROOT_PATH als zentrale, absolute Pfad-Konstante ein und ersetzt
# damit die fehleranfaelligen relativen Includes (__DIR__ . '/../../includes/...')
# in modules/*/*.php und admin/*.php.
#
# Idempotent: kann gefahrlos mehrfach ausgefuehrt werden.
set -e
if [ ! -f "config/config.php" ]; then
    echo "FEHLER: Bitte aus dem KYBRO-Projekt-Root ausfuehren (dort wo config/config.php liegt)."
    exit 1
fi

# ---------- 1) ROOT_PATH in config/config.php ergaenzen ----------
if grep -qE "define\([\"']ROOT_PATH[\"']" config/config.php; then
    echo "ROOT_PATH ist in config/config.php bereits definiert - ueberspringe."
else
    if ! head -1 config/config.php | grep -qE '^<\?php'; then
        echo "FEHLER: config/config.php beginnt nicht mit '<?php' in der ersten Zeile - bitte manuell ergaenzen."
        exit 1
    fi
    cp config/config.php config/config.php.bak
    # Direkt nach Zeile 1 (die "<?php"-Zeile) einfuegen, Rest der Datei unangetastet
    awk '
        NR==1 {
            print
            print ""
            print "// Absoluter Projekt-Root, unabhaengig von der Verzeichnistiefe der"
            print "// aufrufenden Datei nutzbar (z.B. modules/stammdaten/kunden.php)."
            print "// config.php liegt fest in config/, daher hier verankert."
            print "define(\"ROOT_PATH\", dirname(__DIR__));"
            next
        }
        { print }
    ' config/config.php.bak > config/config.php
    echo "ROOT_PATH in config/config.php ergaenzt (Backup: config/config.php.bak)."
fi

# ---------- 2) Includes in modules/*/*.php auf ROOT_PATH umstellen ----------
# (liegen 2 Ebenen unter Root, aktuell z.B. __DIR__ . '/../../includes/...')
changed=0
while IFS= read -r -d '' file; do
    if grep -qE "__DIR__ \. '/\.\./\.\./(includes|vendor)/" "$file"; then
        cp "$file" "$file.bak"
        sed -i -E "s#__DIR__ \. '/\.\./\.\./(includes|vendor)/#ROOT_PATH . '/\1/#g" "$file"
        echo "Korrigiert (modules/): $file"
        changed=$((changed+1))
    fi
done < <(find modules -type f -name '*.php' -print0 2>/dev/null)

# ---------- 3) Includes in admin/*.php auf ROOT_PATH umstellen ----------
# (liegen 1 Ebene unter Root, aktuell __DIR__ . '/../includes/...')
if [ -d "admin" ]; then
    while IFS= read -r -d '' file; do
        if grep -qE "__DIR__ \. '/\.\./(includes|vendor)/" "$file"; then
            cp "$file" "$file.bak"
            sed -i -E "s#__DIR__ \. '/\.\./(includes|vendor)/#ROOT_PATH . '/\1/#g" "$file"
            echo "Korrigiert (admin/): $file"
            changed=$((changed+1))
        fi
    done < <(find admin -maxdepth 1 -type f -name '*.php' -print0 2>/dev/null)
fi

# ---------- 4) Root-Ebene (index.php, login.php, logout.php) fuer Konsistenz ----------
# (liegen direkt im Root, aktuell __DIR__ . '/includes/...' ohne ../)
for file in index.php login.php logout.php; do
    if [ -f "$file" ] && grep -qE "__DIR__ \. '/(includes|vendor)/" "$file"; then
        cp "$file" "$file.bak"
        sed -i -E "s#__DIR__ \. '/(includes|vendor)/#ROOT_PATH . '/\1/#g" "$file"
        echo "Korrigiert (Root): $file"
        changed=$((changed+1))
    fi
done

echo ""
echo "Fertig. $changed Datei(en) angepasst."
echo ""
echo "Hinweis: includes/db.php bindet config/config.php weiterhin relativ ein"
echo "(__DIR__ . '/../config/config.php') - das ist bewusst so belassen, da"
echo "ROOT_PATH erst DURCH das Laden von config.php definiert wird (Henne-Ei)."
echo "Dieser eine relative Pfad ist stabil, da includes/ nie verschachtelt wird."
echo ""
echo "Zur Kontrolle:"
grep -rln "ROOT_PATH" --include='*.php' . 2>/dev/null | grep -v '\.bak$' || true

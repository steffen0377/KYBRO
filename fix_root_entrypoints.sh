#!/bin/bash
# Korrigiert einen Fehler aus introduce_root_path.sh: index.php, login.php
# und logout.php sind der EINSTIEGSPUNKT der Anwendung und muessen
# includes/... laden, BEVOR config.php (und damit ROOT_PATH) ueberhaupt
# geladen wurde. ROOT_PATH dort zu verwenden fuehrt zu "Undefined constant".
# Diese drei Dateien muessen bei relativen Pfaden (__DIR__ . '/includes/...')
# bleiben - das ist hier korrekt, kein Bug.
set -e
if [ ! -f "config/config.php" ]; then
    echo "FEHLER: Bitte aus dem KYBRO-Projekt-Root ausfuehren."
    exit 1
fi

changed=0
for file in index.php login.php logout.php; do
    if [ -f "$file" ] && grep -qE "ROOT_PATH \. '/(includes|vendor)/" "$file"; then
        cp "$file" "$file.bak2"
        sed -i -E "s#ROOT_PATH \. '/(includes|vendor)/#__DIR__ . '/\1/#g" "$file"
        echo "Zurueckgesetzt (Root-Einstiegspunkt): $file"
        changed=$((changed+1))
    fi
done

echo ""
echo "Fertig. $changed Datei(en) korrigiert."
echo ""
echo "Zur Kontrolle:"
for file in index.php login.php logout.php; do
    [ -f "$file" ] && echo "--- $file ---" && cat "$file"
done

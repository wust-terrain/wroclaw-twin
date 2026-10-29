#!/usr/bin/env bash
# Task 04r: start JOSM for the pilot editors with the OSM API blocked (File > Update data / Download are disabled).
# Usage: scripts/josm_pilot.sh [zone_XX_edit.osm ...]      (JOSM_JAR overrides the jar, default ~/tools/josm-tested.jar)
# Tested with JOSM 19613 and OpenJDK 21. The three --add-exports flags are needed on Java 21, otherwise JOSM shows a
# "may work improperly" dialog. Nothing is downloaded by this script.
set -euo pipefail

JOSM_JAR="${JOSM_JAR:-$HOME/tools/josm-tested.jar}"
[ -f "$JOSM_JAR" ] || { echo "JOSM jar not found: $JOSM_JAR (set JOSM_JAR)" >&2; exit 1; }

exec java \
  --add-exports=java.base/sun.security.action=ALL-UNNAMED \
  --add-exports=java.desktop/com.sun.imageio.plugins.jpeg=ALL-UNNAMED \
  --add-exports=java.desktop/com.sun.imageio.spi=ALL-UNNAMED \
  -jar "$JOSM_JAR" --offline=osm_api "$@"

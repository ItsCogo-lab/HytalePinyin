#!/usr/bin/env bash
# Builds the mod's JAR with plain javac (no Maven needed). The name carries
# the mod version and the game version it is for, both from manifest.json
# ("Version" and "ServerVersion"): HytalePinyin-v0.1.0-Hytale-0.7.1.jar.
# Usage: build.sh JDK25_HOME PATH/TO/HytaleServer.jar
set -euo pipefail
JDK=$1; SERVER_JAR=$2
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(mktemp -d); trap 'rm -rf "$OUT"' EXIT
VERSION=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['Version'])" "$HERE/manifest.json")
GAME=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['ServerVersion'].lstrip('>=~^ '))" "$HERE/manifest.json")
JAR="$HERE/HytalePinyin-v$VERSION-Hytale-$GAME.jar"
"$JDK/bin/javac" --release 25 -encoding UTF-8 -cp "$SERVER_JAR" -d "$OUT" $(find "$HERE/src" -name '*.java')
cp -r "$HERE/resources/." "$OUT/"
cp "$HERE/manifest.json" "$OUT/"
cp "$HERE/../LICENSE" "$HERE/../NOTICE.md" "$HERE/../client-patch/FONTS-LICENSE.txt" "$OUT/"
rm -f "$HERE"/HytalePinyin*.jar
"$JDK/bin/jar" --create --file "$JAR" -C "$OUT" .
echo "built $JAR"

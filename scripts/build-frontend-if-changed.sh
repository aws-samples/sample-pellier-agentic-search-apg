#!/usr/bin/env bash
# Build the Storefront and Operator bundle before Pellier starts, unless the last build is current.
#
# The pellier unit runs this before every start. A Vite build takes about 13 s, and no lab edits
# the frontend, so building on every restart only made each restart that much slower. After a
# build this script records the base path it built for. The next start skips the build when the
# bundle is still the one it recorded (no build since, by this script or any other), the base path
# is the same, and nothing the build reads changed since. Anything else builds.
#
# Usage: build-frontend-if-changed.sh FRONTEND_DIR   (reads VITE_BASE_PATH, as the build does)
set -uo pipefail

FRONTEND="${1:?usage: build-frontend-if-changed.sh FRONTEND_DIR}"
cd "$FRONTEND" || exit 1
# Outside dist/, which the backend serves file by file; npm ci removes it with node_modules.
STAMP=node_modules/.pellier-frontend-build
BASE_PATH="${VITE_BASE_PATH:-/}"
INPUTS=(src public index.html package.json package-lock.json vite.config.ts tailwind.config.js
        postcss.config.js tsconfig.json tsconfig.build.json .env .env.production)

why_build() {
    [[ -f $STAMP ]] || { echo "no build recorded"; return; }
    [[ -f dist/index.html ]] || { echo "dist/index.html is missing"; return; }
    [[ dist/index.html -nt $STAMP ]] && { echo "dist/ was rebuilt by another command"; return; }
    [[ "$(cat "$STAMP")" == "$BASE_PATH" ]] || { echo "the base path is now $BASE_PATH"; return; }
    local present=() path changed
    for path in "${INPUTS[@]}"; do [[ -e $path ]] && present+=("$path"); done
    (( ${#present[@]} )) || { echo "none of the build's inputs were found"; return; }
    changed=$(find "${present[@]}" -newer "$STAMP" -print -quit)
    [[ -z $changed ]] || echo "$changed changed"
}

reason=$(why_build)
if [[ -z $reason ]]; then
    echo "frontend: the bundle in dist/ is current for $BASE_PATH; build skipped"
    exit 0
fi
echo "frontend: building ($reason)"
rm -f "$STAMP"
npm run build || exit $?
mkdir -p "$(dirname "$STAMP")"
printf '%s' "$BASE_PATH" > "$STAMP"

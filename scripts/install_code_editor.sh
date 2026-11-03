#!/usr/bin/env bash
# Install the Code Editor release in code-editor-release.env, keeping an event running.
#
# Plan A: the vendor's download of that release. Plan B: the copy under the workshop
# assets' code-editor/ prefix. Either copy must match the release's sha256, and the vendor
# installer then installs from that local file, so it cannot fetch anything else. Plan C,
# only when neither copy is usable: the vendor installer's latest release, which it checks
# itself. The box still comes up, on an editor no test event ran, and the last line says so.
#
# Needs CodeEditorUser; reads ASSETS_BUCKET_NAME and ASSETS_BUCKET_PREFIX when set.
# Prints the plan on its last line: "pinned download", "assets copy" or "latest <version>".
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${CODE_EDITOR_RELEASE_FILE:-$here/code-editor-release.env}"
vendor_url="https://code-editor.amazonaws.com/content/code-editor-server/dist"
vendor="${CODE_EDITOR_VENDOR_URL:-$vendor_url}"
home_dir="${CODE_EDITOR_HOME:-/home/${CodeEditorUser:?CodeEditorUser must be set}}"
version="v${CODE_EDITOR_RELEASE}"
dist="code-editor-server-${version}-${CODE_EDITOR_BUILD}-linux-arm64.tar.gz"
assets=""
if [ -n "${ASSETS_BUCKET_NAME:-}" ]; then
    assets="s3://${ASSETS_BUCKET_NAME}/${ASSETS_BUCKET_PREFIX:-}code-editor"
fi
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/mirror/$version"
archive="$work/mirror/$version/$dist"

note() { echo "install_code_editor: $*" >&2; }

matches() {  # matches <sha256> <file>
    local actual
    if command -v sha256sum >/dev/null 2>&1; then
        actual="$(sha256sum "$2" | cut -d' ' -f1)"
    else
        actual="$(shasum -a 256 "$2" | cut -d' ' -f1)"
    fi
    [ "$actual" = "$1" ]
}

from_assets() {  # from_assets <name> <destination>
    [ -n "$assets" ] && aws s3 cp --only-show-errors "$assets/$1" "$2" >&2
}

plan=""
if curl -fsSL --retry 3 "$vendor/$version/$dist" -o "$archive" \
        && matches "$CODE_EDITOR_ARCHIVE_SHA256" "$archive"; then
    plan="pinned download"
elif from_assets "$dist" "$archive" && matches "$CODE_EDITOR_ARCHIVE_SHA256" "$archive"; then
    plan="assets copy"
fi

installer="$work/install.sh"
if ! curl -fsSL --retry 3 "$vendor/aws-workshop-studio/install.sh" -o "$installer" \
        && ! from_assets install.sh "$installer"; then
    note "no installer from the vendor or the workshop assets"
    exit 1
fi
matches "$CODE_EDITOR_INSTALLER_SHA256" "$installer" \
    || note "WARNING: the vendor installer changed; review it and update its sha256"

if [ -n "$plan" ]; then
    local_base="CODEEDITOR_CLOUDFRONT_BASE_URL=\"file://$work/mirror\""
    sed "s#^CODEEDITOR_CLOUDFRONT_BASE_URL=.*#$local_base#" "$installer" > "$work/local.sh"
    if grep -qxF "$local_base" "$work/local.sh"; then
        CODE_EDITOR_VERSION="$version" CODE_EDITOR_DISTRIBUTION_VERSION="$dist" \
            bash "$work/local.sh" >&2
        product="$home_dir/.local/lib/code-editor-${version}-linux-arm64/dist/product.json"
        installed="$(jq -r .version "$product" 2>/dev/null || true)"
        if [ "$installed" != "$CODE_EDITOR_RELEASE" ]; then
            note "installed '${installed:-nothing}', expected $CODE_EDITOR_RELEASE"
            exit 1
        fi
        echo "$plan"
        exit 0
    fi
    note "WARNING: the installer no longer names its download URL; using plan C"
fi

note "WARNING: Code Editor $CODE_EDITOR_RELEASE is not available from the vendor or the" \
     "workshop assets; installing the vendor's latest release, which no test event ran"
env -u CODE_EDITOR_VERSION -u CODE_EDITOR_DISTRIBUTION_VERSION bash "$installer" >&2
newest="$(ls -d "$home_dir"/.local/lib/code-editor-v*-linux-* 2>/dev/null | tail -1)"
echo "latest $(jq -r .version "$newest/dist/product.json" 2>/dev/null || echo unknown)"

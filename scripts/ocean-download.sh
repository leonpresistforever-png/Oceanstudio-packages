#!/usr/bin/env bash
# Ocean source downloader. Every source, mirror and reused cache must match the
# official upstream SHA256 supplied by the recipe; no unchecked mode exists.
ocean_download() {
    if [[ $# != 3 || ! "$3" =~ ^[0-9a-fA-F]{64}$ ]]; then
        echo 'ocean_download: expected <HTTPS_URL[|MIRROR...]> <DESTINATION> <SHA256>' >&2
        return 1
    fi
    local url_spec="$1" destination="$2" checksum="${3,,}"
    local cache="${OCEAN_PKG_TMPDIR:-${TMPDIR:-/tmp}/ocean-source-downloads}"
    local url partial attempt actual
    local -a urls
    mkdir -p "$cache" "$(dirname "$destination")" || return 1
    if [[ -f "$destination" ]]; then
        read -r actual _ < <(sha256sum "$destination")
        [[ "$actual" == "$checksum" ]] && return 0
    fi
    partial="$cache/.partial-$checksum"
    IFS='|' read -r -a urls <<< "$url_spec"
    for url in "${urls[@]}"; do
        if [[ "$url" == file:///* ]]; then
            # Local verified source archives are useful for offline builds.
            [[ -f "${url:7}" ]] || continue
            cp -- "${url:7}" "$partial" || continue
            read -r actual _ < <(sha256sum "$partial")
            if [[ "$actual" == "$checksum" ]]; then
                mv -f -- "$partial" "$destination" && return 0
            fi
            rm -f -- "$partial"
            continue
        fi
        [[ "$url" == https://* ]] || { echo "Source must use HTTPS: $url" >&2; continue; }
        for attempt in 1 2; do
            # A transport failure OR a successful but corrupt resumed response
            # gets a clean restart before trying the next verified mirror.
            if curl --fail --location --proto '=https' --proto-redir '=https' \
                --continue-at - --retry 3 --retry-all-errors --retry-connrefused \
                --retry-max-time 600 --connect-timeout 30 --max-time 1200 \
                --speed-limit 1024 --speed-time 90 --output "$partial" "$url"; then
                read -r actual _ < <(sha256sum "$partial")
                if [[ "$actual" == "$checksum" ]]; then
                    mv -f -- "$partial" "$destination" && return 0
                fi
                echo "Checksum rejected source candidate; retrying clean: $url" >&2
            fi
            rm -f -- "$partial"
        done
    done
    echo 'No source candidate passed SHA256 verification.' >&2
    return 1
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then ocean_download "$@"; fi

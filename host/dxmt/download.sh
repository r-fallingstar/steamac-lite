#!/usr/bin/env bash
fetch_file() { # url sha256 dest; failed/interrupted downloads retain their .part file
    local url=$1 digest=$2 dest=$3
    if [[ ! -f $dest ]]; then
        mkdir -p "$(dirname "$dest")"
        echo "Downloading $(basename "$dest") (partial downloads resume on retry)" >&2
        # No silent mode: curl displays progress as well as failures. Never replace a
        # completed cache entry until both transfer and checksum have succeeded.
        curl --fail --location --retry 3 --continue-at - --output "$dest.part" "$url" || return 1
        echo "$digest  $dest.part" | shasum -a 256 -c - >/dev/null || {
            echo "checksum mismatch: $dest.part (remove this partial file to retry from the start)" >&2
            return 1
        }
        mv "$dest.part" "$dest"
    fi
    echo "$digest  $dest" | shasum -a 256 -c - >/dev/null || {
        echo "checksum mismatch: $dest (remove this cache file to re-download)" >&2
        return 1
    }
}

FROM debian:trixie@sha256:9cc080028c43b27d2074d63a5f9caf7166d731494965616c1a6d2827a004585c
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends bc bison build-essential ca-certificates file flex kmod libelf-dev libssl-dev patch python3 xz-utils gcc-mingw-w64-x86-64-posix && rm -rf /var/lib/apt/lists/*

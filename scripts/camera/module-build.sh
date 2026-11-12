#!/bin/sh
set -eu
src=/build/linux-7.2.9
obj=/build/obj
if [ ! -f "$src/.camera-patched" ]; then
 tar -C /build -xf /input/linux-7.2.9.tar.xz
 for p in /patches/*.patch; do patch -d "$src" -p1 -F0 < "$p"; done
 touch "$src/.camera-patched"
fi
mkdir -p "$obj"
cp /input/kernel.config "$obj/.config"
make -C "$src" O="$obj" ARCH=arm64 olddefconfig
make -C "$src" O="$obj" ARCH=arm64 -j2 modules_prepare
! grep -q '^CONFIG_MODVERSIONS=y' "$obj/.config"
cp -a /loopback /build/loopback
make -C "$src" O="$obj" ARCH=arm64 M=/build/loopback KBUILD_MODPOST_WARN=1 -j2 modules
cp /build/loopback/v4l2loopback.ko /out/
cp "$obj/include/config/kernel.release" /out/kernel.release
cp "$obj/.config" /out/module-kernel.config
modinfo /out/v4l2loopback.ko

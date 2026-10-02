#!/bin/bash
#
# extract-files.sh — 从魅族21 9008 全分区备份重新提取内核设备树
# 用法: ./extract-files.sh <images目录>   (含 boot_a.img vendor_boot_a.img dtbo_a.img super.img)
#
# 依赖(相对本脚本 ../tools): lpunpack.exe extract.erofs.exe 7z.exe
#       _mkbootimg/unpack_bootimg.py  _extract_dtb/extract_dtb/extract_dtb.py
#       python3 + pip lz4 (lz4_legacy_dec.py)   python3 + extract_dtb
# Git Bash / WSL 均可运行。

set -e

MY_DIR="${BASH_SOURCE%/*}"
SRC="${1:?用法: $0 <9008镜像目录>}"
SRC="${SRC%/}"
TOOLS="${MY_DIR}/../tools"
KERNEL_VER="6.1.25-android14-11-maybe-dirty"
LZ4DEC="${MY_DIR}/../tools/lz4_legacy_dec.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -f "${MY_DIR}/Module.symvers" ] || touch "${MY_DIR}/Module.symvers"
[ -f "${MY_DIR}/System.map" ]     || touch "${MY_DIR}/System.map"

echo "== 1. boot_a.img -> kernel"
python3 "${TOOLS}/_mkbootimg/unpack_bootimg.py" --boot_img "${SRC}/boot_a.img" --out "${TMP}/boot" | tee "${MY_DIR}/extras/boot-header.txt"
cp -f "${TMP}/boot/kernel" "${MY_DIR}/kernel"

echo "== 2. vendor_boot_a.img -> dtb + vendor_ramdisk00"
python3 "${TOOLS}/_mkbootimg/unpack_bootimg.py" --boot_img "${SRC}/vendor_boot_a.img" --out "${TMP}/vboot" | tee "${MY_DIR}/extras/vendor_boot-header.txt"
cp -f "${TMP}/vboot/bootconfig" "${MY_DIR}/extras/vendor_boot-bootconfig.txt"

echo "== 3. 拆分 dtb"
rm -rf "${MY_DIR}/dtb"; mkdir -p "${MY_DIR}/dtb"
python3 "${TOOLS}/_extract_dtb/extract_dtb/extract_dtb.py" "${TMP}/vboot/dtb" -o "${TMP}/dtb_split" >/dev/null
find "${TMP}/dtb_split" -type f -name '*.dtb' -exec cp {} "${MY_DIR}/dtb/" \;

echo "== 4. dtbo_a.img"
cp -f "${SRC}/dtbo_a.img" "${MY_DIR}/dtbo.img"

echo "== 5. vendor_ramdisk00 (LZ4 legacy -> cpio -> 7z)"
python3 "${LZ4DEC}" "${TMP}/vboot/vendor_ramdisk00" "${TMP}/vramdisk.cpio"
rm -rf "${MY_DIR}/vendor_ramdisk"; mkdir -p "${MY_DIR}/vendor_ramdisk"
"${TOOLS}/7z.exe" x "${TMP}/vramdisk.cpio" -o"${TMP}/vramdisk" >/dev/null
cp -f "${TMP}/vramdisk/lib/modules/"* "${MY_DIR}/vendor_ramdisk/"
mkdir -p "${MY_DIR}/extras"
cp -f "${TMP}/vramdisk/first_stage_ramdisk/fstab.qcom" "${MY_DIR}/extras/" 2>/dev/null || true

echo "== 6. super.img -> lpunpack -> EROFS 解包"
"${TOOLS}/lpunpack.exe" "${SRC}/super.img" "${TMP}/super_out"
for P in vendor_dlkm_a system_dlkm_a; do
    "${TOOLS}/extract.erofs.exe" -i "${TMP}/super_out/${P}.img" -x -f -o"${TMP}/${P}" -T8
done

echo "== 7. vendor_dlkm"
rm -rf "${MY_DIR}/vendor_dlkm"; mkdir -p "${MY_DIR}/vendor_dlkm"
cp -f "${TMP}/vendor_dlkm_a/vendor_dlkm_a/lib/modules/"* "${MY_DIR}/vendor_dlkm/"

echo "== 8. system_dlkm (版本目录 ${KERNEL_VER})"
rm -rf "${MY_DIR}/system_dlkm"; mkdir -p "${MY_DIR}/system_dlkm"
cp -rf "${TMP}/system_dlkm_a/system_dlkm_a/lib/modules/${KERNEL_VER}/." "${MY_DIR}/system_dlkm/"

echo "完成。产物位于 ${MY_DIR}"

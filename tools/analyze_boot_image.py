#!/usr/bin/env python3
"""解析 Android boot 镜像(v4)头 + AVB footer/vbmeta, 用来对比"能启动 vs 进 fastboot"。

用法: python tools/analyze_boot_image.py <boot.img> [<boot.img> ...]
"""
import hashlib
import struct
import sys

BOOT_MAGIC = b"ANDROID!"
AVB_MAGIC = b"AVB0"
VBMETA_MAGIC = b"AVB0"

ALGO = {0: "NONE", 1: "SHA256_RSA2048", 2: "SHA256_RSA4096", 3: "SHA256_RSA8192",
        4: "SHA512_RSA2048", 5: "SHA512_RSA4096", 6: "SHA512_RSA8192"}


def decode_os_version(v):
    if v == 0:
        return "0 (未设置 → mkbootimg 没传 --os_version/--os_patch_level)"
    major = (v >> 25) & 0x7F
    minor = (v >> 18) & 0x7F
    patch = (v >> 11) & 0x7F
    year = ((v >> 4) & 0x7F) + 2000
    month = v & 0xF
    return f"{major}.{minor}.{patch} / {year}-{month:02d}  (raw=0x{v:08x})"


def parse_boot_header(data):
    if data[:8] != BOOT_MAGIC:
        return None
    (kernel_size, ramdisk_size, os_version, header_size) = struct.unpack_from("<4I", data, 8)
    header_version = struct.unpack_from("<I", data, 40)[0]
    cmdline = data[44:44 + 1536].split(b"\x00")[0].decode("utf-8", "replace")
    page_size = 0
    if header_version == 0:
        page_size = struct.unpack_from("<I", data, 36)[0]
    out = {
        "header_version": header_version,
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "os_version": decode_os_version(os_version),
        "header_size": header_size,
        "cmdline": cmdline,
        "page_size": page_size,
    }
    if header_version >= 4:
        out["signature_size"] = struct.unpack_from("<I", data, 44 + 1536)[0]
    # 头之后紧跟的 kernel 数据
    kern_off = header_size
    out["kernel_offset"] = kern_off
    out["kernel_sha256"] = hashlib.sha256(data[kern_off:kern_off + kernel_size]).hexdigest()
    return out


def parse_avb(data):
    res = {}
    pos = data.find(AVB_MAGIC)
    offs = []
    while pos >= 0:
        offs.append(pos)
        pos = data.find(AVB_MAGIC, pos + 1)
        if len(offs) > 8:
            break
    res["avb_magic_offsets"] = offs
    # AvbFooter 固定在镜像最后 64 字节
    if len(data) >= 64 and data[-64:-60] == AVB_MAGIC:
        f = struct.unpack_from("<4sIQQQ28s", data, len(data) - 64)
        vbmeta_off, vbmeta_size = f[3], f[4]
        res["footer"] = {
            "version": f[1],
            "original_image_size": f[2],
            "vbmeta_offset": vbmeta_off,
            "vbmeta_size": vbmeta_size,
        }
        blob = data[vbmeta_off:vbmeta_off + vbmeta_size]
        if blob[:4] == VBMETA_MAGIC:
            # AvbVBMetaHeader(256B): magic, required_version(4), auth_block_size(4),
            # auxiliary_block_size(4), algorithm_type(4), hash_offset/size(8+8),
            # signature_offset/size(8+8), public_key_offset/size(8+8), ...
            (magic, req_ver, auth_size, aux_size, algo_type) = struct.unpack_from("<4sIIII", blob, 0)
            (hash_off, hash_size, sig_off, sig_size, pk_off, pk_size) = struct.unpack_from("<6Q", blob, 24)
            rollback = struct.unpack_from("<Q", blob, 24 + 48 + 16 + 8)[0] if len(blob) > 96 else -1
            res["vbmeta"] = {
                "required_version": req_ver,
                "auth_block_size": auth_size,
                "algorithm": ALGO.get(algo_type, f"unknown({algo_type})"),
                "hash_size": hash_size,
                "signature_size": sig_size,
                "public_key_size": pk_size,
                "public_key_sha1": hashlib.sha1(blob[pk_off:pk_off + pk_size]).hexdigest() if pk_size else "",
            }
            # 校验: 对 original_image_size 的哈希是否等于 vbmeta 里的 hash
            ois = f[2]
            calc = hashlib.sha256(data[:ois]).digest()
            stored = blob[hash_off:hash_off + hash_size]
            res["hash_of_payload_matches"] = (calc == stored)
            res["stored_hash"] = stored.hex()[:32] + "…"
            res["calc_hash"] = calc.hex()[:32] + "…"
    return res


def main(paths):
    for p in paths:
        data = open(p, "rb").read()
        print("=" * 100)
        print(f"文件: {p}")
        print(f"大小: {len(data)} 字节  ({len(data)/1048576:.2f} MiB)")
        print(f"SHA256: {hashlib.sha256(data).hexdigest()}")
        hdr = parse_boot_header(data)
        if not hdr:
            print("  ❌ 没有 ANDROID! 魔数(不是 boot 镜像?)")
            continue
        print(f"  header_version : {hdr['header_version']}")
        print(f"  kernel_size    : {hdr['kernel_size']}  ({hdr['kernel_size']/1048576:.2f} MiB)")
        print(f"  ramdisk_size   : {hdr['ramdisk_size']}")
        print(f"  os_version     : {hdr['os_version']}")
        print(f"  header_size    : {hdr['header_size']}  (page_size={hdr['page_size']})")
        print(f"  cmdline        : {hdr['cmdline']!r}")
        if "signature_size" in hdr:
            print(f"  signature_size : {hdr['signature_size']}")
        print(f"  kernel sha256  : {hdr['kernel_sha256']}")
        avb = parse_avb(data)
        print(f"  AVB0 魔数偏移  : {[hex(o) for o in avb['avb_magic_offsets']] or '无'}")
        if "footer" in avb:
            f = avb["footer"]
            print(f"  AVB footer     : version={f['version']} original_image_size={f['original_image_size']}"
                  f" ({f['original_image_size']/1048576:.2f} MiB) vbmeta@{f['vbmeta_offset']} size={f['vbmeta_size']}")
            v = avb.get("vbmeta")
            if v:
                print(f"    vbmeta       : required_version={v['required_version']} algorithm={v['algorithm']}")
                print(f"    pubkey sha1  : {v['public_key_sha1']}")
                print(f"    payload hash : 存储={avb['stored_hash']} 计算={avb['calc_hash']}"
                      f"  → {'一致 ✅' if avb['hash_of_payload_matches'] else '不一致 ❌(AVB 校验会失败)'}")
        else:
            print("  AVB footer     : 无(镜像未签名)")
        # 尾部填充情况
        payload_end = (hdr["kernel_offset"] + hdr["kernel_size"] + hdr["ramdisk_size"])
        if "signature_size" in hdr:
            payload_end += hdr["signature_size"]
        tail = data[payload_end:]
        nz = sum(1 for b in tail[:4096] if b)
        print(f"  有效载荷结束于 : {payload_end} ({payload_end/1048576:.2f} MiB)，之后 {len(tail)} 字节"
              f"（前 4KB 非零字节 {nz}）")


if __name__ == "__main__":
    main(sys.argv[1:])

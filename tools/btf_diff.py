#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从内核镜像/ELF 里扫描并解析 BTF, 用于对比"原厂内核 vs 我们的构建"的结构体布局。

CONFIG_DEBUG_INFO_BTF=y 时内核带 .BTF 段, 里面是完整的类型信息(结构体成员名/偏移/大小、
函数原型)。原厂内核镜像(Image)虽然没有 ELF 段表, 但 .BTF 是自描述数据(magic 0xeb9f),
可以直接在二进制里定位并解析 —— 于是我们能读出原厂内核真实的结构体定义,
再和我们的构建对比, 找出 CRC 差异的来源。

用法:
  python tools/btf_diff.py scan  <image>                 # 只报告 BTF 位置与统计
  python tools/btf_diff.py dump  <image> struct sock     # 打印某结构体成员与偏移
  python tools/btf_diff.py func  <image> scsi_execute    # 搜函数名
  python tools/btf_diff.py diff  <imageA> <imageB>       # 对比两份 BTF 的结构体差异
"""
import struct
import sys
from collections import OrderedDict

# BTF kinds
K_INT, K_PTR, K_ARRAY, K_STRUCT, K_UNION, K_ENUM, K_FWD, K_TYPEDEF, K_VOLATILE, \
    K_CONST, K_RESTRICT, K_FUNC, K_FUNC_PROTO, K_VAR, K_DATASEC, K_FLOAT, K_DECL_TAG, \
    K_TYPE_TAG, K_ENUM64 = range(1, 20)


def _find_btf_candidates(data):
    """列出所有可能的 BTF 头部位置。"""
    magic = b"\x9f\xeb\x01\x00"
    start = 0
    while True:
        i = data.find(magic, start)
        if i < 0:
            return
        if i + 24 <= len(data):
            version = data[i + 2]
            hdr_len = struct.unpack_from("<I", data, i + 4)[0]
            if version in (1, 2, 3) and hdr_len == 24:
                type_off, type_len, str_off, str_len = struct.unpack_from("<IIII", data, i + 8)
                if 0 < type_len < 64 * 1024 * 1024 and 0 < str_len < 32 * 1024 * 1024:
                    yield i, type_off, type_len, str_off, str_len
        start = i + 1


def find_btf(data, verbose=False):
    """在内核镜像里找 BTF, 用"字符串段以 0 开头 + 含已知符号名"来校验, 避免错位。"""
    best = None
    for cand in _find_btf_candidates(data):
        base, type_off, type_len, str_off, str_len = cand
        # 注意: BTF 头里的 type_off/str_off 是相对"头部末尾"(base + hdr_len)的偏移
        hdr_len = 24
        tstart = base + hdr_len + type_off
        sstart = base + hdr_len + str_off
        sb = data[sstart: sstart + str_len]
        ok_first = len(sb) > 0 and sb[0] == 0
        has_known = (b"list_head\x00" in sb) and (b"task_struct\x00" in sb)
        if verbose:
            print("   候选 base=%d type_off=%d type_len=%d str_off=%d str_len=%d 首字节0=%s 含list_head/task_struct=%s"
                  % (base, type_off, type_len, str_off, str_len, ok_first, has_known))
        if ok_first and has_known:
            return cand
        if best is None:
            best = cand          # 模块 .BTF 段字符串表很小, 校验可能不通过 -> 用第一个候选
    return best


class BTF:
    def __init__(self, data):
        found = find_btf(data)
        if not found:
            raise SystemExit("没找到 BTF(该镜像可能未开 CONFIG_DEBUG_INFO_BTF)")
        base, type_off, type_len, str_off, str_len = found
        self.base = base
        hdr_len = 24
        self.type_blob = data[base + hdr_len + type_off: base + hdr_len + type_off + type_len]
        self.str_blob = data[base + hdr_len + str_off: base + hdr_len + str_off + str_len]
        self.types = [None]  # 1-based
        self._parse()

    def s(self, off):
        if off == 0:
            return ""
        end = self.str_blob.find(b"\x00", off)
        return self.str_blob[off:end].decode("utf-8", "replace")

    def _parse(self):
        b = self.type_blob
        p = 0
        tid = 1
        while p < len(b):
            name_off, info, size = struct.unpack_from("<III", b, p)
            p += 12
            kind = (info >> 24) & 0x1F
            vlen = info & 0xFFFF
            kflag = (info >> 31) & 1
            t = {"id": tid, "name": self.s(name_off), "kind": kind, "vlen": vlen,
                 "size": size, "members": [], "type": size}
            if kind in (K_STRUCT, K_UNION):
                t["size"] = size
                for _ in range(vlen):
                    mo, mt, moff = struct.unpack_from("<III", b, p)
                    p += 12
                    if kflag:
                        bit_off = moff & 0xFFFFFF
                        bit_sz = moff >> 24
                    else:
                        bit_off = moff
                        bit_sz = 0
                    t["members"].append((self.s(mo), mt, bit_off, bit_sz))
            elif kind == K_INT:
                t["size"] = size
                t["encoding"] = struct.unpack_from("<I", b, p)[0]
                p += 4
            elif kind == K_ARRAY:
                t["elem_type"], t["index_type"], t["nelems"] = struct.unpack_from("<III", b, p)
                p += 12
            elif kind == K_ENUM:
                for _ in range(vlen):
                    no, val = struct.unpack_from("<Ii", b, p)
                    p += 8
                    t["members"].append((self.s(no), val))
            elif kind == K_ENUM64:
                for _ in range(vlen):
                    no, lo, hi = struct.unpack_from("<III", b, p)
                    p += 12
                    t["members"].append((self.s(no), (hi << 32) | lo))
            elif kind == K_FUNC_PROTO:
                t["ret_type"] = size
                t["params"] = []
                for _ in range(vlen):
                    no, pt = struct.unpack_from("<II", b, p)
                    p += 8
                    t["params"].append((self.s(no), pt))
            elif kind == K_VAR:
                t["type"] = struct.unpack_from("<I", b, p)[0]
                p += 4
            elif kind == K_DATASEC:
                p += 12 * vlen
            elif kind == K_DECL_TAG:
                p += 4          # 只有 DECL_TAG 有 4 字节 component_idx
            elif kind == K_TYPE_TAG:
                pass            # TYPE_TAG 没有附加数据(多消费会导致类型表整体错位)
            elif kind == K_FUNC:
                pass
            # K_PTR/K_TYPEDEF/K_CONST/K_VOLATILE/K_RESTRICT/K_FWD/K_FLOAT: 无附加数据
            self.types.append(t)
            tid += 1

    def tname(self, tid, depth=0):
        """把类型 id 解析成可读名字(处理 typedef/ptr/const/array)。"""
        if tid == 0:
            return "void"
        if depth > 12:
            return "..."
        t = self.types[tid] if 0 < tid < len(self.types) else None
        if t is None:
            return f"<{tid}>"
        k = t["kind"]
        if k == K_PTR:
            return self.tname(t["type"], depth + 1) + " *"
        if k in (K_CONST, K_VOLATILE, K_RESTRICT):
            return self.tname(t["type"], depth + 1)
        if k == K_TYPEDEF:
            return t["name"]
        if k == K_ARRAY:
            return "%s[%d]" % (self.tname(t["elem_type"], depth + 1), t["nelems"])
        if k in (K_STRUCT, K_UNION):
            return ("struct " if k == K_STRUCT else "union ") + (t["name"] or "<anon>")
        if k == K_FUNC_PROTO:
            return "proto"
        if k == K_INT:
            return t["name"]
        return t["name"] or f"kind{k}"

    def structs(self):
        return OrderedDict((t["name"], t) for t in self.types[1:]
                           if t and t["kind"] in (K_STRUCT, K_UNION) and t["name"])

    def funcs(self):
        out = OrderedDict()
        for t in self.types[1:]:
            if t and t["kind"] == K_FUNC and t["name"]:
                proto = self.types[t["type"]] if 0 < t["type"] < len(self.types) else None
                sig = ""
                if proto and proto["kind"] == K_FUNC_PROTO:
                    sig = "%s(%s)" % (self.tname(proto.get("ret_type", 0)),
                                      ", ".join("%s %s" % (self.tname(pt), pn or "")
                                                for pn, pt in proto.get("params", [])))
                out[t["name"]] = sig
        return out


def load(path):
    data = open(path, "rb").read()
    return data, BTF(data)


def cmd_scan(path):
    data, b = load(path)
    print(f"{path}: {len(data)} 字节, BTF 位于偏移 {b.base}, 类型 {len(b.types)-1} 个, 字符串 {len(b.str_blob)} 字节")
    st = b.structs()
    print(f"  有名字的结构体/联合体: {len(st)}")
    fn = b.funcs()
    print(f"  函数: {len(fn)}")


def cmd_dump(path, name):
    _, b = load(path)
    found = [t for t in b.types[1:] if t and t["name"] == name and t["kind"] in (K_STRUCT, K_UNION)]
    if not found:
        # 试试后缀匹配
        found = [t for t in b.types[1:] if t and t["name"].endswith(name) and t["kind"] in (K_STRUCT, K_UNION)]
    for t in found[:3]:
        print(f"== {t['name']}  size={t['size']} 成员 {len(t['members'])}")
        for mn, mt, boff, bsz in t["members"]:
            print(f"   +{boff//8:5d}.{boff%8}  {b.tname(mt):40s} {mn}")


def cmd_func(path, pat):
    _, b = load(path)
    fn = b.funcs()
    for k, v in fn.items():
        if pat in k:
            print(f"  {k}: {v}")


def cmd_diff(pa, pb):
    _, A = load(pa)
    _, B = load(pb)
    sa, sb = A.structs(), B.structs()
    only_a = sorted(set(sa) - set(sb))
    only_b = sorted(set(sb) - set(sa))
    print(f"A={pa}\nB={pb}")
    print(f"结构体: A={len(sa)} B={len(sb)}  只A有={len(only_a)} 只B有={len(only_b)}")
    changed = []
    for n in sorted(set(sa) & set(sb)):
        a, b = sa[n], sb[n]
        am = [(mn, boff // 8) for mn, mt, boff, bsz in a["members"]]
        bm = [(mn, boff // 8) for mn, mt, boff, bsz in b["members"]]
        if a["size"] != b["size"] or am != bm:
            changed.append(n)
    print(f"大小/成员偏移不同的结构体: {len(changed)}")
    for n in changed[:60]:
        a, b = sa[n], sb[n]
        am = {mn: (boff // 8) for mn, mt, boff, bsz in a["members"]}
        bm = {mn: (boff // 8) for mn, mt, boff, bsz in b["members"]}
        added = [m for m in bm if m not in am]
        removed = [m for m in am if m not in bm]
        moved = [m for m in am if m in bm and am[m] != bm[m]]
        print(f"\n  ## {n}: size {a['size']} -> {b['size']}")
        if added:
            print(f"     B 独有字段: {[(m, bm[m]) for m in added][:8]}")
        if removed:
            print(f"     A 独有字段: {[(m, am[m]) for m in removed][:8]}")
        if moved:
            print(f"     偏移变化: {[(m, am[m], bm[m]) for m in moved][:8]}")
    if only_b:
        print(f"\n  B 独有的结构体(前 30): {only_b[:30]}")


KEYS = [
    # 与 74 个 CRC 不一致符号直接相关的结构体
    "sock", "socket", "sockaddr", "msghdr", "proto_ops", "net", "net_device", "sk_buff",
    "file", "inode", "dentry", "path", "super_block", "address_space", "shmem_inode_info",
    "shrinker", "dma_buf", "dma_buf_attachment", "dma_buf_ops", "dma_buf_map",
    "drm_gem_object", "drm_device", "drm_driver", "drm_gem_object_funcs",
    "cgroup", "cgroup_subsys_state", "cftype", "css_set", "cgroup_subsys",
    "folio", "page", "vm_area_struct", "vm_fault", "mm_struct",
    "kernfs_node", "kernfs_ops", "block_device", "gendisk", "request_queue", "bio",
    "task_struct", "module", "device", "kobject", "class", "bus_type", "driver",
    "wait_queue_head", "wait_queue_entry", "timer_list", "work_struct",
    "seq_file", "proc_ops", "file_operations", "attribute", "bin_attribute",
    "clk_hw", "clk_ops", "regmap", "regulator_dev", "iommu_domain", "iommu_ops",
    "scsi_device", "scsi_host", "scsi_cmnd", "ufs_hba", "ufs_host",
    "mem_cgroup", "lruvec", "pglist_data", "zone", "zonelist",
]


def cmd_keydiff(pa, pb, filt=None):
    _, A = load(pa)
    _, B = load(pb)
    sa, sb = A.structs(), B.structs()
    keys = [k for k in KEYS if (filt is None or filt in k)]
    same = []
    for k in keys:
        a, b = sa.get(k), sb.get(k)
        if not a or not b:
            print(f"\n## {k}: 只在一侧存在 (A有={bool(a)} B有={bool(b)})")
            continue
        am = [(mn, boff // 8, A.tname(mt)) for mn, mt, boff, bsz in a["members"]]
        bm = [(mn, boff // 8, B.tname(mt)) for mn, mt, boff, bsz in b["members"]]
        if a["size"] == b["size"] and am == bm:
            same.append(k)
            continue
        print(f"\n===== {k}: size {a['size']} -> {b['size']}  (A=原厂, B=我们)")
        an = {m[0]: m for m in am}
        bn = {m[0]: m for m in bm}
        i = j = 0
        while i < len(am) or j < len(bm):
            if i < len(am) and j < len(bm) and am[i][0] == bm[j][0]:
                if am[i][1] != bm[j][1] or am[i][2] != bm[j][2]:
                    print(f"   ~ {am[i][0]:32s} off {am[i][1]:5d} -> {bm[j][1]:5d}   type {am[i][2]} -> {bm[j][2]}")
                i += 1; j += 1
            elif j < len(bm) and (i >= len(am) or am[i][0] not in bn):
                print(f"   + B独有: {bm[j][0]:28s} off {bm[j][1]:5d}  type {bm[j][2]}")
                j += 1
            elif i < len(am) and (j >= len(bm) or bm[j][0] not in an):
                print(f"   - A独有: {am[i][0]:28s} off {am[i][1]:5d}  type {am[i][2]}")
                i += 1
            else:
                i += 1; j += 1
    print(f"\n(完全一致的关键结构体 {len(same)} 个: {', '.join(same[:40])})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    c = sys.argv[1]
    if c == "scan":
        cmd_scan(sys.argv[2])
    elif c == "dump":
        cmd_dump(sys.argv[2], sys.argv[3])
    elif c == "func":
        cmd_func(sys.argv[2], sys.argv[3])
    elif c == "diff":
        cmd_diff(sys.argv[2], sys.argv[3])
    elif c == "keydiff":
        cmd_keydiff(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        print(__doc__)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从厂商模块自带的 BTF 里读出它调用的内核函数原型(extern FUNC)。

模块 BTF(CONFIG_DEBUG_INFO_BTF_MODULES=y)会记录模块用到的类型, 其中对内核函数的
调用表现为 BTF_FUNC + linkage=BTF_FUNC_EXTERN 的条目, 带有完整原型 —— 这正好能补上
"原厂内核 BTF 里查不到" 的私有函数签名(如 wait_spam_info, 它可能是汇编/无 BTF 条目)。

用法:
  python tools/module_btf_proto.py <目录或 .ko> <符号名...>
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_module_kmi import elf_sections, iter_kos                     # noqa: E402
import importlib.util                                                     # noqa: E402

_spec = importlib.util.spec_from_file_location("btf_diff", os.path.join(os.path.dirname(os.path.abspath(__file__)), "btf_diff.py"))
bd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bd)

BTF_FUNC_EXTERN = 2


def module_btf(data, secs):
    for s in secs:
        if s["sname"] == ".BTF":
            blob = data[s["offset"]:s["offset"] + s["size"]]
            return bd.BTF(blob) if False else _parse_blob(blob)
    return None


def _parse_blob(blob):
    """BTF 段自身就是完整的 BTF 数据(magic 开头), 直接交给解析器。"""
    return bd.BTF(blob)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    target, syms = sys.argv[1], sys.argv[2:]
    for ko in iter_kos([target]):
        data = open(ko, "rb").read()
        if data[:4] != b"\x7fELF":
            continue
        secs = elf_sections(data)
        if not any(s["sname"] == ".BTF" for s in secs):
            continue
        try:
            B = module_btf(data, secs)
        except SystemExit:
            continue                       # .BTF 为空/无效段, 跳过
        except Exception as exc:                                          # noqa: BLE001
            print("  %s: BTF 解析失败 %s" % (os.path.basename(ko), exc))
            continue
        if B is None:
            continue
        found = []
        allfuncs = []
        for t in B.types[1:]:
            if not t or t["kind"] != bd.K_FUNC or not t["name"]:
                continue
            allfuncs.append(t["name"])
            if t["name"] not in syms:
                continue
            proto = B.types[t["type"]] if 0 < t["type"] < len(B.types) else None
            sig = "?"
            if proto and proto["kind"] == bd.K_FUNC_PROTO:
                sig = "%s(%s)" % (B.tname(proto.get("ret_type", 0)),
                                  ", ".join("%s %s" % (B.tname(pt), pn or "")
                                            for pn, pt in proto.get("params", [])))
            linkage = "extern" if not hasattr(t, "linkage") else t["linkage"]
            found.append((t["name"], sig))
        if found:
            print("== %s (.BTF 存在)" % os.path.basename(ko))
            for name, sig in found:
                print("    %-32s %s" % (name, sig))
        elif allfuncs:
            print("== %s 的函数条目(%d): %s" % (os.path.basename(ko), len(allfuncs), ", ".join(allfuncs[:12])))


if __name__ == "__main__":
    main()

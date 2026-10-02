#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给内核源码打上"魅族/高通私有 KMI 兼容层" (A 方案)。

背景: 原厂内核(竞争厂商闭源)比 AOSP ACK 多导出 17 个符号, 设备上的厂商模块依赖它们:

  函数(CALL26):
    scsi_execute_cmd_len   <- ufs_qcom.ko    (首阶段! 没它 UFS 起不来 -> /data 挂不上 -> 卡 logo)
                            原厂实现 = scsi_execute_cmd + 显式 cmdlen(与上游 6.7 一致)
    mem_cgroup_id_put2     <- smartswap_zram.ko
    reclaim_pages          <- smartswap_zram.ko   (我们树里已有, 只是没导出)
    pm_system_irq_wakeup   <- qcom_glink.ko       (同上)
  数据(取地址/读取):
    wait_spam_info         <- binder_info.ko      (LDST64 读取 -> 定义成 8 字节变量即可)
    __tracepoint_android_vh_* / __tracepoint_mm_vmscan_kswapd_wake  <- mz_*.ko 等

判断依据来自模块重定位类型(tools/symbol_ref_kind.py)与模块/内核 BTF。

用法:
  python tools/apply_kmi_shim.py --kernel-root <内核源码根>      # 幂等
"""
import argparse
import os
import re
import sys

MARK = "MZ_KMI_SHIM"

HOOKS_BINDER = [
    "android_vh_binder_alloc",
    "android_vh_binder_ioctl",
]

HOOKS_MM = [
    "android_vh_extfrag_for_order",
    "android_vh_memcg_filepages_protect",
    "android_vh_memcg_protect_lru_gen_add_folio",
    "android_vh_mm_vip_alloc_harder",
    "android_vh_mm_vip_alloc_harder_stat",
    "android_vh_mm_vip_kvmalloc",
    "android_vh_ra_tuning_max_page",
    "android_vh_smartzram_tune_swappiness",
    "android_vh_tune_watermark_ratio",
]

SCSI_SIG_OLD = re.compile(
    r"int scsi_execute_cmd\(struct scsi_device \*sdev, const unsigned char \*cmd,\s*\n"
    r"\s*blk_opf_t opf, void \*buffer, unsigned int bufflen,\s*\n"
    r"\s*int timeout, int retries,\s*\n"
    r"\s*const struct scsi_exec_args \*args\)")

SCSI_SIG_NEW = """int scsi_execute_cmd_len(struct scsi_device *sdev, const unsigned char *cmd,
		     blk_opf_t opf, void *buffer, unsigned int bufflen,
		     int timeout, int retries,
		     const struct scsi_exec_args *args, unsigned int cmdlen)"""

SCSI_TAIL = """
/* %s: 兼容层 —— 原厂内核导出 scsi_execute_cmd_len(显式 CDB 长度), ufs_qcom.ko 依赖它.
 * 语义与上游 6.7 一致: 唯一区别是用 cmdlen 取代 COMMAND_SIZE(cmd[0]).
 */
int scsi_execute_cmd_len(struct scsi_device *sdev, const unsigned char *cmd,
			 blk_opf_t opf, void *buffer, unsigned int bufflen,
			 int timeout, int retries,
			 const struct scsi_exec_args *args, unsigned int cmdlen);
EXPORT_SYMBOL(scsi_execute_cmd_len);

int scsi_execute_cmd(struct scsi_device *sdev, const unsigned char *cmd,
		     blk_opf_t opf, void *buffer, unsigned int bufflen,
		     int timeout, int retries,
		     const struct scsi_exec_args *args)
{
	return scsi_execute_cmd_len(sdev, cmd, opf, buffer, bufflen, timeout,
				    retries, args, COMMAND_SIZE(cmd[0]));
}
""" % MARK

VMS_CAN = """
/* %s: 原厂内核导出给 smartswap_zram.ko */
EXPORT_SYMBOL(reclaim_pages);
/* 主线段 ks - 原厂把该 tracepoint 也导出给 kswapd_opt.ko */
EXPORT_TRACEPOINT_SYMBOL_GPL(mm_vmscan_kswapd_wake);
""" % MARK

WAKEUP_CAN = """
/* %s: 原厂内核导出给 qcom_glink.ko / qca_cld3_kiwi_v2.ko */
EXPORT_SYMBOL(pm_system_irq_wakeup);
""" % MARK

MEMCG_CAN = """
/* %s: 原厂内核导出给 smartswap_zram.ko, 语义同 mem_cgroup_id_put */
void mem_cgroup_id_put2(struct mem_cgroup *memcg)
{
	mem_cgroup_id_put(memcg);
}
EXPORT_SYMBOL(mem_cgroup_id_put2);
""" % MARK

VENDOR_HOOKS_CAN = """
/* %s: 原厂私有的数据符号 —— binder_info.ko 用 LDST64 读取(8 字节), 零值即"无 spam 信息".
 * 原厂内核 BTF 中没有它的函数/变量条目(可能是汇编或未生成 BTF 的编译单元), 但
 * __ksymtab_strings 里有该名字(见 tools/symbol_ref_kind.py 的重定位判定).
 */
unsigned long wait_spam_info;
EXPORT_SYMBOL(wait_spam_info);
""" % (MARK + ":SPAM")


def read(path):
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(text)


def patch_scsi(root, log):
    path = os.path.join(root, "drivers", "scsi", "scsi_lib.c")
    src = read(path)
    if MARK in src:
        log.append("  跳过(已打过): drivers/scsi/scsi_lib.c")
        return True
    if not SCSI_SIG_OLD.search(src):
        log.append("  !! 找不到 scsi_execute_cmd 的签名: drivers/scsi/scsi_lib.c")
        return False
    src = SCSI_SIG_OLD.sub(SCSI_SIG_NEW, src, count=1)
    if "\tscmd->cmd_len = COMMAND_SIZE(cmd[0]);\n" not in src:
        log.append("  !! 找不到 scmd->cmd_len 赋值: drivers/scsi/scsi_lib.c")
        return False
    src = src.replace("\tscmd->cmd_len = COMMAND_SIZE(cmd[0]);\n",
                      "\tscmd->cmd_len = cmdlen;\n", 1)
    src += SCSI_TAIL
    write(path, src)
    log.append("  已打: drivers/scsi/scsi_lib.c (新增 scsi_execute_cmd_len + 导出)")
    return True


def append_marked(root, rel, block, log, expect=None, tag=""):
    path = os.path.join(root, rel)
    src = read(path)
    marker = MARK + tag
    if marker in src:
        log.append("  跳过(已打过): %s%s" % (rel, tag))
        return True
    if expect and expect not in src:
        log.append("  !! %s 里找不到锚点 %r, 拒绝半途修改" % (rel, expect))
        return False
    write(path, src + block)
    log.append("  已打: %s%s" % (rel, tag))
    return True


def patch_hook_header(root, rel, names, log):
    """把 DECLARE_HOOK 插到 hook 头文件的 #endif 之前(必须在 define_trace.h 之前)。"""
    path = os.path.join(root, rel)
    src = read(path)
    if MARK in src:
        log.append("  跳过(已打过): %s" % rel)
        return True
    inc = src.rfind("#include <trace/define_trace.h>")
    if inc < 0:
        log.append("  !! %s 里没有 define_trace.h, 拒绝修改" % rel)
        return False
    endif = src.rfind("\n#endif", 0, inc)
    if endif < 0:
        log.append("  !! %s 里 define_trace.h 之前没有 #endif, 拒绝修改" % rel)
        return False
    decl = "\n/* %s: 原厂私有的 vendor hook, 仅需存在并导出(内核侧不调用) */\n" % MARK
    for n in names:
        decl += "DECLARE_HOOK(%s,\n\tTP_PROTO(void *unused),\n\tTP_ARGS(unused));\n" % n
    src = src[:endif] + decl + src[endif:]
    write(path, src)
    log.append("  已打: %s (+%d 个 hook)" % (rel, len(names)))
    return True


def append_exports(root, rel, names, log):
    path = os.path.join(root, rel)
    src = read(path)
    tag = ":EXPORTS"
    if MARK + tag in src:
        log.append("  跳过(已打过): %s%s" % (rel, tag))
        return True
    block = "\n/* %s%s: 导出原厂私有 hook 的 tracepoint */\n" % (MARK, tag)
    for n in names:
        block += "EXPORT_TRACEPOINT_SYMBOL_GPL(%s);\n" % n
    write(path, src + block)
    log.append("  已打: %s%s (+%d 个导出)" % (rel, tag, len(names)))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel-root", required=True, help="内核源码根(含 drivers/ mm/ 等)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = args.kernel_root
    if not os.path.isdir(os.path.join(root, "drivers")):
        print("内核源码根不对: %s" % root)
        return 2
    log = []
    ok = True
    ok &= patch_scsi(root, log)
    ok &= append_marked(root, "mm/vmscan.c", VMS_CAN, log, expect="reclaim_pages")
    ok &= append_marked(root, "drivers/base/power/wakeup.c", WAKEUP_CAN, log, expect="pm_system_irq_wakeup")
    ok &= append_marked(root, "mm/memcontrol.c", MEMCG_CAN, log, expect="mem_cgroup_id_put")
    ok &= patch_hook_header(root, "include/trace/hooks/binder.h", HOOKS_BINDER, log)
    ok &= patch_hook_header(root, "include/trace/hooks/mm.h", HOOKS_MM, log)
    ok &= append_exports(root, "drivers/android/vendor_hooks.c", HOOKS_BINDER + HOOKS_MM, log)
    ok &= append_marked(root, "drivers/android/vendor_hooks.c", VENDOR_HOOKS_CAN, log, tag=":SPAM")
    print("== KMI 兼容层(A 方案)结果 ==")
    for line in log:
        print(line)
    if not ok:
        print("RESULT: FAIL —— 有锚点未命中, 构建应当停下(不要拿半成品去刷机)")
        return 1
    print("RESULT: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

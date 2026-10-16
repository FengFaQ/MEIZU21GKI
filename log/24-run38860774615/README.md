# 构建失败 run 24

- 时间(UTC): 2026-10-16T06:36:31Z
- 仓库/分支: FengFaQ/MEIZU21GKI @ main
- 提交: 816a78370ccda13b51a587bfff476ce0f161ebee
- 工作流: MEIZU21GKI 构建 (ReSukiSU + SUSFS, android14-6.1.25)
- 运行页面: https://github.com/FengFaQ/MEIZU21GKI/actions/runs/38860774615
- 变体/模式: ReSukiSU / 关闭 (SUSFS=true)
- GKI: android14-6.1.25-2023-10
- LTO: none
- extra_config: |
    # CONFIG_TRIM_UNUSED_KSYMS is not set
    # CONFIG_PANIC_ON_OOPS is not set
    # 允许 adb shell dmesg 读取内核日志(否则 user 版构建下 shell 无权读, 排障只能靠抢 512K
    # 环形缓冲区的开机瞬间 —— 本次黑屏问题正是靠这个手段才定位到 msm_kgsl 的符号 CRC 失配)。
    # 只影响权限位, 不涉及任何导出符号/KMI。
    # CONFIG_SECURITY_DMESG_RESTRICT is not set
    CONFIG_PANIC_TIMEOUT=30
    # CONFIG_DAMON is not set
    # CONFIG_BLK_CGROUP_IOPRIO is not set
    

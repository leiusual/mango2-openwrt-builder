# GL-MG1300 OpenWrt 构建

通过 GitHub Actions 构建 [OpenWrt PR #24886](https://github.com/openwrt/openwrt/pull/24886) 的固定源码，目标设备为 **GL.iNet GL-MG1300（Mango 2）**。

每次构建使用全新的源码目录，固定 OpenWrt、packages 和 LuCI 的提交，不复用旧编译目录或缓存。PR 源码树已包含 SPI-NOR 和 MG1300 设备支持两个提交，直接构建即可。

## 固件内容

以 PR 的设备默认配置为基础，仅额外选择以下软件包：

| 功能 | 软件包 |
| --- | --- |
| LuCI HTTPS 管理界面 | `luci-ssl` |
| QMI 拨号及 LuCI 配置 | `kmod-usb-net-qmi-wwan`、`uqmi`、`luci-proto-qmi` |
| Modem AT 串口 | `kmod-usb-serial-option` |
| USB 识别与驱动绑定诊断 | `usbutils` |
| WireGuard 及 LuCI 配置 | `kmod-wireguard`、`wireguard-tools`、`luci-proto-wireguard` |

USB 控制器、无线驱动等由 MG1300 profile 选择；USB 网络/串口底层驱动、QMI、WireGuard 的间接依赖由 `make defconfig` 解析。构建会核对配置片段中的选项是否实际生效。

IPv6、DHCP、DNS、防火墙和无线使用上游默认值。APN、蜂窝接口、USB ID 绑定、WireGuard Peer 和路由在刷机后按实际网络配置。

源码只应用两处单行补丁：

| 补丁 | 修改 |
| --- | --- |
| `patches/0001-default-lan-ip.patch` | 默认 LAN 地址改为 `192.168.8.1/24` |
| `patches/0002-qmi-ipv4-gateway-prefix.patch` | 修正原生 QMI 在 `dhcp=0` 分支中的 IPv4 网关主机路由：`/128` → `/32` |

补丁应用前执行 `git apply --check`，应用后检查脚本语法；不适用时停止构建。完整差异随构建信息保存。

## 配置入口

| 文件 | 用途 |
| --- | --- |
| `configs/release.json` | 固定源码 SHA、PR 编号、自有修订号与 Pre-release 标记 |
| `configs/mg1300.config` | 设备和额外软件包选择 |
| `feeds.conf` | 固定官方 packages、LuCI 提交 |
| `patches/` | 构建时应用的源码补丁 |

当前源码：`e507084c386fd415a31563a09def0dfa85191b2f`。

当前版本：`OpenWrt-PR24886-e507084c-mg1300-r3`。构建不会自动追踪 PR 更新。

## 构建与发布

| 触发方式 | 行为 |
| --- | --- |
| main push / Pull Request | 检查版本、发布逻辑和文件格式 |
| Actions → Build MG1300 OpenWrt → Run workflow，选择分支 | 完整构建并上传 Artifacts |
| 推送匹配配置的 `OpenWrt-PR*-mg1300-r*` tag，或手动选择该 tag | 完整构建，成功后自动发布 Release |

发布版本时，先提交修改并确保检查通过，再创建配置对应的 tag：

```sh
release_tag=$(python3 scripts/release.py version)
git tag -a "$release_tag" -m "$release_tag"
git push origin "$release_tag"
```

修改配置、补丁、feeds 或构建发布实现时递增 `revision`；更新源码 SHA 时重新核对补丁与 feeds，并将 `revision` 设为 1。已发布的 tag 和附件不覆盖。

发布前会校验 MG1300 镜像、源码/feeds、构建输入、tag 与校验和。附件先上传到草稿，完整后再公开；当前设置为 **Pre-release，待实机验收**。

Release 和 `mg1300-release-*` Artifact 包含：

- `*-sysupgrade.bin`：MG1300 固件。
- `*-build-output.tar.gz`：完整 `bin/`，包括原始镜像、匹配内核的软件包和清单。
- `*-build-info.tar.gz`：固定源码、feeds、展开配置、补丁差异和构建日志。
- `build-metadata.json`、`SHA256SUMS`：构建来源和产物校验信息。

`mg1300-build-info-*` Artifact 单独保存诊断信息，失败时也会尝试上传。Artifacts 保留 14 天。工作流使用 Ubuntu 24.04，完整构建最长 6 小时，失败后尝试单线程输出详细日志。

## 使用

全新安装或恢复出厂设置后，通过 LAN 访问 `https://192.168.8.1`。保留配置升级时，已有 LAN 地址仍然优先。

在 LuCI 中添加 QMI 接口、填写实际控制设备 `/dev/cdc-wdmX` 和 APN，并加入 `wan` 防火墙区域；WireGuard 的密钥、Peer、路由和防火墙按用途配置。串口设备需核对实际 `/dev/ttyUSBX`，可用 `lsusb`、`lsusb -t` 检查驱动绑定。预装驱动不代表特定 Modem 已能自动识别。

这是 PR 测试固件。刷写方式见 [PR 安装说明](https://github.com/openwrt/openwrt/pull/24886)；从 GL 原厂迁移时不保留配置，刷写前备份并确认恢复方法。**仅用于 MG1300，不能刷入 MT1300。** 编译通过后仍需实机验证网络、无线、USB 和升级功能。

本地检查构建发布代码：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/release.py version
git diff --check
```

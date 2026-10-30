# Mango2 OpenWrt Builder

通过 GitHub Actions 构建 [OpenWrt PR #24886](https://github.com/openwrt/openwrt/pull/24886) 的固定源码，目标设备为 **GL.iNet GL-MG1300（Mango 2）**。

每次构建使用全新的源码目录，固定 OpenWrt、packages 和 LuCI 的提交，不复用旧编译目录或缓存。PR 源码树已包含 SPI-NOR 和 MG1300 设备支持两个提交，直接构建即可。

## 固件内容

以 PR 的设备默认配置为基础，仅额外选择以下软件包：

| 功能 | 软件包 |
| --- | --- |
| LuCI HTTPS 管理界面 | `luci-ssl` |
| QMI 拨号及 LuCI 配置 | `kmod-usb-net-qmi-wwan`、`uqmi`、`luci-proto-qmi` |
| Modem AT 串口 | `kmod-usb-serial-option` |
| 按需读取、发送和删除短信（CLI） | `sms-tool`，命令名 `sms_tool` |
| USB 识别与驱动绑定诊断 | `usbutils` |
| WireGuard 及 LuCI 配置 | `kmod-wireguard`、`wireguard-tools`、`luci-proto-wireguard` |

USB 控制器、无线驱动等由 MG1300 profile 选择；USB 网络/串口底层驱动、QMI、WireGuard 的间接依赖由 `make defconfig` 解析。构建会核对配置片段中的选项是否实际生效。

IPv6、DHCP、DNS和防火墙使用上游默认值。hostname 默认为 `Mango`；双频 Wi-Fi 的 SSID 默认为 `Mango`、国家为 `CN`，默认开启且不设密码（开放网络），信道和带宽沿用上游硬件检测结果。APN、蜂窝接口、WireGuard Peer 和路由在刷机后按实际网络配置。短信只提供 CLI，不安装短信 LuCI 插件或启用后台轮询。

`files/` 作为 OpenWrt 根文件系统 overlay 内置到镜像，并纳入构建输入 SHA256 和 build-info 归档；包含 DJI 模块驱动绑定 hotplug，以及 MG1300 的 LAN IP / hostname / Wi-Fi 默认配置。采用官方 [Firmware Selector](https://firmware-selector.openwrt.org/?version=25.12.6) 的 `uci-defaults` 首次启动脚本方式，在上游生成配置后通过 `uci set` / `uci commit` 应用定制值，不覆盖整份 UCI 配置，也不修改 `config_generate`。参考该方式不改变本项目固定的 PR 源码版本。

`files/etc/uci-defaults/99-mango-defaults` 仅保留相对固定源码 `e507084c` 的定制值：

| 项目 | 上游默认 | 本项目 |
| --- | --- | --- |
| LAN IPv4 | `192.168.1.1/24` | `192.168.8.1/24`，使用 CIDR 格式，不另设 `netmask` |
| hostname | `OpenWrt` | `Mango` |
| Wi-Fi 国家 | 2.4/5 GHz 不指定国家 | `CN` |
| Wi-Fi SSID / 启用状态 | `OpenWrt`，默认禁用 | 两个无线接口均设为 `Mango`、`disabled=0` |

核对依据为固定版本的 [config_generate](https://github.com/openwrt/openwrt/blob/e507084c386fd415a31563a09def0dfa85191b2f/package/base-files/files/bin/config_generate) 和 [mac80211.uc](https://github.com/openwrt/openwrt/blob/e507084c386fd415a31563a09def0dfa85191b2f/package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc)。2.4/5 GHz 加密默认即为 `none`，因此不重复设置。该版本在 `wifi-iface` 上设置 `disabled=1`，脚本只需将其改为 `0`，无需额外设置 `wifi-device.disabled`。LAN/WAN 端口由 MG1300 上游板级配置提供，LAN 静态协议、Wi-Fi 的 LAN 归属、AP 模式、信道和带宽等均沿用上游。

脚本仅通过 UCI 设置和提交上述定制值。无线检测与配置生成由上游 [boot](https://github.com/openwrt/openwrt/blob/e507084c386fd415a31563a09def0dfa85191b2f/package/base-files/files/etc/init.d/boot) 和 [无线 hotplug](https://github.com/openwrt/openwrt/blob/e507084c386fd415a31563a09def0dfa85191b2f/package/network/config/wifi-scripts/files/etc/hotplug.d/ieee80211/10-wifi-detect) 负责，默认设置脚本不再调用 `wifi config` 或维护独立日志。脚本成功退出后由系统从 `/etc/uci-defaults/` 删除，后续启动不再执行；只读原件仍保留在 `/rom/etc/uci-defaults/`。UCI 命令失败时返回非零，由系统保留脚本供下次启动执行。

源码只应用一处单行补丁：

| 补丁 | 修改 |
| --- | --- |
| `patches/0001-qmi-ipv4-gateway-prefix.patch` | 修正原生 QMI 在 `dhcp=0` 分支中的 IPv4 网关主机路由：`/128` → `/32` |

补丁应用前执行 `git apply --check`，应用后检查脚本语法；不适用时停止构建。完整差异随构建信息保存。

## 配置入口

| 文件 | 用途 |
| --- | --- |
| `configs/release.json` | 固定源码 SHA、PR 编号、自有修订号与 Pre-release 标记 |
| `configs/mango2.config` | 设备和额外软件包选择 |
| `feeds.conf` | 固定官方 packages、LuCI 提交 |
| `patches/` | 构建时应用的源码补丁 |
| `files/` | 内置到固件根目录的文件，包括 DJI USB hotplug 和 Mango 默认配置 |

当前源码：`e507084c386fd415a31563a09def0dfa85191b2f`。

当前版本：`OpenWrt-PR24886-e507084c-mango2-r8`。构建不会自动追踪 PR 更新。

## 构建与发布

| 触发方式 | 行为 |
| --- | --- |
| main push / Pull Request | 检查版本、发布逻辑和文件格式 |
| Actions → Build Mango2 → Run workflow，选择分支 | 完整构建并上传 Artifacts |
| 推送匹配配置的 `OpenWrt-PR*-mango2-r*` tag，或手动选择该 tag | 完整构建，成功后自动发布 Release |

发布版本时，先提交修改并确保检查通过，再创建配置对应的 tag：

```sh
release_tag=$(python3 scripts/release.py version)
git tag -a "$release_tag" -m "$release_tag"
git push origin "$release_tag"
```

修改配置、补丁、feeds 或构建发布实现时递增 `revision`；更新源码 SHA 时重新核对补丁与 feeds，并将 `revision` 设为 1。已发布的 tag 和附件不覆盖。

发布前会校验 MG1300 镜像、源码/feeds、构建输入、tag 与校验和。附件先上传到草稿，完整后再公开；当前设置为 **Pre-release，待实机验收**。

Release 和 `mango2-release-*` Artifact 包含：

- `*-sysupgrade.bin`：MG1300 固件。
- `*-build-output.tar.gz`：完整 `bin/`，包括原始镜像、匹配内核的软件包和清单。
- `*-build-info.tar.gz`：固定源码、feeds、展开配置、补丁差异和构建日志。
- `build-metadata.json`、`SHA256SUMS`：构建来源和产物校验信息。

`mango2-build-info-*` Artifact 单独保存诊断信息，失败时也会尝试上传。Artifacts 保留 14 天。工作流使用 Ubuntu 24.04，完整构建最长 6 小时，失败后尝试单线程输出详细日志。

## 使用

安装和升级均不保留配置，使用固件默认值重新生成配置，再按需设置。启动后通过 LAN 访问 `https://192.168.8.1`。

全新配置会生成 hostname `Mango` 和双频无密码 Wi-Fi `Mango`（国家 `CN`）；root 沿用上游默认无密码，不通过 workflow 注入密码。两个频段均不显式设置信道，信道和带宽由上游硬件检测生成。可在 LuCI 中设置密码。`files/etc/uci-defaults/99-mango-defaults` 只在首次启动时应用定制值，不包含旧配置迁移逻辑。

在 LuCI 中添加 QMI 接口、填写实际控制设备 `/dev/cdc-wdmX` 和 APN，并加入 `wan` 防火墙区域；WireGuard 的密钥、Peer、路由和防火墙按用途配置。串口设备需核对实际 `/dev/ttyUSBX`，可用 `lsusb`、`lsusb -t` 检查驱动绑定。

### DJI 模块自动绑定

`files/etc/hotplug.d/usb/99-dji-qmi` 来自当前 MG1300 上使用的脚本，限定 DJI IG832 USB ID `2ca3:4006`：接口 0–3 使用 `option`，接口 4 使用 `qmi_wwan`。它处理 USB add 及冷插拔重放事件，不会设置 APN、创建拨号接口或重置模块；其他 USB ID 不受影响。

串口动态 ID 引用 `05c6:908b` 的 `RSVD(4)`，避免串口驱动占用接口 4；确认四个串口已绑定后，临时引用 `2c7c:0125` 的 QMI 驱动信息完成绑定，并移除临时 QMI ID。检测到异常接口布局、已有其他驱动或持久的同 ID QMI 规则时停止并记录 `dji-qmi` 日志，不主动解绑设备。

这两个参考条目已核对 [Linux 6.18 option 驱动](https://github.com/torvalds/linux/blob/v6.18/drivers/usb/serial/option.c)和 [QMI 驱动](https://github.com/torvalds/linux/blob/v6.18/drivers/net/usb/qmi_wwan.c)，当前运行内核为 6.18.44。更换源码/内核或模块 USB 模式后需重新核对；不能视为所有 DJI 模块通用支持。内置后的新固件仍需验收冷启动和热插拔。

### 按需读取短信

当前设备已验证 AT 端口为 `/dev/ttyUSB2`，短信存放在模块内部 `ME`：

```sh
sms_tool -d /dev/ttyUSB2 -s ME status
sms_tool -d /dev/ttyUSB2 -s ME recv
sms_tool -d /dev/ttyUSB2 -s ME -j recv
```

普通输出便于直接阅读；JSON 输出适合程序处理。长短信按分段返回，不自动合并。端口和存储区只作为当前设备示例，不写入全局默认值。

这是 PR 测试固件。刷写方式见 [PR 安装说明](https://github.com/openwrt/openwrt/pull/24886)；从 GL 原厂迁移时不保留配置，刷写前备份并确认恢复方法。**仅用于 MG1300，不能刷入 MT1300。** 编译通过后仍需实机验证网络、无线、USB 和升级功能。

本地检查构建发布代码：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/release.py version
sh -n files/etc/hotplug.d/usb/99-dji-qmi
sh -n files/etc/uci-defaults/99-mango-defaults
git diff --check
```

#!/usr/bin/env python3
"""Version, package and verify GL-MG1300 release artifacts."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = 'glinet_gl-mg1300'


def version(config):
    if config['source_repository'] != 'openwrt/openwrt' or config['device'] != 'mg1300':
        raise ValueError('This release pipeline is exclusively for OpenWrt GL-MG1300')
    if type(config['source_pr']) is not int or config['source_pr'] < 1:
        raise ValueError('Expected an upstream PR number')
    if not re.fullmatch(r'[0-9a-f]{40}', config['source_commit']):
        raise ValueError('OpenWrt source must be pinned to a full commit SHA')
    if type(config['revision']) is not int or config['revision'] < 1:
        raise ValueError('Revision must be a positive integer')
    if type(config['prerelease']) is not bool:
        raise ValueError('prerelease must be a boolean')
    return f"OpenWrt-PR{config['source_pr']}-{config['source_commit'][:8]}-mg1300-r{config['revision']}"


def check_ref(config, ref_type, ref_name):
    tag = version(config)
    if ref_type == 'tag' and ref_name != tag:
        raise ValueError(f'Tag {ref_name!r} does not match locked release {tag!r}')
    return tag


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def feeds(repo):
    result = {}
    for line in (repo / 'feeds.conf').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = re.fullmatch(r'src-git (packages|luci) https://github.com/openwrt/\1\.git\^([0-9a-f]{40})', line)
        if not match or match[1] in result:
            raise ValueError('Expected exactly two official feeds pinned to full commit SHAs')
        result[match[1]] = match[2]
    if set(result) != {'packages', 'luci'}:
        raise ValueError('Missing packages or luci feed')
    return result


def recipe(repo):
    paths = [repo / 'configs/mg1300.config', repo / 'configs/release.json', repo / 'feeds.conf']
    paths += sorted((repo / 'patches').glob('*.patch'))
    paths += sorted(p for p in (repo / 'files').rglob('*') if p.is_file())
    return {str(p.relative_to(repo)): sha256(p) for p in paths}


def provenance(repo, config):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    return {'release_tag': version(config), 'builder_commit': commit,
            'run_id': os.environ.get('GITHUB_RUN_ID', 'local'),
            'source': config, 'feeds': feeds(repo), 'recipe_sha256': recipe(repo)}


def verify_metadata(metadata, expected):
    for field, value in expected.items():
        if metadata.get(field) != value:
            raise ValueError(f'Artifact provenance mismatch: {field}')
    if not metadata.get('original_image', '').endswith(f'-{PROFILE}-squashfs-sysupgrade.bin'):
        raise ValueError('Artifact is not a GL-MG1300 sysupgrade image')


def package(repo, config, firmware, info, output):
    images = list((firmware / 'targets/ramips/mt7621').glob(f'*-{PROFILE}-squashfs-sysupgrade.bin'))
    if len(images) != 1 or images[0].stat().st_size == 0:
        raise ValueError('Expected one nonempty GL-MG1300 sysupgrade image')
    source = re.search(r'^commit ([0-9a-f]{40})$', (info / 'source.txt').read_text(), re.M)
    if not source or source[1] != config['source_commit']:
        raise ValueError('Build used a different OpenWrt source commit')
    actual_feeds = dict(line.split() for line in (info / 'feed-revisions.txt').read_text().splitlines())
    if actual_feeds != feeds(repo):
        raise ValueError('Build feeds differ from the locked feeds')
    if f'CONFIG_TARGET_ramips_mt7621_DEVICE_{PROFILE}=y' not in (info / 'config.full').read_text().splitlines():
        raise ValueError('Resolved configuration did not select MG1300')
    recorded = json.loads((info / 'builder-inputs.json').read_text())
    inputs = provenance(repo, config)
    if recorded != inputs:
        raise ValueError('Build inputs changed since compilation started')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty release output directory to avoid mixing versions')
    tag = version(config)
    metadata = dict(inputs, original_image=images[0].name,
                    image_sha256=sha256(images[0]))
    (output / 'build-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    shutil.copyfile(images[0], output / f'{tag}-sysupgrade.bin')
    # Preserve matching kernel packages and the complete original build output.
    with tarfile.open(output / f'{tag}-build-output.tar.gz', 'w:gz') as archive:
        archive.add(firmware, arcname='bin')
    with tarfile.open(output / f'{tag}-build-info.tar.gz', 'w:gz') as archive:
        archive.add(info, arcname='build-info')
    names = sorted(p.name for p in output.iterdir())
    (output / 'SHA256SUMS').write_text(''.join(f'{sha256(output / name)}  {name}\n' for name in names))


def verify(repo, config, output):
    tag = version(config)
    metadata = json.loads((output / 'build-metadata.json').read_text())
    verify_metadata(metadata, provenance(repo, config))
    expected_names = {'build-metadata.json', f'{tag}-sysupgrade.bin',
                      f'{tag}-build-output.tar.gz', f'{tag}-build-info.tar.gz'}
    checksums = {}
    for line in (output / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        if name in checksums or name not in expected_names:
            raise ValueError('Unexpected or duplicate checksum entry')
        checksums[name] = digest
    if set(checksums) != expected_names:
        raise ValueError('Incomplete release checksums')
    for name, digest in checksums.items():
        if sha256(output / name) != digest:
            raise ValueError(f'Checksum mismatch: {name}')
    if sha256(output / f'{tag}-sysupgrade.bin') != metadata['image_sha256']:
        raise ValueError('Image differs from the audited firmware')
    repository = os.environ.get('GITHUB_REPOSITORY', 'leiusual/mg1300-openwrt-builder')
    (output / 'release-notes.md').write_text(f'''GL.iNet **GL-MG1300（Mango 2）** 测试固件，不能用于 MT1300 或 NanoPi Zero2。

- 自有版本：`{tag}`；构建仓库 commit：`{metadata['builder_commit']}`。
- 源码：OpenWrt PR #{config['source_pr']}，固定 commit `{config['source_commit']}`，加本仓库两处补丁。
- 这不是 OpenWrt 官方稳定版，也不是 GL.iNet 原厂固件；构建与镜像检查通过，实机功能仍待验收。
- 默认 LAN：`192.168.8.1/24`；包含 LuCI HTTPS、QMI、Modem 串口、短信 CLI、USB 诊断及 WireGuard，以及 DJI `2ca3:4006` 驱动绑定 hotplug。
- 全新配置：hostname `Mango`；双频 Wi-Fi `Mango`，国家 `CN`，默认开启且不设密码；保留配置升级时沿用已有设置。
- `*-sysupgrade.bin` 是 MG1300 镜像；`*-build-output.tar.gz` 保存完整输出及匹配的软件包；`*-build-info.tar.gz` 保存配置、源码差异及构建日志。
- `SHA256SUMS` 校验上述文件与 `build-metadata.json`。安装和验收请阅读[该版本 README](https://github.com/{repository}/blob/{tag}/README.md)。

DJI hotplug 沿用现有设备上使用的脚本；新镜像仍需验证冷启动和热插拔，APN 和拨号接口需按实际网络配置。
''')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['version', 'record', 'package', 'verify'])
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--firmware', type=Path, default=REPO / 'openwrt/bin')
    parser.add_argument('--info', type=Path, default=REPO / 'build-info')
    parser.add_argument('--output', type=Path, default=REPO / 'release-assets')
    args = parser.parse_args()
    config = json.loads((REPO / 'configs/release.json').read_text())
    tag = check_ref(config, os.environ.get('GITHUB_REF_TYPE', ''), os.environ.get('GITHUB_REF_NAME', ''))
    if args.command == 'version':
        feeds(REPO)
        if args.github_output:
            with args.github_output.open('a') as stream:
                stream.write(f'tag={tag}\nsource_sha={config["source_commit"]}\nprerelease={str(config["prerelease"]).lower()}\n')
        print(tag)
    elif args.command == 'record':
        args.info.mkdir(parents=True, exist_ok=True)
        (args.info / 'builder-inputs.json').write_text(json.dumps(provenance(REPO, config), indent=2) + '\n')
    elif args.command == 'package':
        package(REPO, config, args.firmware.resolve(), args.info.resolve(), args.output.resolve())
    else:
        verify(REPO, config, args.output.resolve())


if __name__ == '__main__':
    main()

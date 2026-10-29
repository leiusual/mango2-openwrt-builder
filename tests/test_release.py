import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import release


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'configs/release.json').read_text())

    def test_device_source_and_revision_identify_release(self):
        tag = release.version(self.config)
        self.assertIn('-' + self.config['source_commit'][:8] + '-mango2-r', tag)
        self.assertEqual(release.version(dict(self.config, revision=2)).rsplit('-r', 1)[1], '2')

    def test_wrong_device_or_unpinned_source_rejected(self):
        for change in [{'device': 'zero2'}, {'device': 'mt1300'},
                       {'source_commit': 'main'}, {'revision': 0}, {'revision': True}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                release.version(dict(self.config, **change))

    def test_wrong_release_tag_rejected(self):
        for tag in ['build-20261025-01', 'OpenWrt-PR24886-00000000-mango2-r1']:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.check_ref(self.config, 'tag', tag)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        (self.repo / 'configs').mkdir(parents=True)
        (self.repo / 'patches').mkdir()
        for name in ['configs/release.json', 'configs/mango2.config', 'feeds.conf']:
            (self.repo / name).write_bytes((ROOT / name).read_bytes())
        self.config = json.loads((self.repo / 'configs/release.json').read_text())
        self.firmware = self.root / 'bin'
        target = self.firmware / 'targets/ramips/mt7621'
        target.mkdir(parents=True)
        self.image = target / 'openwrt-ramips-mt7621-glinet_gl-mg1300-squashfs-sysupgrade.bin'
        self.image.write_bytes(b'MG1300 test image')
        self.info = self.root / 'info'
        self.info.mkdir()
        (self.info / 'source.txt').write_text('commit ' + self.config['source_commit'] + '\n')
        (self.info / 'feed-revisions.txt').write_text(''.join(f'{k} {v}\n' for k, v in release.feeds(self.repo).items()))
        (self.info / 'config.full').write_text('CONFIG_TARGET_ramips_mt7621_DEVICE_glinet_gl-mg1300=y\n')
        self.output = self.root / 'assets'
        self.mock_git = patch('release.subprocess.check_output', return_value='b' * 40 + '\n')
        self.mock_git.start()
        self.addCleanup(self.mock_git.stop)
        self.record()

    def record(self):
        (self.info / 'builder-inputs.json').write_text(json.dumps(release.provenance(self.repo, self.config)))

    def package(self):
        release.package(self.repo, self.config, self.firmware, self.info, self.output)

    def test_complete_release_and_checksums(self):
        self.package()
        release.verify(self.repo, self.config, self.output)
        self.assertTrue((self.output / 'release-notes.md').exists())

    def test_tampered_image_is_rejected(self):
        self.package()
        (self.output / (release.version(self.config) + '-sysupgrade.bin')).write_bytes(b'wrong image')
        with self.assertRaisesRegex(ValueError, 'Checksum'):
            release.verify(self.repo, self.config, self.output)

    def test_incomplete_checksums_are_rejected(self):
        self.package()
        (self.output / 'SHA256SUMS').write_text('')
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            release.verify(self.repo, self.config, self.output)

    def test_mt1300_image_is_rejected(self):
        self.image.rename(self.image.with_name(self.image.name.replace('mg1300', 'mt1300')))
        with self.assertRaisesRegex(ValueError, 'GL-MG1300'):
            self.package()

    def test_missing_image_is_rejected(self):
        self.image.unlink()
        with self.assertRaisesRegex(ValueError, 'one nonempty'):
            self.package()

    def test_empty_image_is_rejected(self):
        self.image.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'one nonempty'):
            self.package()

    def test_multiple_images_are_rejected(self):
        self.image.with_name('extra-' + self.image.name).write_bytes(b'extra image')
        with self.assertRaisesRegex(ValueError, 'one nonempty'):
            self.package()

    def test_different_source_or_feeds_are_rejected(self):
        for name, content in [('source.txt', 'commit ' + '0' * 40 + '\n'), ('feed-revisions.txt', 'packages ' + '0' * 40 + '\n')]:
            target = self.info / name
            old = target.read_text()
            target.write_text(content)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.package()
            target.write_text(old)

    def test_changed_builder_inputs_are_rejected(self):
        (self.repo / 'configs/mango2.config').write_text('different recipe')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.package()

    def test_changed_firmware_overlay_is_rejected(self):
        overlay = self.repo / 'files/etc/hotplug.d/usb/99-dji-qmi'
        overlay.parent.mkdir(parents=True)
        overlay.write_text('#!/bin/sh\nexit 0\n')
        self.record()
        overlay.write_text('#!/bin/sh\nexit 1\n')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.package()

    def test_removed_firmware_overlay_is_rejected(self):
        overlay = self.repo / 'files/etc/hotplug.d/usb/99-dji-qmi'
        overlay.parent.mkdir(parents=True)
        overlay.write_text('#!/bin/sh\nexit 0\n')
        self.record()
        overlay.unlink()
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.package()

    def test_different_builder_commit_is_rejected(self):
        self.package()
        metadata = json.loads((self.output / 'build-metadata.json').read_text())
        expected = release.provenance(self.repo, self.config)
        metadata['builder_commit'] = 'c' * 40
        with self.assertRaisesRegex(ValueError, 'builder_commit'):
            release.verify_metadata(metadata, expected)


if __name__ == '__main__':
    unittest.main()

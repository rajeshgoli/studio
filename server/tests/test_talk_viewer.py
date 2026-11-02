import json
import tempfile
import unittest
from pathlib import Path

from server.productions import Productions
from server.talk_viewer import Talks


class TalkViewerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.folder = self.root / 'talks/sample'
        self.folder.mkdir(parents=True)
        self.config = dict(title='<Talk>', parts=['intro', 'one', 'two'],
                           camera_parts=['intro'], sessions={'rounds': ['one', 'two']},
                           takes_dir='takes', renders=['build/full.mp4', 'build/shorts/*.mp4'],
                           publish='v3/description.md')
        self.write('production.json', json.dumps(self.config))
        self.talks = Talks(self.root)

    def write(self, name, text='sample'):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_discovery_grouping_and_media(self):
        for name in ['take01_mic.wav', 'take01_phone.mp4', 'rounds_take01_mic.wav',
                     'one_take02_mic.wav', 'take03_mic.wav', 'unknown_take04_mic.wav']:
            self.write('takes/' + name)
        self.write('takes/take03.json', json.dumps({'parts': ['two']}))
        self.write('build/full.mp4')
        self.write('build/shorts/short.mp4')
        self.write('build/private.mp4')
        self.write('v3/description.md', 'Publishing <text>')
        data = self.talks.detail('sample')
        groups = {p['name']: [t['name'] for t in p['takes']] for p in data['parts']}
        self.assertEqual(groups['intro'], ['take01'])
        self.assertEqual(groups['one'], ['rounds_take01', 'one_take02'])
        self.assertEqual(groups['two'], ['take03', 'rounds_take01'])
        self.assertEqual(groups['Unassigned'], ['unknown_take04'])
        self.assertEqual(len(data['renders']), 2)
        self.assertTrue(data['renders'][0]['url'].startswith('/file/talk:sample/'))
        self.assertEqual(data['publishing']['text'], 'Publishing <text>')
        self.assertEqual(Productions(self.root).list()[0]['kind'], 'talk')

    def test_recording_room_take_names(self):
        for name in ['all-from-two_take01', 'Round-One_take02', 'Session-A_take03']:
            self.write(f'takes/{name}_mic.wav')
            self.write(f'takes/{name}.json', json.dumps({'parts': ['two']}))
        self.write('takes/Unknown-Part_take04_mic.wav')
        groups = {p['name']: [t['name'] for t in p['takes']]
                  for p in self.talks.detail('sample')['parts']}
        self.assertEqual(set(groups['two']),
                         {'all-from-two_take01', 'Round-One_take02', 'Session-A_take03'})
        self.assertEqual(groups['Unassigned'], ['Unknown-Part_take04'])

    def test_allowlist_and_symlink_targets(self):
        secret = self.write('build/private.mp4')
        outside = self.root / 'outside.wav'
        outside.write_text('secret')
        for name, target in [('takes/take01_mic.wav', secret), ('takes/take02_mic.wav', outside),
                             ('build/shorts/link.mp4', secret)]:
            path = self.folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)
        self.write('takes/deleted/take03_mic.wav')
        self.write('build/shorts/nested/private.mp4')
        for relative in ['build/private.mp4', 'takes/take01_mic.wav', 'takes/take02_mic.wav',
                         'build/shorts/link.mp4', 'takes/deleted/take03_mic.wav',
                         'build/shorts/nested/private.mp4', '../outside.wav', '/outside.wav',
                         'takes/../production.json', 'production.json']:
            with self.subTest(relative=relative), self.assertRaises(FileNotFoundError):
                self.talks.file('sample', relative)
        self.assertEqual(self.talks.detail('sample')['renders'], [])

    def test_corrupt_optional_metadata_and_invalid_productions(self):
        self.write('takes/take01_mic.wav')
        self.write('takes/take01.json', '{')
        self.assertEqual(self.talks.detail('sample')['parts'][0]['takes'][0]['name'], 'take01')
        self.write('production.json', '[]')
        self.assertEqual(self.talks.list(), [])
        for pid in ['../sample', 'missing']:
            with self.assertRaises(FileNotFoundError):
                self.talks.detail(pid)

"""Exercise the recording flow without opening hardware or playing sound."""
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import soundfile as sf
from server.tests import test_rooms as harness
from talk.phone import Phone
from talk.talk_room import PAGE, RATE, SILENT, line_cues, make_page, render_cued

PHONE = dict(camera_package='example.camera', record_tap=[10, 20],
             dcim='/sdcard/DCIM/Camera', preview_size=[300, 200], serial='test-device')


class TalkTest(harness.RoomTest):
    # Reuse HTTP/device harness, not singing-specific tests.
    def setUp(self):
        super().setUp()
        self.folder = self.root / 'talks' / 'demo'
        self.folder.mkdir(parents=True)
        config = dict(parts=['intro', 'body'], sessions={'all': ['intro', 'body']},
                      camera_parts=['intro'], script_dir='script', takes_dir='takes')
        (self.folder / 'production.json').write_text(json.dumps(config))
        (self.root / 'studio.json').write_text(json.dumps(dict(mic='Test mic', ear='Test ear', phone=PHONE)))
        for part in config['parts']:
            path = self.folder / 'script' / part
            (path / 'clips').mkdir(parents=True)
            (path / 'lines.json').write_text(json.dumps({'lines': [
                {'speaker': 'RAJESH', 'text': 'First line'},
                {'speaker': 'CLAUDE', 'text': 'Reply'},
                {'speaker': 'RAJESH', 'text': 'Last line'}]}))
            sf.write(path / 'clips/01_claude.wav', np.zeros(480), RATE)
        p = patch('talk.phone.Phone.connected', return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def open(self):
        self.assertEqual(self.request('/room/open', {'kind': 'talk', 'production': 'demo'})[0], 200)
        return self.server.room

    def post(self, action, body=None):
        return self.request('/room/talk/' + action, {} if body is None else body)[0]

    def wait_idle(self, room):
        deadline = time.monotonic() + 5
        while room.stage != 'idle' and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(room.stage, 'idle')

    def test_rehearsal_no_phone_no_files_and_stale_callbacks(self):
        room = self.open()
        self.assertEqual(room.ear_name, SILENT)
        self.assertEqual(self.request('/room/talk/preview.jpg')[0], 503)
        self.assertEqual(room.state()['phone_note'], 'no phone')
        self.assertEqual(self.post('rehearse', {'on': True}), 200)
        self.assertEqual(self.post('step', {'dir': 1}), 200)
        self.assertTrue(self.server.busy)
        self.assertFalse(room.recording)
        self.assertEqual(self.post('step', {'dir': 1}), 200)
        self.assertEqual(room.line, 1)
        self.assertEqual(self.post('abort'), 200)
        # A delayed completion from a prior rehearsal cannot advance a new one.
        self.post('step', {'dir': 1})
        time.sleep(.7)
        self.assertEqual(room.line, 0)
        self.post('abort')
        self.assertFalse(room.takes_dir.exists())
        room.mic.feed(480)
        self.post('rehearse', {'on': False})
        self.post('step', {'dir': 1})
        self.assertEqual(room.stage, 'idle')
        self.assertIn('no phone', room.note)
        self.assertFalse(room.takes_dir.exists())

    def test_audio_take_marks_clip_reload_and_saving(self):
        room = self.open()
        self.post('part', {'name': 'body'})
        self.post('ear', {'name': SILENT})
        path = self.folder / 'script/body/clips/01_claude.wav'
        sf.write(path, np.zeros(960), RATE)
        self.post('step', {'dir': 1})
        self.assertEqual(len(room.clips[1]), 960)
        room.mic.feed(4800)
        self.post('step', {'dir': 1})
        deadline = time.monotonic() + 3
        while room.line != 2 and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(room.line, 2, (room.stage, room.ear_name, room.note, room.run_id, room.claude_playing))
        room.mic.feed(2400)
        self.post('step', {'dir': 1})
        self.assertEqual(self.request('/room/close', {})[0], 409)
        self.wait_idle(room)
        meta = json.loads((room.takes_dir / 'body_take01.json').read_text())
        self.assertEqual([e['sample'] for e in meta['events']], [0, 4800, 4800, 7200])
        self.assertTrue(meta['complete'])
        self.assertEqual(sf.info(room.takes_dir / meta['mic']).frames, 7200)
        self.assertFalse(self.server.busy)
        self.assertEqual(self.request('/room/close', {})[0], 200)
        self.assertTrue(all(not t.is_alive() for t in room.threads))

    def test_phone_pull_failure_preserves_marks(self):
        room = self.open()
        with patch.object(room.phone, 'check_camera'), patch.object(room.phone, 'toggle_record'), patch.object(room.phone, 'newest_video', side_effect=RuntimeError('unplugged')):
            self.post('step', {'dir': 1})
            room.mic.feed(480)
            self.post('abort')
            self.wait_idle(room)
        meta = json.loads((room.takes_dir / 'take01.json').read_text())
        self.assertIn('unplugged', meta['phone_error'])
        self.assertEqual(meta['events'][-1]['sample'], 480)
        self.assertFalse(meta['complete'])

    def test_validation_routes_and_page(self):
        room = self.open()
        for action, body in [('step', {'dir': True}), ('step', {'dir': 0}),
                             ('start', {'line': -1}), ('start', {'line': 3}),
                             ('rehearse', {'on': 1}), ('part', {'name': '../secret'}),
                             ('ear', {'name': 'Test mic'})]:
            self.assertEqual(self.post(action, body), 400)
        self.assertEqual(self.request('/room/talk/step?dir=1', {})[0], 400)
        self.assertEqual(self.request('/room/sing/')[0], 404)
        self.assertEqual(self.request('/room/sing/abort', {})[0], 404)
        self.assertEqual(self.request('/room/talk/state', headers={'Host': 'remote.example'})[0], 403)
        self.assertEqual(self.request('/room/talk/abort', {}, headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('/api/status')[0], 200)
        self.assertEqual(json.loads(self.request('/api/status')[1])['room'], 'talk')
        room.lines[0]['text'] = '</script><img src=x onerror=alert(1)>'
        room.lines[0]['face'] = [{'emoji': '😳', 'after_word': 0}, {'emoji': '<b>', 'after_word': 2}]
        page = make_page(room)
        self.assertIn('<span class="cue">😳</span> &lt;/script&gt;&lt;img src=x <span class="cue">&lt;b&gt;</span> onerror', page)
        self.assertNotIn('</script><img', page)
        self.assertNotIn('{{', page)
        self.assertIn('localStorage', page)
        self.assertIn('/room/talk/state', page)
        room.phone.pulling = True
        self.assertTrue(self.server.busy)
        self.assertEqual(self.request('/room/close', {})[0], 409)
        room.phone.pulling = False

    def test_symlink_production_rejected(self):
        (self.folder / 'takes').symlink_to(self.root)
        self.assertEqual(self.request('/room/open', {'kind': 'talk', 'production': 'demo'})[0], 400)


# The base harness is shared; do not inherit its singing feature checks.
for name in list(vars(harness.RoomTest)):
    if name.startswith('test_') and name not in TalkTest.__dict__:
        setattr(TalkTest, name, None)


class CueTest(unittest.TestCase):
    """Acting cues sit at their word in the prompter, where the animation shows them."""
    TEXT = 'We built it out of old parts . Nobody fixes anything . Done'

    def page(self, *lines):
        room = SimpleNamespace(lines=[{'part': 'p', 'card': ['P'], 'speaker': 'RAJESH', **l} for l in lines],
                               choices=[('p', 'p')], session='p', video=False, phone=SimpleNamespace(size=(9, 16)))
        page = make_page(room)
        data = json.loads(page.split('const LINES=', 1)[1].split(';\n', 1)[0])
        return page, data

    def test_face_cues_take_paired_directions(self):
        line = {'text': self.TEXT, 'directions': ['melting a little 🫠', 'giggling 🤭', 'laughing 🤣'],
                'face': [{'emoji': '🫠', 'after_word': 7}, {'emoji': '🤭', 'after_word': 11}, {'emoji': '🤣', 'after_word': 13}]}
        self.assertEqual(line_cues(line), [(7, '🫠 melting a little'), (11, '🤭 giggling'), (13, '🤣 laughing')])
        self.assertEqual(render_cued(line['text'], line_cues(line)),
                         'We built it out of old parts <span class="cue">🫠 melting a little</span> . Nobody fixes anything '
                         '<span class="cue">🤭 giggling</span> . Done <span class="cue">🤣 laughing</span>')

    def test_unpaired_or_conflicting_directions_show_emoji_alone(self):
        face = [{'emoji': '😏', 'after_word': 1}, {'emoji': '🤣', 'after_word': 2}]
        for directions in (['laughing 🤣'], ['sheepish', 'smug 😏 then laughing 🤣'], None, ['a', 3]):
            self.assertEqual(line_cues({'text': 'a b c', 'directions': directions, 'face': face}), [(1, '😏'), (2, '🤣')])
        # A direction without an emoji still pairs by order.
        self.assertEqual(line_cues({'text': 'a b c', 'directions': ['sly', 'big laugh'], 'face': face}),
                         [(1, '😏 sly'), (2, '🤣 big laugh')])

    def test_positions_clamp_and_anchor(self):
        face = [{'emoji': '1', 'after_word': -2}, {'emoji': '2', 'after_word': 99}, {'emoji': '3', 'after_word': True},
                {'emoji': '4', 'anchor': 'Clock'}, {'emoji': '5', 'anchor': 'absent'}, '6', {'emoji': ''}, {'after_word': 1}, 7]
        self.assertEqual(line_cues({'text': 'look at the clock, now', 'face': face}),
                         [(0, '1'), (5, '2'), (5, '3'), (3, '4'), (5, '5'), (5, '6')])

    def test_acting_cues_win_over_face(self):
        line = {'text': 'a b c', 'face': [{'emoji': '🤣', 'after_word': 0}], 'directions': ['laughing 🤣'],
                'acting_cues': [{'direction': 'laughing 🤣', 'after_word': 0, 'anchor': 'a', 'placement': 'before'},
                                {'direction': 'long pause', 'after_word': 3}, {'direction': 5, 'after_word': 1}]}
        self.assertEqual(line_cues(line), [(0, '🤣 laughing'), (3, 'long pause')])
        self.assertEqual(line_cues({**line, 'acting_cues': []}), [(0, '🤣 laughing')])

    def test_page_keeps_string_face_and_sends_cues_to_strip_mode(self):
        page, data = self.page({'text': 'Hello there', 'face': '😁'},
                               {'text': '*Big* (aside) <b>', 'face': [{'emoji': '<i>', 'after_word': 1}]},
                               {'speaker': 'CLAUDE', 'text': 'Fine', 'acting_cues': [{'direction': 'deadpan', 'after_word': 0}]})
        self.assertIn('Hello there<span class="face">😁</span>', page)
        self.assertIn('<em>Big</em> <span class="cue">&lt;i&gt;</span> <span class="dir">(aside)</span> &lt;b&gt;', page)
        self.assertIn('<span class="cue">deadpan</span> Fine', page)
        self.assertNotIn('<i>', page)
        self.assertEqual([(l['words'], l['cues']) for l in data],
                         [(['Hello', 'there'], []), (['*Big*', '(aside)', '<b>'], [[1, '<i>']]), (['Fine'], [[0, 'deadpan']])])

    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_strip_chunks_carry_cues(self):
        js = PAGE[PAGE.index('function items('):PAGE.index('const CHUNKS')]
        lines = [{'words': self.TEXT.split(), 'cues': [[7, 'A'], [11, 'B'], [13, 'C']]},
                 {'words': ['(aside)', 'Go', 'now', '(beat)', 'then', 'stop'], 'cues': [[0, 'X'], [3, 'Y'], [1, 'Z']]},
                 {'words': [], 'cues': [[0, 'only']]}]
        out = subprocess.run(['node', '-e', js + f'console.log(JSON.stringify({json.dumps(lines)}.map(l=>chunk(items(l)))))'],
                             capture_output=True, text=True, check=True).stdout
        show = lambda chunks: [' '.join(x if isinstance(x, str) else f"[{x['cue']}]" for x in c) for c in chunks]
        self.assertEqual([show(c) for c in json.loads(out)], [
            ['We built it out', 'of old parts [A] .', 'Nobody fixes anything [B] .', 'Done [C]'],
            ['[X] (aside)', '[Z] Go now', '[Y] (beat)', 'then stop'],
            ['[only]']])


class PhoneTest(unittest.TestCase):
    def test_fixed_commands_serial_and_filename(self):
        phone = Phone(PHONE)
        with patch('talk.phone.subprocess.run') as run:
            run.return_value.stdout = 'device\n'
            self.assertTrue(phone.connected())
            self.assertEqual(run.call_args.args[0], ['adb', '-s', 'test-device', 'get-state'])
            phone.toggle_record()
            self.assertEqual(run.call_args.args[0][-5:], ['shell', 'input', 'tap', '10', '20'])
            for name in ('../bad.mp4', 'file.mp4;bad', 'a\nb.mp4', 'photo.jpg'):
                with self.assertRaises(ValueError):
                    phone.pull_video(name, Path('/tmp/unused.mp4'))
            run.return_value.stdout = 'bad name.mp4\n'
            with self.assertRaises(ValueError):
                phone.newest_video()

    def test_pull_cannot_overwrite_existing_take(self):
        phone = Phone(PHONE)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'take01_phone.mp4'
            destination.write_bytes(b'original take')
            def download(*args, **kwargs):
                self.assertTrue(phone.pulling)
                Path(args[-1]).write_bytes(b'new take')
            with patch.object(phone, '_run', side_effect=download):
                with self.assertRaises(FileExistsError):
                    phone.pull_video('new.mp4', destination)
            self.assertEqual(destination.read_bytes(), b'original take')
            self.assertFalse(phone.pulling)

    def test_disconnected_and_bad_config(self):
        phone = Phone(PHONE)
        with patch('talk.phone.subprocess.run', side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(RuntimeError, 'no phone'):
                phone.check_camera()
        for key, value in [('dcim', '/a; touch /b'), ('record_tap', [True, 1]), ('serial', '-d')]:
            with self.assertRaises(ValueError):
                Phone({**PHONE, key: value})


if __name__ == '__main__':
    unittest.main()

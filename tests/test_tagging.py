import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from mutagen.id3 import ID3
from backend import metadata, tagging
from backend.media import probe_mp3

META = {'title': 'Música: Ação', 'artist': 'Artista ft. Convidado', 'album': 'Álbum', 'year': '2017', 'youtube_id': 'ClU3fctbGls'}


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/FFprobe necessários')
class TaggingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.mp3 = self.root / 'a.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:a', 'libmp3lame', str(self.mp3)], check=True)
        thumb = self.root / 'thumb.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=1', '-frames:v', '1', str(thumb)], check=True)
        self.thumb = thumb

    def tearDown(self):
        self.temp.cleanup()

    def test_tags_cover_v23_and_audio_unchanged(self):
        cover = tagging.make_cover(self.thumb, self.root / 'cover.jpg')
        before = tagging.audio_md5(self.mp3)
        self.assertTrue(tagging.tag_file(self.mp3, META, cover, self.root / 'work'))
        tags = ID3(self.mp3)
        self.assertEqual(tags.version, (2, 3, 0))
        self.assertEqual(str(tags['TIT2']), 'Música: Ação')
        self.assertEqual(str(tags['TPE1']), 'Artista ft. Convidado')
        self.assertEqual(str(tags['TALB']), 'Álbum')
        raw = ID3(self.mp3, translate=False)  # frames exatamente como gravados no arquivo
        self.assertEqual(str(raw['TYER']), '2017')
        self.assertNotIn('TDRC', raw)
        self.assertEqual(str(tags['TXXX:YouTube ID']), 'ClU3fctbGls')
        picture = tags['APIC:Capa']
        self.assertEqual((picture.type, picture.mime), (3, 'image/jpeg'))
        self.assertEqual(picture.data, cover)
        self.assertEqual(tagging.audio_md5(self.mp3), before)
        self.assertEqual(probe_mp3(self.mp3)[1]['title'], 'Música: Ação')
        self.assertEqual(list((self.root / 'work').iterdir()), [])
        # Cobertura quadrada 500x500.
        size = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(self.root / 'cover.jpg')], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(size, '500,500')

    def test_retag_replaces_old_frames_without_duplicates(self):
        tagging.tag_file(self.mp3, META, None, self.root / 'work')
        tagging.tag_file(self.mp3, {**META, 'title': 'Novo', 'album': ''}, None, self.root / 'work')
        tags = ID3(self.mp3)
        self.assertEqual(str(tags['TIT2']), 'Novo')
        self.assertNotIn('TALB', tags)
        self.assertEqual(len(tags.getall('TXXX:YouTube ID')), 1)

    def test_failures_leave_original_untouched(self):
        original = self.mp3.read_bytes()
        with patch('backend.tagging.write_tags', side_effect=OSError('disco cheio')):
            self.assertFalse(tagging.tag_file(self.mp3, META, None, self.root / 'work'))
        self.assertEqual(self.mp3.read_bytes(), original)
        with patch('backend.tagging.audio_md5', side_effect=['MD5=a', 'MD5=b']):
            self.assertFalse(tagging.tag_file(self.mp3, META, None, self.root / 'work'))
        self.assertEqual(self.mp3.read_bytes(), original)
        broken = self.root / 'broken.mp3'
        broken.write_bytes(b'nao e mp3')
        self.assertFalse(tagging.tag_file(broken, META, None, self.root / 'work'))
        self.assertEqual(broken.read_bytes(), b'nao e mp3')
        self.assertEqual(list((self.root / 'work').iterdir()), [])

    def test_invalid_cover_is_rejected(self):
        bad = self.root / 'bad.jpg'
        bad.write_bytes(b'not an image')
        with self.assertRaises(Exception):
            tagging.make_cover(bad, self.root / 'out.jpg')


class MetadataTests(unittest.TestCase):
    def test_read_info_whitelist_limits_and_build_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'x.info.json'
            path.write_text(json.dumps({'title': 'P!NK - What About Us (Official Video)\x00', 'channel': 'P!NK', 'upload_date': '20170816',
                                        'formats': [{'url': 'https://secreto'}], 'http_headers': {'Cookie': 'x'}}), encoding='utf-8')
            info = metadata.read_info(path)
            self.assertNotIn('formats', info)
            self.assertNotIn('\x00', info['title'])
            meta = metadata.build_meta('ClU3fctbGls', info)
            self.assertEqual((meta['artist'], meta['track'], meta['year'], meta['album'], meta['source']), ('P!NK', 'What About Us', '2017', '', 'title'))
            self.assertEqual(metadata.tag_values(meta)['youtube_id'], 'ClU3fctbGls')
            path.write_text('[1,2]')
            self.assertIsNone(metadata.read_info(path))
            path.write_text('{')
            self.assertIsNone(metadata.read_info(path))
            self.assertIsNone(metadata.read_info(Path(tmp) / 'ausente.json'))
            path.write_text(json.dumps({'title': 'x', 'artists': ['A', 'B'], 'album': 'Disco', 'release_year': 2019}))
            info = metadata.read_info(path)
            meta = metadata.build_meta('abcdefghijk', info)
            self.assertEqual((meta['artist'], meta['source'], meta['album'], meta['year']), ('A, B', 'youtube', 'Disco', '2019'))

    def test_store_cover_only_accepts_jpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = Path(tmp) / 'g.jpg', Path(tmp) / 'b.jpg'
            good.write_bytes(b'\xff\xd8\xff rest')
            bad.write_bytes(b'GIF89a')
            self.assertTrue(metadata.store_cover(good, Path(tmp) / 'covers', 'abcdefghijk'))
            self.assertFalse(metadata.store_cover(bad, Path(tmp) / 'covers', 'lmnopqrstuv'))
            self.assertEqual([p.name for p in (Path(tmp) / 'covers').iterdir()], ['abcdefghijk.jpg'])


if __name__ == '__main__':
    unittest.main()

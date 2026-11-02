import unittest
from backend.artist import clean_track, infer, primary


class ArtistTests(unittest.TestCase):
    def test_title_pattern_with_noise_and_featuring(self):
        cases = [
            ('P!nk - Try (Official Video)', 'P!NK', 'P!nk', 'P!nk', 'Try'),
            ('Calvin Harris, Rihanna - This Is What You Came For (Official Video)', '', 'Calvin Harris, Rihanna', 'Calvin Harris', 'This Is What You Came For'),
            ('Years & Years - King (Official Video)', '', 'Years & Years', 'Years & Years', 'King'),
            ('Timbaland - Apologize ft. OneRepublic', '', 'Timbaland ft. OneRepublic', 'Timbaland', 'Apologize'),
            ('Bebe Rexha - The Way I Are (Dance With Somebody) feat. Lil Wayne [Official Music Video]', '', 'Bebe Rexha ft. Lil Wayne', 'Bebe Rexha', 'The Way I Are (Dance With Somebody)'),
            ('The Weeknd & Ariana Grande - Save Your Tears (Remix) (Official Video)', '', 'The Weeknd & Ariana Grande', 'The Weeknd & Ariana Grande', 'Save Your Tears (Remix)'),
        ]
        for title, channel, artist, main, track in cases:
            got = infer(title, channel)
            self.assertEqual((got['artist'], got['artist_primary'], got['track'], got['source']), (artist, main, track, 'title'), title)

    def test_channel_fallback_known_artist_and_nothing(self):
        self.assertEqual(infer('Sem hífen', 'Canal Foo - Topic')['artist'], 'Canal Foo')
        self.assertEqual(infer('Sem hífen', 'Canal Foo - Topic')['source'], 'channel')
        self.assertEqual(infer('Artista - Faixa', '', 'Artista', 'youtube')['track'], 'Faixa')
        self.assertEqual(infer('Outro - Faixa', '', 'Artista', 'tags')['track'], 'Outro - Faixa')
        empty = infer('Só título', '')
        self.assertEqual((empty['artist'], empty['source'], empty['track']), ('', '', 'Só título'))

    def test_helpers_keep_meaningful_brackets(self):
        self.assertEqual(clean_track('Song (Ao Vivo) [Lyric Video]'), 'Song (Ao Vivo)')
        self.assertEqual(primary('A ft. B'), 'A')
        self.assertEqual(primary('Earth, Wind & Fire'), 'Earth')


if __name__ == '__main__':
    unittest.main()

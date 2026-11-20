import unittest

from clipwatcher.publish import post_text


class PostTextTest(unittest.TestCase):
    stream_info = {"creator": "kaicenat", "game": "Grand Theft Auto V"}

    def test_hashtags_respect_platform_limits_and_are_unique(self):
        for platform, limit in post_text.MAX_HASHTAGS.items():
            hashtags = post_text.pick_hashtags(self.stream_info, "#gaming #shorts", platform)
            self.assertLessEqual(len(hashtags), limit)
            self.assertEqual(len(hashtags), len({tag.lower() for tag in hashtags}))

    def test_game_and_creator_tags_come_first(self):
        hashtags = post_text.pick_hashtags(self.stream_info, "", "default")
        self.assertEqual(hashtags[:4], ["#gta5", "#gtav", "#kaicenat", "#kaicenatclips"])

    def test_caption_has_credit_and_alias(self):
        caption = post_text.build_caption("CHAT WAS NOT READY", "https://twitch.tv/kaicenat",
                                          "#shorts", self.stream_info, "instagram")
        self.assertIn("🎮 Kai Cenat playing Grand Theft Auto V", caption)
        self.assertIn("🎥 Credit: https://twitch.tv/kaicenat", caption)

    def test_youtube_title(self):
        title = post_text.youtube_title("HE REALLY DID IT", self.stream_info)
        self.assertEqual(title, "He really did it | Kai Cenat #Shorts")


if __name__ == "__main__":
    unittest.main()

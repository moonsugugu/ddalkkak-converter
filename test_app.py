import unittest
from app import popup_position, menu_choices
from pathlib import Path


class PopupPlacementTests(unittest.TestCase):
    def test_frequent_actions_and_compatible_favorites(self):
        paths=[Path('photo.jpg')]
        choices,_=menu_choices(paths,{})
        self.assertEqual(choices[:3],['pdf','png','compress'])
        choices,_=menu_choices(paths,{'usage':{'.jpg:ocr_txt':5,'.jpg:webp':2}})
        self.assertEqual(choices[:2],['ocr_txt','webp'])
        choices,presets=menu_choices(paths,{'presets':[{'name':'작게','target':'size','options':{'max_mb':1}}]})
        self.assertEqual(choices[0],'fav:0')
        self.assertEqual(menu_choices([Path('movie.mp4')],{'presets':list(presets.values())})[0][0],'fav:0')
        self.assertFalse(menu_choices([Path('sound.wav')],{'presets':list(presets.values())})[1])

    def test_centered_on_cursor(self):
        self.assertEqual(popup_position((1000, 600), (0, 0, 1920, 1040)), (770, 370))

    def test_clamped_inside_work_area(self):
        self.assertEqual(popup_position((1919, 1039), (0, 0, 1920, 1040)), (1460, 580))
        self.assertEqual(popup_position((1, 1), (0, 0, 1920, 1040)), (0, 0))

    def test_negative_monitor_coordinates(self):
        self.assertEqual(popup_position((-1900, -100), (-1920, -200, 0, 880)), (-1920, -200))


if __name__ == '__main__':
    unittest.main()

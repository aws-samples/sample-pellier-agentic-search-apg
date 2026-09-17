"""Keep the guide export lossless at the executable and navigation boundaries."""
import unittest
from sync_workshop_guides import parse


class GuideParserTests(unittest.TestCase):
    def test_nested_coaching_and_code_are_not_treated_as_directives(self):
        code = 'printf "%s\\n" "::::"\n# code heading\n'
        nodes = parse('::::expand{header="Hint"}\n```bash\n' + code + '```\n::::')
        self.assertEqual(nodes[0]['kind'], 'expand')
        self.assertEqual(nodes[0]['children'][0]['text'], '```bash\n' + code + '```')

    def test_tables_and_heading_anchors_survive(self):
        nodes = parse('## Steps\n| Tool | Evidence |\n|---|---|\n| `check_inventory` | Current stock |\n## Steps')
        self.assertEqual(nodes[0]['id'], 'steps')
        self.assertEqual(nodes[1]['rows'], [['`check_inventory`', 'Current stock']])
        self.assertEqual(nodes[2]['id'], 'steps-2')

    def test_tabs_keep_manual_and_coaching_paths_separate(self):
        nodes = parse('::::tabs{variant="container"}\n:::tab{id="manual" label="Manual path"}\nEdit the marked block.\n:::\n:::tab{id="coach" label="Coach"}\nAsk for a hint.\n:::\n::::')
        self.assertEqual([n['title'] for n in nodes[0]['children']], ['Manual path', 'Coach'])

    def test_invalid_container_cannot_silently_hide_required_work(self):
        for text in ['::::expand{header="Hint"}\nMissing close', ':::']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)


if __name__ == '__main__':
    unittest.main()

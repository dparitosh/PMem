import unittest
from backend.services.unified_data_import import FileParser, FileType

class TestFileParserXMI(unittest.TestCase):
    def test_parse_xmi(self):
        # Use a simple XMI content (could be anything, parser is mocked)
        fake_xmi = b'<XMI><Class name="TestClass" id="1"/><Attribute name="testAttr" id="2"/></XMI>'
        rows, stats = FileParser.parse(fake_xmi, FileType.XMI)
        print("Parsed Rows:", rows)
        print("Stats:", stats)
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 1)
        self.assertIn('label', rows[0])
        self.assertIn('name', rows[0])
        self.assertIn('row_count', stats)
        self.assertIn('relationships', stats)
        self.assertEqual(stats['relationships']['relationship_count'], 1)

if __name__ == '__main__':
    unittest.main()
import unittest
from backend.services.unified_data_import import FileParser, FileType

class TestFileParserXMI(unittest.TestCase):
    def test_parse_xmi(self):
        # Use a simple XMI content (could be anything, parser is mocked)
        fake_xmi = b'<XMI><Class name="TestClass" id="1"/><Attribute name="testAttr" id="2"/></XMI>'
        rows, stats = FileParser.parse(fake_xmi, FileType.XMI)
        print("Parsed Rows:", rows)
        print("Stats:", stats)
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 1)
        self.assertIn('label', rows[0])
        self.assertIn('name', rows[0])
        self.assertIn('row_count', stats)
        self.assertIn('relationships', stats)
        self.assertEqual(stats['relationships']['relationship_count'], 1)

if __name__ == '__main__':
    unittest.main()


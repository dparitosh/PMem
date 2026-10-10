import unittest
from backend.Services.unified_data_import import FileParser, FileType


class TestFileParserXMI(unittest.TestCase):
    def test_parse_xmi(self):
        source = b'<x:XMI xmlns:x="http://www.omg.org/XMI" xmlns:uml="http://www.omg.org/spec/UML/20131001"><packagedElement x:id="class1" x:type="uml:Class" name="TestClass"/></x:XMI>'
        rows, stats = FileParser.parse(source, FileType.XMI)
        self.assertNotIn('error', stats)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'TestClass')
        self.assertIn('row_count', stats)
        self.assertIsInstance(stats['relationships']['relationship_count'], int)


if __name__ == '__main__':
    unittest.main()

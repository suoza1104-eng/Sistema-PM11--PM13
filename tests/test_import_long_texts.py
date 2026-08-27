import unittest

from core.import_service import parse_operation_sheets


class _WorkbookStub:
    def __init__(self, rows):
        self.rows = rows

    def read_sheet(self, _sheet_name):
        return self.rows

    @staticmethod
    def _normalize_name(value):
        return str(value).lower().replace(' ', '')


class TestLongTextImport(unittest.TestCase):
    @staticmethod
    def _rows():
        return [
            ['OPERAÇÃO', None, None, None, None, None, None, None],
            ['Identificador', 'Texto breve', 'OPERAÇÃO', 'LOCAL INSTAL',
             'EQUIPAMENTO', 'oper', 'suboper', 'Texto '],
            [1, 'TÍTULO', 'TÍTULO', 'LOCAL-1', None, '0010', None, None],
            [1, 'TÍTULO', 'MECÂNICO SOLDADOR OU SOLDADOR', 'LOCAL-1',
             None, '0010', '0010', 'NÃO SE APLICA'],
            [1, 'TÍTULO', 'ATIVIDADE', 'LOCAL-1', None, '0020', None,
             'PROCEDIMENTO'],
        ]

    def assert_expected_texts(self, texts):
        self.assertEqual(
            [(row['operation_code'], row['suboperation_code'], row['text'])
             for row in texts],
            [
                ('0010', '', ''),
                ('0010', '0010', 'NÃO SE APLICA'),
                ('0020', '', 'PROCEDIMENTO'),
            ],
        )

    def test_plain_text_header_and_empty_0010_placeholder(self):
        _, texts = parse_operation_sheets(
            _WorkbookStub(self._rows()), ['TEXTO LONGO'])

        self.assert_expected_texts(texts)

    def test_recovers_legacy_ambiguous_column_mapping(self):
        # Old cached JS selected descriptive OPERAÇÃO as the code and Texto
        # breve as the procedure. The backend must recover `oper` and `Texto`.
        legacy_mapping = {
            'lt_sheet_name': 'TEXTO LONGO',
            'long_texts': {
                'legacy_identifier': 0,
                'operation_code': 2,
                'suboperation_code': 6,
                'text': 1,
            },
        }
        _, texts = parse_operation_sheets(
            _WorkbookStub(self._rows()), ['TEXTO LONGO'], legacy_mapping)

        self.assert_expected_texts(texts)

    def test_preserves_textual_identifier_in_operation_and_long_text_sheets(self):
        identifier = 'EQ.01-A/SETOR#2'
        text_rows = self._rows()
        for row in text_rows[2:]:
            row[0] = identifier
        _, texts = parse_operation_sheets(
            _WorkbookStub(text_rows), ['TEXTO LONGO'], selected_entities=['long_texts'])
        self.assertTrue(texts)
        self.assertEqual({row['legacy_identifier'] for row in texts}, {identifier})

        operation_rows = [
            ['Identificador', 'OPER', 'Texto breve', 'Centro de trabalho'],
            [identifier, '0010', 'Atividade', 'MEC01'],
        ]
        operations, _ = parse_operation_sheets(
            _WorkbookStub(operation_rows), ['OPERAÇÕES'], selected_entities=['operations'])
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]['legacy_identifier'], identifier)


if __name__ == '__main__':
    unittest.main()

import json
import unittest

from core.long_text_structure import (
    MODE_FREE, MODE_MIXED, MODE_STRUCTURED,
    detect_structure, materialize_record, render_nodes,
)


class TestLongTextStructure(unittest.TestCase):
    def test_recognizes_common_numbering_variants(self):
        text = (
            '1- SENSOR DE SUBVELOCIDADE\n'
            '1.1. texto A\n'
            '1.2 texto B\n'
            '1.3.texto C\n'
            '1.4 - texto D\n'
            '1.5-texto E\n'
            '1.6_texto F\n'
            '1.7   texto G\n'
            '1.8\ttexto H'
        )
        result = detect_structure(text)
        self.assertEqual(result['mode'], MODE_STRUCTURED)
        self.assertEqual(
            result['rendered_text'],
            '1 SENSOR DE SUBVELOCIDADE\n'
            '1.1 texto A\n1.2 texto B\n1.3 texto C\n1.4 texto D\n'
            '1.5 texto E\n1.6 texto F\n1.7 texto G\n1.8 texto H'
        )

    def test_free_text_is_never_numbered(self):
        text = 'REALIZAR INSPEÇÃO VISUAL.\nVERIFICAR CABOS.\nREALIZAR LIMPEZA EXTERNA.'
        result = detect_structure(text)
        self.assertEqual(result['mode'], MODE_FREE)
        self.assertEqual(result['rendered_text'], text)
        self.assertIsNone(result['structure_json'])

    def test_materialize_uses_original_text_when_legacy_rendered_text_is_empty(self):
        record = {
            'text': '',
            'structure_mode': MODE_FREE,
            'structure_json': None,
            'source_text_original': 'NÃO SE APLICA',
        }
        self.assertEqual(materialize_record(record), 'NÃO SE APLICA')

    def test_measurements_at_line_start_are_not_false_topics(self):
        text = '1.1 KW\n2.5 MM\n3.5 BAR'
        self.assertEqual(detect_structure(text)['mode'], MODE_FREE)

    def test_mixed_text_keeps_free_paragraphs_unnumbered(self):
        text = 'RECOMENDAÇÕES\n1 RISCO DE CORTE\n1.1 USAR LUVA\nOBSERVAÇÃO:\n2 RISCO ELÉTRICO\n2.1 TESTAR AUSÊNCIA DE TENSÃO'
        result = detect_structure(text)
        self.assertEqual(result['mode'], MODE_MIXED)
        self.assertTrue(result['rendered_text'].startswith('RECOMENDAÇÕES\n1 RISCO DE CORTE'))
        self.assertIn('\nOBSERVAÇÃO:\n2 RISCO ELÉTRICO', result['rendered_text'])

    def test_structured_text_preserves_internal_blank_lines(self):
        text = '1 ETAPA A\n\n1.1 DETALHE A\n\n2 ETAPA B'
        result = detect_structure(text)
        self.assertEqual(result['rendered_text'], text)
        nodes = json.loads(result['structure_json'])
        self.assertEqual([node['text'] for node in nodes if node['type'] == 'free'], ['', ''])
        self.assertEqual(
            materialize_record({
                'text': result['rendered_text'],
                'structure_mode': result['mode'],
                'structure_json': result['structure_json'],
            }),
            text,
        )

    def test_structured_text_preserves_outer_blank_lines(self):
        text = '\n1 ETAPA A\n1.1 DETALHE A\n2 ETAPA B\n'
        result = detect_structure(text)
        self.assertEqual(result['rendered_text'], text)
        self.assertEqual(materialize_record({
            'text': result['rendered_text'],
            'structure_mode': result['mode'],
            'structure_json': result['structure_json'],
        }), text)

    def test_old_structured_json_recovers_blank_lines_from_saved_text(self):
        compact = detect_structure('1 ETAPA A\n1.1 DETALHE A\n2 ETAPA B')
        spaced = '1 ETAPA A\n\n1.1 DETALHE A\n\n2 ETAPA B'
        record = {
            'text': spaced,
            'structure_mode': compact['mode'],
            'structure_json': compact['structure_json'],
        }
        self.assertEqual(materialize_record(record), spaced)

    def test_numbering_is_materialized_after_reorder_delete(self):
        result = detect_structure('1 BLOCO A\n1.1 A1\n2 BLOCO B\n2.1 B1')
        nodes = json.loads(result['structure_json'])
        # Remove first block (A + A1). B must become block 1 automatically.
        nodes = nodes[2:]
        self.assertEqual(render_nodes(nodes), '1 BLOCO B\n1.1 B1')
        record = {'text': 'stale', 'structure_mode': MODE_STRUCTURED, 'structure_json': json.dumps(nodes)}
        self.assertEqual(materialize_record(record), '1 BLOCO B\n1.1 B1')

    def test_wrapped_numbered_instructions_become_topics_and_subtopics(self):
        text = (
            '1- SENSOR DE SUBVELOCIDADE\n'
            '1.1 REALIZAR LIMPEZA UTILIZANDO SOPRADOR\n'
            'ELÉTRICO/AR COMPRIMIDO, PINCEL E TOALHAS;\n'
            '1.2 REALIZAR A DESMONTAGEM DOS TERMINAIS DE ALIMENTAÇÃO,\n'
            'RETIRANDO OS PARAFUSOS DE PROTEÇÃO.\n'
            '1.3 VERIFICAR CONEXÕES.\n\n'
            '## ( ) EXECUTADO ( ) NÃO EXECUTADO'
        )
        result = detect_structure(text)
        nodes = json.loads(result['structure_json'])
        topics = [node for node in nodes if node['type'] == 'topic']
        self.assertEqual([node['level'] for node in topics], [1, 2, 2, 2])
        self.assertEqual(len(topics), 4)
        self.assertIn('SOPRADOR ELÉTRICO/AR COMPRIMIDO', topics[1]['text'])
        self.assertIn('ALIMENTAÇÃO, RETIRANDO OS PARAFUSOS', topics[2]['text'])
        self.assertEqual(nodes[-1]['type'], 'free')
        self.assertTrue(nodes[-1]['text'].startswith('##'))

    def test_numbering_can_restart_inside_the_same_long_text(self):
        nodes = [
            {'type': 'topic', 'level': 1, 'text': 'PROCEDIMENTO'},
            {'type': 'topic', 'level': 2, 'text': 'ÚLTIMA ETAPA'},
            {'type': 'free', 'level': 0, 'text': 'RECOMENDAÇÕES DE SEGURANÇA'},
            {'type': 'topic', 'level': 1, 'text': 'RISCO DE CORTE', 'restart_numbering': True},
            {'type': 'topic', 'level': 1, 'text': 'RISCO DE PROJEÇÃO'},
        ]
        self.assertEqual(
            render_nodes(nodes),
            '1 PROCEDIMENTO\n1.1 ÚLTIMA ETAPA\nRECOMENDAÇÕES DE SEGURANÇA\n1 RISCO DE CORTE\n2 RISCO DE PROJEÇÃO'
        )
        record = {'structure_mode': MODE_MIXED, 'structure_json': json.dumps(nodes), 'text': ''}
        self.assertIn('\n1 RISCO DE CORTE\n2 RISCO DE PROJEÇÃO', materialize_record(record))

    def test_numbering_can_resume_the_sequence_before_restart(self):
        nodes = [
            {'type': 'topic', 'level': 1, 'text': 'ETAPA PRINCIPAL'},
            {'type': 'topic', 'level': 2, 'text': 'ETAPA CINCO'},
            {'type': 'topic', 'level': 2, 'text': 'ETAPA SEIS'},
            {'type': 'free', 'level': 0, 'text': 'SEGURANÇA'},
            {'type': 'topic', 'level': 1, 'text': 'RISCO UM', 'restart_numbering': True},
            {'type': 'topic', 'level': 1, 'text': 'RISCO DOIS'},
            {'type': 'free', 'level': 0, 'text': 'PROCEDIMENTO'},
            {'type': 'topic', 'level': 2, 'text': 'ETAPA SETE', 'resume_numbering': True},
        ]
        rendered = render_nodes(nodes)
        self.assertIn('1 RISCO UM\n2 RISCO DOIS', rendered)
        self.assertTrue(rendered.endswith('1.3 ETAPA SETE'))


if __name__ == '__main__':
    unittest.main()

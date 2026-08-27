import datetime
import unittest

from core_pm11.balance import _occurrence_indices, _working_dates
from core_pm11.plans_util import parse_offset_from_text


class TestPM11CalendarOffsets(unittest.TestCase):
    def setUp(self):
        self.anchor = datetime.date(2026, 8, 31)  # Monday
        self.dates = _working_dates(self.anchor, 30)

    def index_for(self, code):
        offset = parse_offset_from_text(code=code)
        return _occurrence_indices(self.dates, self.anchor, offset, 'MES', 1)[0]

    def test_week_and_sap_weekday_map_to_working_day_columns(self):
        self.assertEqual(self.index_for('1S2'), 0)   # SEG1
        self.assertEqual(self.index_for('1S3'), 1)   # TER1
        self.assertEqual(self.index_for('2S2'), 5)   # SEG2
        self.assertEqual(self.index_for('2S3'), 6)   # TER2
        self.assertEqual(self.index_for('3S4'), 12)  # QUA3
        self.assertEqual(self.index_for('4S6'), 19)  # SEX4

    def test_monthly_offsets_cover_every_weekday_without_weekend_gaps(self):
        indices = {self.index_for(f'{week}S{sap_day}') for week in range(1, 5) for sap_day in range(2, 7)}
        self.assertEqual(indices, set(range(20)))


if __name__ == '__main__':
    unittest.main()

import datetime
import re


_DAYS = ('Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo')


def parse_offset_from_text(description='', code=''):
    """Return the 1-based calendar offset encoded as nSd, or None."""
    for value in (description, code):
        match = re.search(r'(?<!\d)(\d+)\s*S\s*([2-6])(?!\d)', str(value or ''), re.IGNORECASE)
        if match:
            week, day = map(int, match.groups())
            if week >= 1:
                # PM11 uses SAP weekday numbers: 2=Monday ... 6=Friday.
                # offset_days remains a 1-based calendar offset from Monday.
                return (week - 1) * 7 + (day - 1)
    return None


def get_plan_dates_and_labels(anchor_date_str, offset_days, description='', code=''):
    if offset_days in (None, ''):
        offset_days = parse_offset_from_text(description, code)
    if offset_days in (None, ''):
        return {'day_of_week_label': '', 'calculated_start_date': ''}
    try:
        offset = int(offset_days)
        if offset < 1:
            raise ValueError
        anchor = datetime.date.fromisoformat(str(anchor_date_str))
        logical_delta = offset - 1
        working_delta = (logical_delta // 7) * 5 + min(logical_delta % 7, 5)
        start = anchor
        for _ in range(working_delta):
            start += datetime.timedelta(days=1)
            while start.weekday() >= 5:
                start += datetime.timedelta(days=1)
    except (TypeError, ValueError):
        return {'day_of_week_label': '', 'calculated_start_date': ''}
    week = ((offset - 1) // 7) + 1
    day_index = (offset - 1) % 7
    sap_day = day_index + 2
    return {
        'day_of_week_label': f'{_DAYS[day_index]} ({week}S{sap_day})',
        'calculated_start_date': start.strftime('%d/%m/%Y')
    }

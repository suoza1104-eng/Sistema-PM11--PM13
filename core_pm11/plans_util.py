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
        start = datetime.date.fromisoformat(str(anchor_date_str)) + datetime.timedelta(days=offset - 1)
    except (TypeError, ValueError):
        return {'day_of_week_label': '', 'calculated_start_date': ''}
    week = ((offset - 1) // 7) + 1
    day_index = start.weekday()
    sap_day = (day_index % 5) + 2
    return {
        'day_of_week_label': f'{_DAYS[day_index]} ({week}S{sap_day})',
        'calculated_start_date': start.strftime('%d/%m/%Y')
    }

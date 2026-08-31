import zipfile
import xml.etree.ElementTree as ET
import os


class XLSXSafetyError(ValueError):
    """Raised when an XLSX is technically valid but unsafe to process locally."""


class XLSXReader:
    """A lightweight, dependency-free reader for Excel (.xlsx) files.

    Safety goals for the local PM13 application:
    - ignore style-only cells / inflated Excel used-ranges;
    - stream worksheet XML instead of loading the whole sheet tree;
    - stop with a friendly error before a malformed/bloated workbook consumes
      enough RAM to freeze the browser/desktop;
    - keep normal corporate workbooks transparent to the caller.
    """

    MAIN_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    # These limits are intentionally generous for a PM13 maintenance workbook.
    # They are protection against accidental million-line tails, not business limits.
    MAX_SHARED_STRINGS = 500_000
    MAX_DATA_ROWS = 50_000
    MAX_EXCEL_ROW_WITH_DATA = 200_000

    def __init__(self, file_path):
        self.file_path = file_path
        self.shared_strings = []
        self.sheets = {}  # name -> worksheet filename
        self._load_metadata()

    @staticmethod
    def _find_zip_name_ci(namelist, target_path):
        target_lower = target_path.lower()
        for name in namelist:
            if name.lower() == target_lower:
                return name
        raise KeyError(f"Arquivo {target_path} não encontrado no ZIP.")

    def _load_shared_strings(self, z, actual_name):
        """Load shared strings in streaming mode with a hard safety cap."""
        strings = []
        ns = self.MAIN_NS
        with z.open(actual_name, 'r') as stream:
            for event, elem in ET.iterparse(stream, events=('end',)):
                if elem.tag != f'{ns}si':
                    continue
                texts = elem.findall(f'.//{ns}t')
                strings.append(''.join(t.text or '' for t in texts))
                if len(strings) > self.MAX_SHARED_STRINGS:
                    raise XLSXSafetyError(
                        'A planilha possui mais de '
                        f'{self.MAX_SHARED_STRINGS:,} textos/células compartilhados. '
                        'Isso normalmente indica uma aba inflada com centenas de milhares '
                        'de linhas residuais. Limpe as linhas/colunas excedentes no Excel, '
                        'salve uma nova cópia e tente importar novamente.'
                    )
                elem.clear()
        return strings

    def _load_metadata(self):
        """Loads sheet relationships and shared strings."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {self.file_path}")

        try:
            with zipfile.ZipFile(self.file_path, 'r') as z:
                namelist = z.namelist()

                def read_zip_file_ci(target_path):
                    return z.read(self._find_zip_name_ci(namelist, target_path))

                # 1. Load shared strings without materializing the entire XML tree.
                self.shared_strings = []
                try:
                    ss_name = self._find_zip_name_ci(namelist, 'xl/sharedStrings.xml')
                    self.shared_strings = self._load_shared_strings(z, ss_name)
                except KeyError:
                    pass

                # 2. Load workbook structure to match Sheet Name -> Rel ID.
                workbook_xml = read_zip_file_ci('xl/workbook.xml')
                wb_root = ET.fromstring(workbook_xml)
                ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
                      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

                sheets_elements = wb_root.findall('.//ns:sheet', ns)
                sheet_rels = {}
                for sheet in sheets_elements:
                    name = sheet.attrib.get('name')
                    r_id = sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                    if name and r_id:
                        sheet_rels[r_id] = name

                # 3. Load worksheet file mappings.
                rels_xml = read_zip_file_ci('xl/_rels/workbook.xml.rels')
                rels_root = ET.fromstring(rels_xml)
                rels_ns = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}

                for rel in rels_root.findall('.//rel:Relationship', rels_ns):
                    rid = rel.attrib.get('Id')
                    target = rel.attrib.get('Target')
                    if rid in sheet_rels and target:
                        if target.startswith('/'):
                            # Package-absolute target (e.g. openpyxl/LibreOffice writers).
                            target = target.lstrip('/')
                        elif not target.startswith('xl/'):
                            # Target relative to the part that owns this .rels file (xl/).
                            target = 'xl/' + target
                        self.sheets[sheet_rels[rid]] = target
        except zipfile.BadZipFile as exc:
            raise ValueError('O arquivo não é um XLSX válido ou está corrompido.') from exc

    def get_sheet_names(self):
        return list(self.sheets.keys())

    def _normalize_name(self, name):
        import unicodedata
        n = name.lower().strip().replace(" ", "").replace(".", "").replace("-", "")
        return "".join(c for c in unicodedata.normalize('NFD', n) if unicodedata.category(c) != 'Mn')

    def find_sheet_path(self, target_name):
        norm_target = self._normalize_name(target_name)
        for name, path in self.sheets.items():
            if self._normalize_name(name) == norm_target:
                return path
        return None

    @staticmethod
    def _col_letter_to_index(col_str):
        idx = 0
        for char in col_str:
            idx = idx * 26 + (ord(char.upper()) - 64)
        return idx - 1

    @classmethod
    def _parse_ref(cls, ref_str):
        col_str = ""
        row_str = ""
        for char in ref_str or '':
            if char.isalpha():
                col_str += char
            elif char.isdigit():
                row_str += char
        if not col_str or not row_str:
            return None, None
        return int(row_str) - 1, cls._col_letter_to_index(col_str)

    def _parse_cell_value(self, cell):
        ns = self.MAIN_NS
        t = cell.attrib.get('t')
        val = None
        has_payload = False

        if t == 'inlineStr':
            texts = cell.findall(f'.//{ns}t')
            if texts:
                has_payload = True
                val = ''.join(x.text or '' for x in texts)
        else:
            val_el = cell.find(f'{ns}v')
            if val_el is not None:
                has_payload = True
                val_str = val_el.text
                if val_str is None:
                    val = None
                elif t == 's':
                    try:
                        val = self.shared_strings[int(val_str)]
                    except (IndexError, ValueError):
                        val = val_str
                elif t in ('str', 'e'):
                    val = val_str
                else:
                    try:
                        val = float(val_str) if '.' in val_str else int(val_str)
                    except (TypeError, ValueError):
                        val = val_str

        # A style-only cell such as <c r="E1048424" s="37"/> is not data.
        return has_payload, val

    def read_sheet(self, sheet_name, max_rows=None, max_data_rows=None,
                   max_excel_row_with_data=None):
        """Reads a sheet and returns rows as lists of cell values.

        ``max_rows`` is used for header-only inspection and deliberately bypasses
        full-import safety thresholds after that row. Full imports use generous
        limits so a million-row accidental tail becomes a clear validation error
        instead of a memory spike / browser crash.
        """
        sheet_path = self.find_sheet_path(sheet_name)
        if not sheet_path:
            raise ValueError(f"Planilha não encontrada: {sheet_name}")

        if max_data_rows is None:
            max_data_rows = self.MAX_DATA_ROWS
        if max_excel_row_with_data is None:
            max_excel_row_with_data = self.MAX_EXCEL_ROW_WITH_DATA

        rows_data = {}
        max_data_row = -1
        data_row_count = 0
        ns = self.MAIN_NS

        with zipfile.ZipFile(self.file_path, 'r') as z:
            actual_name = self._find_zip_name_ci(z.namelist(), sheet_path)
            with z.open(actual_name, 'r') as stream:
                for event, elem in ET.iterparse(stream, events=('end',)):
                    if elem.tag != f'{ns}row':
                        continue

                    row_num_raw = elem.attrib.get('r')
                    try:
                        row_idx = int(row_num_raw) - 1 if row_num_raw else (max_data_row + 1)
                    except ValueError:
                        row_idx = max_data_row + 1

                    if max_rows is not None and row_idx >= int(max_rows):
                        elem.clear()
                        break

                    row_cells = []
                    for cell in elem.findall(f'{ns}c'):
                        ref = cell.attrib.get('r')
                        _, c_idx = self._parse_ref(ref)
                        if c_idx is None:
                            continue
                        has_payload, val = self._parse_cell_value(cell)
                        if not has_payload:
                            continue
                        row_cells.append((c_idx, val))

                    if row_cells:
                        data_row_count += 1
                        excel_row = row_idx + 1
                        if max_rows is None and excel_row > int(max_excel_row_with_data):
                            raise XLSXSafetyError(
                                f"A aba '{sheet_name}' possui conteúdo na linha {excel_row:,}, muito além "
                                'da faixa esperada para uma carga PM13. Isso costuma ocorrer quando a '
                                'planilha possui uma cauda residual/inflada. Exclua as linhas excedentes '
                                'no Excel (não apenas o conteúdo), salve uma nova cópia e tente novamente.'
                            )
                        if max_rows is None and data_row_count > int(max_data_rows):
                            raise XLSXSafetyError(
                                f"A aba '{sheet_name}' ultrapassou {int(max_data_rows):,} linhas com dados. "
                                'A importação foi interrompida preventivamente para evitar consumo excessivo '
                                'de memória. Verifique se existem milhares de linhas residuais, fórmulas ou '
                                'valores preenchidos abaixo da área real da planilha.'
                            )

                        row_cells.sort(key=lambda x: x[0])
                        max_c = row_cells[-1][0]
                        full_row = [None] * (max_c + 1)
                        for c_idx, value in row_cells:
                            full_row[c_idx] = value
                        rows_data[row_idx] = full_row
                        if row_idx > max_data_row:
                            max_data_row = row_idx

                    elem.clear()

        if not rows_data:
            return []

        return [rows_data.get(r, []) for r in range(max_data_row + 1)]

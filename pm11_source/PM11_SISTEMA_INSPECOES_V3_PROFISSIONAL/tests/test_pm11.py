import os, sys, unittest, tempfile
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,ROOT)
from core.migrations import run_migrations
from core import models, balance, import_export

class PM11Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_migrations()
    def setUp(self):
        self.p=models.create_project({'name':'__TEST_PM11__'})
    def tearDown(self):
        try: models.set_project_lock(self.p['id'],False)
        except: pass
        try: models.delete_project(self.p['id'])
        except: pass
    def plan(self,suffix='01S',desc='PLANO TESTE'):
        return models.create_plan(self.p['id'],{'center_code':'U','process_code':'R','type_code':'I','line_code':'ST3','subarea_code':'DFS','suffix':suffix,'description':desc,'cycle_code':suffix if suffix in ('01S','01D','01M') else '01S'})
    def test_plan_item_characteristic_and_condition_f(self):
        pl=self.plan()
        self.assertEqual(pl['code'],'URIST3DFS01S')
        it=models.create_item(self.p['id'],{'plan_id':pl['id'],'equipment_code':'100','route':'5','description':'INSPEÇÃO MOTOR','inspection_minutes':15,'condition_code':'F'})
        self.assertEqual(it['route'],'0005');self.assertEqual(it['condition_code'],'F')
        ch=models.create_characteristic(self.p['id'],{'item_id':it['id'],'characteristic_type':'QUANTITA','description':'TEMPERATURA','method_code':'PIROM','unit_code':'°C','decimals':1,'lower_limit':0,'upper_limit':80})
        self.assertEqual(ch['unit_code'],'°C')
    def test_qualitative_clears_numeric(self):
        pl=self.plan('01D','DIARIO')
        it=models.create_item(self.p['id'],{'plan_id':pl['id'],'equipment_code':'100','description':'INSPEÇÃO FIXAÇÃO','inspection_minutes':5})
        ch=models.create_characteristic(self.p['id'],{'item_id':it['id'],'characteristic_type':'QUALITAT','description':'FIXAÇÃO','method_code':'VISUAL','unit_code':'mm','reference_value':1})
        self.assertEqual(ch['unit_code'],'');self.assertIsNone(ch['reference_value'])
    def test_item_and_package_templates(self):
        pl=self.plan()
        it=models.create_item(self.p['id'],{'plan_id':pl['id'],'equipment_code':'C101','route':'0101','description':'INSPEÇÃO MOTOR','inspection_minutes':15})
        models.create_characteristic(self.p['id'],{'item_id':it['id'],'characteristic_type':'QUALITAT','description':'FIXAÇÃO','method_code':'VISUAL'})
        t=models.save_item_template_from_item(self.p['id'],it['id'],'MOTOR PADRÃO')
        created=models.apply_item_template(self.p['id'],t['id'],pl['id'],'C102','0201')
        self.assertEqual(created['item']['route'],'0201')
        pkg=models.save_plan_as_package_template(self.p['id'],pl['id'],'PACOTE PLANO')
        r=models.apply_equipment_template(self.p['id'],pkg['id'],'C103','0301',plan_id_override=pl['id'])
        self.assertGreaterEqual(r['items_created'],2)
    def test_clone_plan_with_children(self):
        pl=self.plan();it=models.create_item(self.p['id'],{'plan_id':pl['id'],'equipment_code':'X','route':'0001','description':'INSPEÇÃO','inspection_minutes':10});models.create_characteristic(self.p['id'],{'item_id':it['id'],'characteristic_type':'QUALITAT','description':'ESTADO','method_code':'VISUAL'})
        cp=models.clone_plan(self.p['id'],pl['id'],True,new_code='URIST3DFS02S',new_description='CÓPIA')
        its=[x for x in models.list_items(self.p['id']) if x['plan_id']==cp['plan']['id']]
        self.assertEqual(len(its),1);self.assertEqual(len(models.list_characteristics(self.p['id'],item_id=its[0]['id'])),1)
    def test_balance_target_and_filters(self):
        pl=self.plan()
        for n in range(6):models.create_item(self.p['id'],{'plan_id':pl['id'],'equipment_code':'M'+str(n),'route':str(n+1),'description':'INSPEÇÃO MOTOR '+str(n),'inspection_minutes':30,'gpm':'041' if n<3 else '042'})
        b=balance.auto_balance_preview(self.p['id'],days=30,target_minutes=60,filters={'gpm':'041'})
        self.assertEqual(len(b['after']),30);self.assertIn('days_over_target',b['after_metrics']);self.assertTrue(all(x.get('gpm')=='041' for d in b['after'] for x in d['items']))
    def test_project_duplicate_and_lock(self):
        pl=self.plan();models.create_item(self.p['id'],{'plan_id':pl['id'],'equipment_code':'A','description':'INSPEÇÃO A','inspection_minutes':10})
        dup=models.duplicate_project(self.p['id'],'__TEST_DUP__')
        try:
            self.assertEqual(len(models.list_plans(dup['id'])),1);self.assertEqual(len(models.list_items(dup['id'])),1)
            models.set_project_lock(dup['id'],True);self.assertTrue(models.project_is_locked(dup['id']))
        finally:
            models.set_project_lock(dup['id'],False);models.delete_project(dup['id'])
    def test_export_roundtrip_and_merge_renumber(self):
        pl=self.plan('01M','MENSAL');it=models.create_item(self.p['id'],{'plan_id':pl['id'],'equipment_code':'100','route':'0001','description':'INSPEÇÃO REDUTOR','inspection_minutes':20});models.create_characteristic(self.p['id'],{'item_id':it['id'],'characteristic_type':'QUALITAT','description':'VAZAMENTO','method_code':'VISUAL'})
        raw=import_export.export_project(self.p['id']);fd,path=tempfile.mkstemp(suffix='.xlsx');os.close(fd)
        with open(path,'wb') as fh: fh.write(raw)
        dest=models.create_project({'name':'__TEST_DEST__'})
        try:
            # Collision with source identifier 1 must renumber the imported item and preserve its characteristic.
            dp=models.create_plan(dest['id'],{'center_code':'U','process_code':'R','type_code':'I','line_code':'ST3','subarea_code':'AUX','suffix':'001','description':'DEST','cycle_code':'01S'})
            models.create_item(dest['id'],{'plan_id':dp['id'],'equipment_code':'EX','description':'EXISTENTE','inspection_minutes':1,'legacy_identifier':1})
            p=import_export.preview_import(path);self.assertEqual(p['counts'],{'plans':1,'items':1,'characteristics':1})
            r=import_export.confirm_import(dest['id'],path,'MERGE');self.assertEqual(r['stats']['items_created'],1)
            imported=[x for x in models.list_items(dest['id']) if x['description']=='INSPEÇÃO REDUTOR'][0]
            self.assertNotEqual(imported['legacy_identifier'],1);self.assertEqual(len(models.list_characteristics(dest['id'],item_id=imported['id'])),1)
        finally:
            os.remove(path);models.delete_project(dest['id'])
    def test_real_reference_workbook_detection(self):
        path=os.path.join(ROOT,'references','Planos Padrão Área1.xlsx')
        if not os.path.exists(path):self.skipTest('Planilha de referência não encontrada')
        p=import_export.preview_import(path)
        self.assertGreater(p['counts']['plans'],0);self.assertGreater(p['counts']['items'],0);self.assertGreater(p['counts']['characteristics'],0)
        self.assertEqual(p['detection']['plans']['sheet'],'Cod Planos');self.assertEqual(p['detection']['items']['sheet'],'ITENS');self.assertIn('SÍNTESE',p['detection']['characteristics']['sheet'])
        self.assertEqual(p['samples']['characteristics'][0].get('characteristic_type'),'QUALITAT')

if __name__=='__main__':unittest.main()

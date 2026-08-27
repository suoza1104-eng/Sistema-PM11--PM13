const App={projectId:Number(localStorage.getItem('pm11_project_id')||0),view:'dashboard',projects:[],
 async init(){
   try{
     document.querySelectorAll('.menu-item[data-view]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();this.navigate(a.dataset.view)}));
     document.querySelector('#btn-global-undo')?.addEventListener('click',()=>this.undo());
     document.querySelector('#btn-global-redo')?.addEventListener('click',()=>this.redo());
     document.querySelector('#btn-switch-project-top')?.addEventListener('click',()=>this.navigate('projects'));
     document.querySelector('#sidebar-toggle')?.addEventListener('click',()=>document.querySelector('#sidebar')?.classList.toggle('collapsed'));
     document.querySelector('#menu-toggle-btn')?.addEventListener('click',()=>document.querySelector('#sidebar')?.classList.toggle('mobile-open'));
     document.querySelector('#btn-shutdown')?.addEventListener('click',async()=>{if(!confirm('Encerrar o servidor PM11?'))return;try{await API.post('/api/shutdown',{})}catch{};UI.toast('Servidor PM11 encerrado.','warn')});
     document.addEventListener('keydown',e=>{const tag=document.activeElement?.tagName;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!['INPUT','TEXTAREA','SELECT'].includes(tag)){e.preventDefault();this.undo()}if((e.ctrlKey||e.metaKey)&&(e.key.toLowerCase()==='y'||(e.shiftKey&&e.key.toLowerCase()==='z'))&&!['INPUT','TEXTAREA','SELECT'].includes(tag)){e.preventDefault();this.redo()}});
     await this.loadProjects();
     if(!this.projectId&&this.projects[0])this.setProject(this.projects[0].id,false);
     const hash=(location.hash||'#dashboard').replace('#','');
     const valid=['dashboard','plans','items','characteristics','balance','templates','io','settings','projects'];
     await this.navigate(valid.includes(hash)?hash:'dashboard');
   }catch(e){
     console.error('Falha ao iniciar PM11:',e);
     const v=document.querySelector('#view');
     if(v)v.innerHTML=`<div class="errorbox"><b>Erro ao iniciar PM11:</b> ${String(e?.message||e)}</div>`;
   }
 },
 async loadProjects(){this.projects=await API.get('/api/projects');if(this.projectId&&!this.projects.some(p=>p.id===this.projectId))this.projectId=0;this.updateProjectHeader()},
 setProject(id,navigate=true){this.projectId=Number(id);localStorage.setItem('pm11_project_id',this.projectId);this.updateProjectHeader();if(navigate)this.navigate('dashboard')},
 updateProjectHeader(){const p=this.projects.find(x=>x.id===this.projectId);const n=document.querySelector('#active-project-name'),c=document.querySelector('#active-project-items');if(n)n.textContent=p?.name||'Nenhum projeto';if(c)c.textContent=`${p?.items_count||0} itens`},
 async navigate(view){
   let loaderShown=false;
   try{
     if(!this.projectId&&view!=='projects')view='projects';
     this.view=view;location.hash=view;
     document.querySelectorAll('.menu-item[data-view]').forEach(a=>a.classList.toggle('active',a.dataset.view===view));
     const modules={dashboard:window.Dashboard,plans:window.Plans,items:window.Items,characteristics:window.Characteristics,balance:window.Balance,templates:window.Templates,io:window.IO,settings:window.Settings,projects:window.Projects};
     const mod=modules[view];
     if(!mod||typeof mod.render!=='function')throw new Error(`Módulo da tela '${view}' não foi carregado. Faça Ctrl+F5 e confirme os arquivos static/js.`);
     if(!window.UI||typeof UI.showLoader!=='function')throw new Error('Módulo de interface UI não foi carregado corretamente.');
     UI.showLoader('Carregando...');loaderShown=true;
     await mod.render();
   }catch(e){
     console.error(`Erro na tela ${view}:`,e);
     const v=document.querySelector('#view');
     const msg=String(e?.message||e);
     if(v)v.innerHTML=`<div class="section-header-actions pm11-page-head"><div><h1>Erro</h1><p class="subtitle">Não foi possível carregar esta tela.</p></div></div><div class="errorbox"><b>Erro ao carregar:</b> ${window.UI?.esc?UI.esc(msg):msg}</div>`;
     window.UI?.toast?.(msg,'error');
     window.API?.post?.('/api/logs',{context:view,message:`ERRO FRONTEND: ${e?.stack||msg}`}).catch(()=>{});
   }finally{
     if(loaderShown)UI.hideLoader();
     await this.loadProjects().catch(()=>{});
     await this.historyStatus();
   }
 },
 refresh(){return this.navigate(this.view)},
 async historyStatus(){const u=document.querySelector('#btn-global-undo'),r=document.querySelector('#btn-global-redo');if(!this.projectId){if(u)u.disabled=true;if(r)r.disabled=true;return}try{const s=await API.get('/api/history/status');if(u){u.disabled=!s.undo;u.title=s.undo?`Desfazer: ${s.undo}`:'Nada para desfazer'}if(r){r.disabled=!s.redo;r.title=s.redo?`Refazer: ${s.redo}`:'Nada para refazer'}}catch{}},
 async undo(){if(!this.projectId)return;try{const r=await API.post('/api/history/undo',{project_id:this.projectId});UI.toast(r.ok?`Desfeito: ${r.action}`:r.message,r.ok?'ok':'warn');await this.refresh()}catch(e){UI.toast(e.message,'error')}},
 async redo(){if(!this.projectId)return;try{const r=await API.post('/api/history/redo',{project_id:this.projectId});UI.toast(r.ok?`Refeito: ${r.action}`:r.message,r.ok?'ok':'warn');await this.refresh()}catch(e){UI.toast(e.message,'error')}}
};
window.App=App;
window.addEventListener('DOMContentLoaded',()=>App.init());

/* [codex/unknown · op Ali · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14] */
'use strict';
window.ModelReview=(()=>{
  const state={data:null,version:null,filter:'failures',index:0,token:0,row:null,anchor:null};
  const el=id=>document.getElementById(id),txt=(id,v)=>{el(id).textContent=v??'';};
  const labels={missed:'Defect missed',false_rejects:'Good item rejected',unknown:'Item uncertain',detected:'Defect found',good_passed:'Good item passed'};
  function rows(){return (version()?.rows||[]).filter(r=>state.filter==='all'||['missed','false_rejects','unknown'].includes(r.category));}
  function version(){return state.data?.versions.find(v=>v.id===state.version);}
  function controls(){
    const v=version(),list=rows();state.index=Math.min(Math.max(0,state.index),Math.max(0,list.length-1));
    txt('model-position',list.length?`Example ${state.index+1} of ${list.length}`:'No examples');
    el('model-previous').disabled=state.index===0;el('model-next').disabled=state.index>=list.length-1;
    txt('model-note',state.data?.benchmark?.limitations||'');
    el('model-version').value=state.version||'';
    txt('model-bundle',v?.bundle||'Not available');txt('model-device',v?.device||'Not recorded');txt('model-margin',v?.source_label||'See frozen model bundle');txt('model-version-status',v?.ready?'Verified results for every benchmark member.':(v?.issues||[]).join('. '));
    el('model-history').disabled=!list.length;
    return {v,list};
  }
  async function select(){
    const {v,list}=controls(),row=list[state.index],token=++state.token;state.row=row;if(row)state.anchor=row.pick;
    el('model-images').hidden=!row;el('model-empty').hidden=!!row;
    txt('model-empty',!v?.ready?'This version needs a verified evaluation on every benchmark item.': 'No failures in this selection.');
    txt('model-verdict',row?labels[row.category]:'');txt('model-diagnosis',row?.diagnosis||'');
    el('model-verdict').className=row&&['missed','false_rejects'].includes(row.category)?'flagged':'';
    txt('model-explanation',row?.explanation||'No evaluated example selected.');txt('model-diagnosis-detail',row?.diagnosis||'No example');
    if(!row){for(const id of ['model-selected-type','model-score','model-known-type','model-provenance'])txt(id,'—');}
    if(!row)return;
    for(const id of ['model-original','model-crop']){el(id).removeAttribute('src');delete el(id).dataset.source;el(id).hidden=true;}
    for(const id of ['model-selected-type','model-score','model-known-type','model-provenance'])txt(id,'—');
    txt('model-crop-note','Loading crop…');
    try{
      const [run,item]=row.pick.split('/');
      const data=await get('/api/history/item',{run,item});if(token!==state.token)return;
      const c=data.captures.find(c=>c.filename===row.file);
      if(!c)throw new Error('Benchmark capture unavailable');
      const evaluation=data.evaluations.find(e=>e.id===v.id),score=evaluation?.scores[c.id];
      if(!score?.input_verified)throw new Error('Image identity could not be verified');
      setImage('model-original',c.url);
      if(evaluation.crop_policy==='part-top-v2'&&c.bbox){
        const image=el('model-crop');image.onload=()=>{if(token===state.token){image.hidden=false;txt('model-crop-note','');}};
        image.onerror=()=>{if(token===state.token)txt('model-crop-note','Reconstructed crop unavailable');};
        image.src='/api/history/crop?'+new URLSearchParams({run,item,capture:c.id,evaluation:v.id});
      }else txt('model-crop-note','Model crop not recorded');
      const s=row.score,o=row.oracle;
      txt('model-score',s.status==='ok'?`${format(s.score)} / ${format(s.threshold)}`:'No routed score');
      txt('model-selected-type',row.selected_type?human(row.selected_type):'Unknown');
      txt('model-known-type',`${human(row.type)} · ${format(o.score)} / ${format(o.threshold)}`);
      txt('model-provenance',`${row.pick} · ${row.file} · recorded label: ${row.label}`);
      txt('model-bundle',v.bundle);txt('model-device',v.device||'Not recorded');
    }catch(e){if(token===state.token){txt('model-crop-note',e.message);txt('model-diagnosis','Evidence unavailable');}}
  }
  async function load(id){
    try{
      state.data=await get('/api/models/compare',{benchmark:id});
      const versions=state.data.versions;state.version=versions.find(v=>v.id===state.version)?.id||versions.find(v=>v.ready)?.id||versions[0]?.id;
      options(el('model-version'),versions.map(v=>[v.id,v.label]),state.version);
      const tbody=el('model-summary');tbody.replaceChildren();
      for(const v of versions){const tr=document.createElement('tr');tr.append(node('td',v.label.replace('Latest training run','Latest run').replace('Previous version','Previous')));
        if(v.ready){tr.append(node('td',String(v.counts.missed)),node('td',String(v.counts.false_rejects)),node('td',String(v.counts.unknown)));}
        else {const td=node('td','Not compared');td.colSpan=3;td.title=v.issues.join('; ');tr.append(td);}tbody.append(tr);}
      txt('model-benchmark-count',`${state.data.benchmark.members.length} picks · saved-image replay`);
      state.index=0;await select();
    }catch(e){txt('model-empty',e.message);el('model-empty').hidden=false;}
  }
  async function init(){
    try{const data=await get('/api/models/benchmarks');options(el('model-benchmark'),data.benchmarks.map(b=>[b.id,b.name]),data.benchmarks[0]?.id);if(data.benchmarks.length)await load(data.benchmarks[0].id);else txt('model-empty','No benchmark definitions available.');}
    catch(e){txt('model-empty',e.message);}
  }
  el('model-benchmark').onchange=e=>load(e.target.value);
  el('model-version').onchange=e=>{const pick=state.anchor;state.version=e.target.value;let list=rows(),index=list.findIndex(r=>r.pick===pick);if(index<0&&version()?.ready){state.filter='all';el('model-filter').value='all';list=rows();index=list.findIndex(r=>r.pick===pick);}if(index>=0)state.index=index;select();};
  el('model-filter').onchange=e=>{state.filter=e.target.value;state.index=0;select();};
  for(const [id,step] of [['model-previous',-1],['model-next',1]])el(id).onclick=()=>{state.index+=step;select();};
  el('model-detail-page').onchange=e=>{for(const id of ['example','scores','benchmark','eligibility','version'])el('model-detail-'+id).hidden=id!==e.target.value;};
  el('model-details-open').onclick=()=>el('model-dialog').showModal();
  el('model-details-close').onclick=()=>el('model-dialog').close();
  el('model-history').onclick=async()=>{const row=state.row;if(!row)return;const [run,item]=row.pick.split('/');ui.evaluationChoice=state.version;mode('history');await loadRun(run,item);if(ui.mode==='history'&&ui.run===run&&ui.item===item){const capture=ui.detail?.captures?.find(c=>c.filename===row.file);if(capture){ui.selected.set(captureKey(ui.detail),capture.id);render();}}};
  return {init};
})();
ModelReview.init();

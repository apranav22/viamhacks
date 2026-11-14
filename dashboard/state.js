/* [codex/unknown · op Ali · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]
 * Shared telemetry reducer. Decisions never imply successful physical placement. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DashboardState = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  function detector(reason, decision) {
    if (decision !== 'reject') return null;
    if ((reason || '').startsWith('known: tape')) return 'tape';
    if ((reason || '').startsWith('anomaly:')) return 'anomalib';
    return null;
  }
  function frameUrl(event) {
    const f = event.frame;
    if (!f || f.ok === false || !(f.mime || 'image/jpeg').startsWith('image/')) return null;
    return f.url || '/frame/' + encodeURIComponent(f.id) + '?run=' + encodeURIComponent(event.run || '');
  }
  function anomalyStatus(score) {
    if (!score || !score.status) return 'Not evaluated';
    if (score.status !== 'ok') return ({missing:'Unavailable', not_replayed:'Not replayed', unknown_type:'Unknown type', invalid:'Invalid input', source_mismatch:'Source mismatch', error:'Error'})[score.status] || score.status;
    return score.anomalous === true ? 'Flagged' : score.anomalous === false ? 'No flag' : 'Result incomplete';
  }
  function captureVerdict(score, tapeFlagged, label, replay = false) {
    // A replay replaces only model evidence. Never mix its verdict with an old tape decision.
    const model = score?.status === 'ok' ? score.anomalous : undefined;
    const tape = !replay && tapeFlagged === true;
    if (model === true || tape) {
      const by = model === true && tape ? 'model and tape rule' : tape ? 'tape rule' : 'model';
      return {text:label === 'good' ? 'Good part flagged' : 'Defect found by '+by, short:label === 'good'?'Good part flagged':'Defect found', tone:'flagged'};
    }
    if (model === false) {
      if (['tape','marker','other','defect'].includes(label)) return {text:'Defect missed',short:'Defect missed',tone:'missed'};
      return {text:'No defect detected',short:'',tone:''};
    }
    if (score?.status && !['missing','not_replayed'].includes(score.status)) return {text:'Could not check',short:'',tone:''};
    return {text:'Not checked',short:'',tone:''};
  }
  function viewLabel(v) {
    const names={'oblique+45':'Table, tilted +45°','oblique-45':'Table, tilted −45°','tilt+60':'Held, underside +60°','tilt-60':'Held, underside −60°',
      'end_a':'Held, end A','end_b':'Held, end B'};
    return names[v] || v;
  }
  class RunState {
    constructor() { this.reset(); }
    reset(run = null) {
      this.run=run; this.items=new Map(); this.current=null; this.stage='IDLE'; this.feeds={};
      this.live=false; this.replay=false; this.started=null; this.lastReceived=0; this.policy={}; this.log=[]; this.pending=[];
    }
    item(n) {
      const key=String(n);
      if (!this.items.has(key)) this.items.set(key,{id:key,number:n,captures:[],record:{},delivery:'Not confirmed',unassigned:[]});
      return this.items.get(key);
    }
    newestFeed(camera,event) {
      const old=this.feeds[camera];
      if (frameUrl(event) && (!old || (event.t || 0)>=(old.t || 0))) this.feeds[camera]=event;
    }
    source(item,event) {
      if (event.capture_id) return item.captures.find(c=>c.capture_id===event.capture_id || c.filename===event.capture_id);
      return item.captures.filter(c=>c.view===event.view && (!finite(event.t) || !finite(c.timestamp) || c.timestamp<=event.t)).at(-1);
    }
    ingest(event) {
      if (!event?.k) return;
      if (event.k==='run') { this.reset(event.run); this.live=event.live===true; this.replay=!!event._replay; this.started=event.t; this.policy=event.detector_policy || {}; this.stage='RUN'; }
      if (event.run && this.run && event.run!==this.run) return;
      if (!this.run && event.run) this.run=event.run;
      if (event._replay) this.replay=true;
      if (!['ping','backlog_done','preview','arm_state','preview_status'].includes(event.k)) this.lastReceived=Date.now();
      const n=Number.isInteger(event.n)?event.n:Number.isInteger(event.item)?event.item:this.current;
      if (event.k==='state') { this.stage=event.state || 'UNKNOWN'; if (n!=null) this.current=n; }
      if (event.k==='preview') this.newestFeed(event.cam,event);
      if (event.k==='watch' || event.k==='look') this.newestFeed('cam',event);
      if (event.k==='view') this.newestFeed('overview-cam',event);
      if (event.k==='snap') this.newestFeed(event.cam,event);
      if (n==null) return;
      const item=this.item(n);
      if (event.k==='look' || event.k==='view' || (event.k==='watch' && event.placed)) {
        const view=event.k==='look'?(event.view || 'top'):event.k==='view'?event.view:'watch';
        const id=event.capture_id || [this.run,n,view,event.s ?? event.frame?.id ?? event.t].join(':');
        if (!item.captures.some(c=>c.id===id)) {
          const attempt=(event.label || '').match(/(?:look|attempt)\s+(\d+)/i)?.[1];
          item.captures.push({id,capture_id:event.capture_id,filename:event.k==='look'?(event.view?`${event.view}.jpg`:attempt?`top_${attempt}.jpg`:event.label || 'top'):view,
            label:event.k==='look'?(event.view?viewLabel(event.view):attempt?`Top ${attempt}`:'Top'):viewLabel(view),view,url:frameUrl(event),timestamp:event.t,
            bbox:event.item?.bbox || event.crop,score:{},tape:event.tape,tape_threshold:event.tape_threshold ?? this.policy[view==='top'?'tape_top':'tape_web'],trigger:false});
          this.pending=this.pending.filter(p=>{if(p.n===n && this.source(item,p.event)){this.attach(item,p.event);return false;}return true;});
        }
      }
      if (event.k==='anomaly_result' && !this.attach(item,event)) this.pending.push({n,event});
      if (event.k==='crop') { const c=this.source(item,event); if (c) { c.crop_url=frameUrl(event); c.crop_label='Inspected crop'; } }
      if (event.k==='decision' || event.k==='cycle') {
        Object.assign(item.record,event);
        for (const [view,score] of Object.entries(event.scores || {})) {
          const c=this.source(item,{view,t:event.t,capture_id:score.capture_id});
          if(c){Object.assign(c.score,score);if(finite(score.tape))c.tape=score.tape;}
          else if(!item.unassigned.includes(`${view}: result received without an associated capture`))item.unassigned.push(`${view}: result received without an associated capture`);
        }
        const c=this.source(item,{view:event.at || event.decided_at_view,t:event.t,capture_id:event.capture_id});
        if(c){c.trigger=true;c.trigger_detector=detector(event.reason,event.decision);}
        if(event.t_released)item.delivery='Release recorded; physical placement unconfirmed';
      }
      if(event.k==='latency')item.record.latency_ms=event.ms_to_motion ?? event.ms_to_cmd;
      if(event.k==='grasp_result')item.grasp=event.ok?'Grip reported held':'Grip missed';
      if(event.k==='span' && /release/i.test(event.name || ''))item.delivery=event.error?'Release failed: '+event.error:
        (this.live?'Release sequence completed; physical placement unconfirmed':'Dry-run release; physical placement unconfirmed');
      if(['recovery','error','stopped'].includes(event.k)){const text=event.what || event.msg || event.reason || event.k;this.log.push({t:event.t,text});if(this.log.length>50)this.log.shift();item.notice=text;}
    }
    attach(item,event) {
      const c=this.source(item,event);if(!c)return false;
      c.score={...c.score,status:event.status,score:event.score,threshold:event.threshold,ratio:event.ratio,anomalous:event.anomalous,infer_ms:event.infer_ms,detail:event.detail,selected_type:event.selected_type};
      // Never overlay a model-coordinate heatmap on an untransformed camera rectangle.
      if(event.model_input_url){c.crop_url=event.model_input_url;c.crop_label='Recorded model input';}
      return true;
    }
  }
  return {viewLabel,RunState,frameUrl,anomalyStatus,captureVerdict,detector,finite};
});

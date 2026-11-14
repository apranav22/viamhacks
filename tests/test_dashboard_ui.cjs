// [codex/unknown · op Ali · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {RunState,anomalyStatus,captureVerdict,frameUrl}=require('../dashboard/state.js');
function run(){const s=new RunState();s.ingest({k:'run',run:'one',live:true});s.ingest({k:'state',n:1,state:'INSPECT'});return s;}
test('top retries stay separate and a score belongs to the latest preceding capture',()=>{
 const s=run();s.ingest({k:'look',n:1,s:1,t:1,label:'hover look 1'});s.ingest({k:'look',n:1,s:2,t:2,label:'hover look 2'});
 s.ingest({k:'anomaly_result',n:1,t:3,view:'top',status:'ok',score:12,threshold:10,anomalous:true});
 assert.equal(s.item(1).captures.length,2);assert.equal(anomalyStatus(s.item(1).captures[0].score),'Not evaluated');assert.equal(s.item(1).captures[1].score.anomalous,true);
});
test('late scores do not attach to a later retry or a different item',()=>{
 const s=run();s.ingest({k:'look',n:1,s:1,t:1});s.ingest({k:'look',n:1,s:2,t:4});s.ingest({k:'look',n:2,s:3,t:5});
 s.ingest({k:'anomaly_result',n:1,t:2,view:'top',status:'ok',anomalous:true});
 assert.equal(s.item(1).captures[0].score.anomalous,true);assert.equal(s.item(1).captures[1].score.status,undefined);assert.equal(s.item(2).captures[0].score.status,undefined);
});
test('tape decision retains independently positive anomaly evidence',()=>{
 const s=run();s.ingest({k:'look',n:1,s:1,t:1,tape:.03});s.ingest({k:'anomaly_result',n:1,t:2,view:'top',status:'ok',anomalous:true});
 s.ingest({k:'decision',n:1,t:3,decision:'reject',at:'top',reason:'known: tape (top face)'});
 const c=s.item(1).captures[0];assert.equal(c.trigger_detector,'tape');assert.equal(c.score.anomalous,true);assert.equal(s.item(1).delivery,'Not confirmed');
});
test('release success, release failure and dry run do not imply physical delivery',()=>{
 const s=run();s.ingest({k:'span',n:1,name:'release (reject)',error:'jam'});assert.match(s.item(1).delivery,/failed/);
 s.ingest({k:'span',n:1,name:'release (reject)',error:null});assert.match(s.item(1).delivery,/completed; physical placement unconfirmed/);
 s.live=false;s.ingest({k:'span',n:2,name:'release (set)'});assert.match(s.item(2).delivery,/Dry-run.*unconfirmed/);assert.match(s.item(1).delivery,/completed/);
});
test('camera feeds keep newest timestamp and images carry run identity',()=>{
 const s=run();s.ingest({k:'watch',run:'one',t:2,frame:{id:1}});s.ingest({k:'preview',cam:'cam',t:3,frame:{id:2}});s.ingest({k:'preview',cam:'cam',t:1,frame:{id:3}});
 assert.equal(s.feeds.cam.frame.id,2);assert.equal(frameUrl({run:'one',frame:{id:1}}),'/frame/1?run=one');assert.equal(frameUrl({frame:{id:1,ok:false}}),null);
});
test('new runs clear old evidence and old packets cannot overwrite it',()=>{
 const s=run();s.ingest({k:'look',n:1,s:1,t:1});s.ingest({k:'run',run:'two'});s.ingest({k:'look',run:'one',n:1,s:2,t:2});
 assert.equal(s.items.size,0);assert.equal(s.run,'two');
});
test('missing or invalid model results never display as clear',()=>{
 assert.equal(anomalyStatus({status:'missing'}),'Unavailable');assert.equal(anomalyStatus({status:'unknown_type'}),'Unknown type');assert.equal(anomalyStatus({status:'ok'}),'Result incomplete');
});
test('plain verdict distinguishes missed labeled defects from unlabeled clear captures',()=>{
 const clear={status:'ok',anomalous:false};
 assert.equal(captureVerdict(clear,null,'tape').text,'Defect missed');
 assert.equal(captureVerdict(clear,null,null).text,'No defect detected');
 assert.equal(captureVerdict({status:'missing'},null,'tape').text,'Not checked');
 assert.equal(captureVerdict({status:'unknown_type',anomalous:false},null,'tape').text,'Could not check');
 assert.equal(captureVerdict({status:'ok',anomalous:true},null,'good').text,'Good part flagged');
});
test('rechecked verdict never borrows a tape flag from the original run',()=>{
 const clear={status:'ok',anomalous:false},flag={status:'ok',anomalous:true};
 assert.equal(captureVerdict(clear,true,'tape',true).text,'Defect missed');
 assert.equal(captureVerdict(clear,true,'tape',false).text,'Defect found by tape rule');
 assert.equal(captureVerdict(flag,true,null,false).text,'Defect found by model and tape rule');
 assert.equal(captureVerdict({status:'not_replayed'},true,'tape',true).text,'Not checked');
});

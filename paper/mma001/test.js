"use strict";
const m=require("./model.js");
let checks=0;
function ok(value,message){checks++;if(!value)throw Error(message);}
function close(a,b,message,tolerance=1e-10){ok(Math.abs(a-b)<=tolerance,message);}
function throws(fn,message){let threw=false;try{fn();}catch(_){threw=true;}ok(threw,message);}
function row(id,date,a,b,y=1) {
 return [id,id,date,a,b,y,900,45,30,2,1,4,3,180,60,1,0,1,0,
  "1980-01-01","1981-01-01",72,70,"Lightweight","Decision - Unanimous"];
}
close(m.marketProbability(-150,130)+m.marketProbability(130,-150),1,"Market corner symmetry");
close(m.marketProbability(-110,-110),.5,"Vig removal");
close(m.valueAtPrice(.55,100).expectedProfitPerUnit,.1,"EV uses offered payout");
close(m.valueAtPrice(.5,-110).expectedProfitPerUnit,-1/22,"EV includes vig");
throws(()=>m.marketProbability(0,-110),"Reject bad odds");
throws(()=>m.validateDev([row(1,"2025-01-01",1,2)]),"Reject sealed dates");
throws(()=>m.validateDev([row(1,"2024-02-30",1,2)]),"Reject nonexistent date");
throws(()=>m.validateDev([row(1,"2024-01-01",1,2),row(1,"2024-02-01",1,3)]),"Reject duplicate fight");
throws(()=>m.validateDev([row(1,"2024-01-01",1,1)]),"Reject identical fighters");
const history=[row(1,"2010-01-01",1,2),row(2,"2010-02-01",1,3),row(3,"2010-02-01",1,4),row(4,"2010-04-01",1,5)];
const prices=history.map(r=>[r[0],-110,-110,1,1]);
const base=m.buildExamples(history,prices);
const changed=history.map(r=>[...r]);changed[1][5]=0;changed[1][7]=1000;changed[1][13]=800;
const altered=m.buildExamples(changed,prices);
for(const id of [2,3]) {
 const a=base.find(r=>r.id===id),b=altered.find(r=>r.id===id);
 a.x.forEach((v,j)=>close(v,b.x[j],"Same-day outcomes and stats do not leak"));
}
ok(base.find(r=>r.id===4).x.some((v,j)=>v!==altered.find(r=>r.id===4).x[j]),"Past result affects later forecast");
const reordered=m.buildExamples([history[3],history[2],history[0],history[1]],prices);
base.forEach((r,i)=>r.x.forEach((v,j)=>close(v,reordered[i].x[j],"Input order does not change features")));
const future=[...history,row(5,"2024-12-14",1,6)];
const extended=m.buildExamples(future,[...prices,[5,-110,-110,1,1]]);
base.forEach((r,i)=>r.x.forEach((v,j)=>close(v,extended[i].x[j],"Future results do not change earlier features")));
throws(()=>m.buildExamples(history,[[1,-110,-110,2,1]]),"Reject duplicate source prices");
throws(()=>m.buildExamples(history,[[1,-110,-110,1,1],[1,-110,-110,1,1]]),"Reject repeated price pair");
const none=history.map(r=>[...r]);for(let j=7;j<=18;j++)none[0][j]=null;
const missing=m.buildExamples(none,prices);
for(const r of missing)ok(r.x.every(Number.isFinite),"Missing stats remain valid");
const debut=m.buildExamples([row(1,"2010-01-01",1,2)],[[1,-110,-110,1,1]])[0];
for(const j of [1,2,3,4,5,6,7,9,10])close(debut.x[j],0,"Debut has neutral history");
const training=Array.from({length:300},(_,i)=>({
 id:i,event:i,date:"2011-01-01",q:.4+(i%3)*.1,y:i%4?1:0,
 x:m.FEATURES.map((_,j)=>j===0?(i%7-3)/3:0)
}));
const fitted=m.fit(training,.01,true);
ok(fitted.converged,"Optimizer converges");
for(const r of training) {
 const p=m.predict(fitted,r.x,r.q),reversed=m.predict(fitted,r.x.map(x=>-x),1-r.q);
 close(p+reversed,1,"Model is symmetric under corner swap");
 ok(p>0&&p<1,"Probabilities remain valid");
}
const mirrored=training.map(r=>({...r,q:1-r.q,y:1-r.y,x:r.x.map(v=>-v)}));
const mirrorFit=m.fit(mirrored,.01,true);
fitted.coefficients.forEach((v,j)=>close(v,mirrorFit.coefficients[j],"Training is invariant to corner swap",1e-8));
throws(()=>m.fit([...training,{...training[0],date:"2025-01-01"}]),"Direct fit refuses sealed date");
const zero=m.fit(training.map(r=>({...r,x:r.x.map(()=>0)})),.01,true);
for(const q of [.1,.5,.9])close(m.predict(zero,Array(m.FEATURES.length).fill(0),q),q,"Neutral model returns market");
const bootstrap=m.eventBootstrap([{event:1,y:1,q:.5,p:.5},{event:2,y:0,q:.5,p:.5}],100);
close(bootstrap.ci95[0],0,"No-change bootstrap lower");
close(bootstrap.ci95[1],0,"No-change bootstrap upper");
if(typeof console!=="undefined")console.log(checks+" checks passed");
module.exports={checks};

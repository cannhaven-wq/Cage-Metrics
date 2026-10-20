"use strict";
/* MMA-001 transcribed verbatim from the Google Doc "MMA Formula v1" (2026-10-20) for reproduction. */
const CUTOFF = "2025-01-01";
const FEATURES = [
  "age_advantage_5y", "ufc_record_logodds_gap", "elo_gap_400",
  "sig_net_gap_2_per_min", "td_net_gap_2_per_15", "td_matchup_gap_2",
  "control_net_gap_025", "kd_net_gap_per_15", "reach_gap_4in",
  "layoff_log_gap_2", "experience_log_gap_2"
];
const COLUMNS = ["fight_id","event_id","event_date","a_id","b_id","y","seconds",
  "a_sig","b_sig","a_td","b_td","a_td_attempts","b_td_attempts",
  "a_control","b_control","a_kd","b_kd","a_sub","b_sub",
  "a_dob","b_dob","a_reach","b_reach","weight_class","method"];
const HALF_LIFE_DAYS = 730;
const clip = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const finite = x => typeof x === "number" && Number.isFinite(x);
function sigmoid(z) { return z >= 0 ? 1 / (1 + Math.exp(-z)) : Math.exp(z) / (1 + Math.exp(z)); }
function logit(p) { if (!finite(p) || p <= 0 || p >= 1) throw Error("Invalid probability"); return Math.log(p / (1-p)); }
function implied(odds) {
  if (!finite(odds) || Math.abs(odds) < 100 || Math.abs(odds) > 10000) throw Error("Invalid American odds");
  return odds > 0 ? 100 / (odds+100) : -odds / (100-odds);
}
function marketProbability(a, b) { const x=implied(a), y=implied(b); return x/(x+y); }
function decimalOdds(odds) { implied(odds); return odds>0 ? 1+odds/100 : 1+100/-odds; }
function valueAtPrice(p, odds) {
  if (!finite(p) || p<=0 || p>=1) throw Error("Invalid probability");
  const d=decimalOdds(odds);
  return {probability:p, fairAmerican:p>=0.5 ? -100*p/(1-p) : 100*(1-p)/p,
    breakEvenProbability:1/d, expectedProfitPerUnit:p*d-1,
    status:"Experimental estimate; no betting advantage established"};
}
function dateMs(s) {
  if (typeof s!=="string" || !/^\d{4}-\d{2}-\d{2}$/.test(s)) throw Error("Invalid date");
  const ms=Date.parse(s+"T00:00:00Z");
  if (!Number.isFinite(ms) || new Date(ms).toISOString().slice(0,10)!==s) throw Error("Invalid date");
  return ms;
}
function validateDev(rows) {
  const seen = new Set();
  for (const r of rows) {
    if (!Array.isArray(r) || r.length!==COLUMNS.length) throw Error("Wrong export columns");
    dateMs(r[2]);
    if (r[2]>=CUTOFF) throw Error("Sealed date refused");
    for(const i of [0,1,3,4]) if(!Number.isSafeInteger(r[i])) throw Error("Invalid id");
    if(seen.has(r[0])) throw Error("Duplicate fight");
    seen.add(r[0]);
    if(r[3]===r[4] || ![0,0.5,1].includes(r[5])) throw Error("Invalid corners/outcome");
    for(const i of [6,7,8,9,10,11,12,13,14,15,16,17,18,21,22]) {
      if(r[i]!==null && (!finite(r[i]) || r[i]<0)) throw Error("Invalid numeric field");
    }
  }
}
function emptyState() {
  return {w:0,l:0,n:0,elo:1500,last:null,decayAt:null,
    sigMin:0,sigNet:0,tdMin:0,tdNet:0,tdOwn:0,tdConceded:0,tdOppAttempts:0,
    controlMin:0,controlNet:0,kdMin:0,kdNet:0};
}
const DECAY_FIELDS=["sigMin","sigNet","tdMin","tdNet","tdOwn","tdConceded",
  "tdOppAttempts","controlMin","controlNet","kdMin","kdNet"];
function decay(state, ms) {
  if(state.decayAt!==null) {
    if(ms<state.decayAt) throw Error("History out of order");
    const factor=Math.pow(0.5,(ms-state.decayAt)/86400000/HALF_LIFE_DAYS);
    for(const k of DECAY_FIELDS) state[k]*=factor;
  }
  state.decayAt=ms;
}
function age(dob, ms) {
  if(!dob) return null;
  const a=(ms-dateMs(dob))/86400000/365.2425;
  return a>=16 && a<=60 ? a : null;
}
function profile(state, ms, dob, reach) {
  return {...state,age:age(dob,ms),reach:finite(reach)&&reach>=40&&reach<=100?reach:null,
    record:Math.log((state.w+2)/(state.l+2)),
    sigNetRate:state.sigNet/(state.sigMin+30),
    tdNetRate:15*state.tdNet/(state.tdMin+30),
    tdAttack:15*state.tdOwn/(state.tdMin+30),
    tdDefense:1-(state.tdConceded+5)/(state.tdOppAttempts+10),
    controlNetRate:state.controlNet/60/(state.controlMin+30),
    kdNetRate:15*state.kdNet/(state.kdMin+30),
    layoff:state.last===null?null:(ms-state.last)/86400000};
}
function matchupFeatures(a,b) {
  return [
    a.age!==null&&b.age!==null?(b.age-a.age)/5:0,
    a.record-b.record,(a.elo-b.elo)/400,
    (a.sigNetRate-b.sigNetRate)/2,(a.tdNetRate-b.tdNetRate)/2,
    (a.tdAttack*(1-b.tdDefense)-b.tdAttack*(1-a.tdDefense))/2,
    (a.controlNetRate-b.controlNetRate)/0.25,a.kdNetRate-b.kdNetRate,
    a.reach!==null&&b.reach!==null?(a.reach-b.reach)/4:0,
    a.layoff!==null&&b.layoff!==null?(Math.log1p(b.layoff)-Math.log1p(a.layoff))/2:0,
    (Math.log1p(a.n)-Math.log1p(b.n))/2
  ].map(v=>clip(v,-5,5));
}
function updateStats(state,r,side,ms) {
  state.n++;
  const win=side===0?r[5]:1-r[5];
  if(win===1) state.w++; else if(win===0) state.l++;
  state.last=ms;
  const seconds=r[6];
  if(!finite(seconds)||seconds<=0||seconds>3600) return;
  const minutes=seconds/60, own=i=>r[i+side], other=i=>r[i+1-side];
  if(finite(own(7))&&finite(other(7))) {
    state.sigMin+=minutes; state.sigNet+=own(7)-other(7);
  }
  if([own(9),other(9),own(11),other(11)].every(finite)
      &&own(9)<=own(11)&&other(9)<=other(11)) {
    state.tdMin+=minutes;state.tdNet+=own(9)-other(9);state.tdOwn+=own(9);
    state.tdConceded+=other(9);state.tdOppAttempts+=other(11);
  }
  if([own(13),other(13)].every(finite) && own(13)<=seconds && other(13)<=seconds) {
    state.controlMin+=minutes;state.controlNet+=own(13)-other(13);
  }
  if([own(15),other(15)].every(finite)) {
    state.kdMin+=minutes;state.kdNet+=own(15)-other(15);
  }
}
function buildExamples(rows, prices) {
  validateDev(rows);
  const odds=new Map();
  for(const r of prices) {
    if(!Array.isArray(r)||r.length!==5||r[3]!==1||r[4]!==1||odds.has(r[0])) throw Error("Invalid or ambiguous price pair");
    odds.set(r[0],marketProbability(r[1],r[2]));
  }
  const ordered=[...rows].sort((a,b)=>a[2].localeCompare(b[2])||a[0]-b[0]);
  const states=new Map(), out=[];
  const get=id=>{if(!states.has(id)) states.set(id,emptyState());return states.get(id);};
  for(let start=0;start<ordered.length;) {
    let end=start+1;while(end<ordered.length&&ordered[end][2]===ordered[start][2]) end++;
    const ms=dateMs(ordered[start][2]), eloChanges=new Map();
    for(let i=start;i<end;i++) {
      const r=ordered[i],a=get(r[3]),b=get(r[4]);
      decay(a,ms);decay(b,ms);
      const x=matchupFeatures(profile(a,ms,r[19],r[21]),profile(b,ms,r[20],r[22]));
      const q=odds.get(r[0]);
      if((r[5]===0||r[5]===1)&&q!==undefined) {
        out.push({id:r[0],event:r[1],date:r[2],y:r[5],q,x});
      }
      const expected=1/(1+Math.pow(10,(b.elo-a.elo)/400)),delta=32*(r[5]-expected);
      eloChanges.set(r[3],(eloChanges.get(r[3])||0)+delta);
      eloChanges.set(r[4],(eloChanges.get(r[4])||0)-delta);
    }
    for(let i=start;i<end;i++) {
      const r=ordered[i];updateStats(get(r[3]),r,0,ms);updateStats(get(r[4]),r,1,ms);
    }
    for(const [id,change] of eloChanges) get(id).elo+=change;
    start=end;
  }
  return out;
}
function dot(a,b) {let s=0;for(let j=0;j<a.length;j++)s+=a[j]*b[j];return s;}
function softplus(x) {return Math.max(0,x)+Math.log1p(Math.exp(-Math.abs(x)));}
function objective(rows,beta,scales,lambda,useMarket) {
  let sum=0;
  for(const r of rows) {
    let z=useMarket?logit(r.q):0;
    for(let j=0;j<beta.length;j++) z+=beta[j]*r.x[j]/scales[j];
    sum+=softplus(z)-r.y*z;
  }
  return sum/rows.length+0.5*lambda*dot(beta,beta);
}
function solve(matrix,rhs) {
  const n=rhs.length,a=matrix.map((r,i)=>[...r,rhs[i]]);
  for(let j=0;j<n;j++) {
    let p=j;for(let k=j+1;k<n;k++)if(Math.abs(a[k][j])>Math.abs(a[p][j]))p=k;
    [a[j],a[p]]=[a[p],a[j]];
    if(Math.abs(a[j][j])<1e-14) throw Error("Singular fit");
    const divisor=a[j][j];for(let c=j;c<=n;c++)a[j][c]/=divisor;
    for(let r=0;r<n;r++)if(r!==j){const t=a[r][j];for(let c=j;c<=n;c++)a[r][c]-=t*a[j][c];}
  }
  return a.map(r=>r[n]);
}
function fit(rows,lambda=0.01,useMarket=true) {
  if(rows.length<100||!finite(lambda)||lambda<=0)throw Error("Insufficient training rows or invalid penalty");
  if(rows.some(r=>r.date>=CUTOFF))throw Error("Sealed fit refused");
  const d=FEATURES.length,scales=Array(d).fill(0);
  for(const r of rows)for(let j=0;j<d;j++)scales[j]+=r.x[j]**2;
  for(let j=0;j<d;j++)scales[j]=Math.max(Math.sqrt(scales[j]/rows.length),0.1);
  let beta=Array(d).fill(0),converged=false,iterations=0;
  for(let iter=0;iter<60;iter++) {
    const g=beta.map(b=>lambda*b),h=Array.from({length:d},(_,j)=>Array.from({length:d},(_,k)=>j===k?lambda:0));
    for(const r of rows) {
      const x=r.x.map((v,j)=>v/scales[j]),z=(useMarket?logit(r.q):0)+dot(beta,x),p=sigmoid(z),v=Math.max(p*(1-p),1e-10)/rows.length;
      for(let j=0;j<d;j++){
        g[j]+=(p-r.y)*x[j]/rows.length;
        for(let k=0;k<=j;k++)h[j][k]+=v*x[j]*x[k];
      }
    }
    for(let j=0;j<d;j++)for(let k=0;k<j;k++)h[k][j]=h[j][k];
    iterations=iter+1;
    if(Math.max(...g.map(Math.abs))<1e-8){converged=true;break;}
    const step=solve(h,g),old=objective(rows,beta,scales,lambda,useMarket);
    let alpha=1,next;
    while(alpha>1e-8) {
      next=beta.map((b,j)=>b-alpha*step[j]);
      if(objective(rows,next,scales,lambda,useMarket)<=old-1e-4*alpha*dot(g,step))break;
      alpha/=2;
    }
    if(alpha<=1e-8)throw Error("Fit line search failed");
    beta=next;
  }
  if(!converged)throw Error("Fit failed to converge");
  return {version:"mma-001-dev-v1",features:FEATURES,lambda,useMarket,scales,beta,
    coefficients:beta.map((b,j)=>b/scales[j]),converged,iterations,
    trainingRows:rows.length,trainingFirst:rows[0].date,trainingLast:rows.at(-1).date};
}
function predict(model,x,q) {
  if(x.length!==FEATURES.length||!x.every(finite))throw Error("Invalid feature vector");
  return sigmoid((model.useMarket?logit(q):0)+dot(model.coefficients,x));
}
function score(rows,probability) {
  if(!rows.length)throw Error("No evaluation rows");
  let ll=0,brier=0,correct=0;
  for(const r of rows) {
    const p=probability(r);if(!finite(p)||p<0||p>1)throw Error("Invalid forecast");
    const safe=clip(p,1e-12,1-1e-12);
    ll-=r.y*Math.log(safe)+(1-r.y)*Math.log(1-safe);
    brier+=(p-r.y)**2;correct+=(p>=0.5?1:0)===r.y?1:0;
  }
  return {n:rows.length,events:new Set(rows.map(r=>r.event)).size,logLoss:ll/rows.length,brier:brier/rows.length,accuracy:correct/rows.length};
}
function develop(examples) {
  const training=examples.filter(r=>r.date>="2010-01-01"&&r.date<"2020-01-01");
  const validation=examples.filter(r=>r.date>="2020-01-01"&&r.date<"2023-01-01");
  const trials=[0.001,0.01,0.1].map(lambda=>{
    const model=fit(training,lambda,true);
    return {lambda,validation:score(validation,r=>predict(model,r.x,r.q))};
  });
  const selected=[...trials].sort((a,b)=>a.validation.logLoss-b.validation.logLoss||b.lambda-a.lambda)[0].lambda;
  const evaluations=[],predictions=[];
  for(const year of [2023,2024]) {
    const tr=examples.filter(r=>r.date>="2010-01-01"&&r.date<year+"-01-01");
    const te=examples.filter(r=>r.date>=year+"-01-01"&&r.date<(year+1)+"-01-01");
    const model=fit(tr,selected,true);
    evaluations.push({year,market:score(te,r=>r.q),model:score(te,r=>predict(model,r.x,r.q)),trainingRows:tr.length});
    for(const r of te)predictions.push({...r,p:predict(model,r.x,r.q)});
  }
  const market=score(predictions,r=>r.q),model=score(predictions,r=>r.p);
  const final=fit(examples.filter(r=>r.date>="2010-01-01"),selected,true);
  return {status:"Exploratory DEV only; not independently audited; no holdout look",
    variantsTriedOnDev:3,trials,selectedLambda:selected,evaluations,
    combined:{market,model,logLossImprovement:market.logLoss-model.logLoss},final,predictions};
}
function eventBootstrap(predictions,resamples=10000,seed=20261012) {
  if(!Number.isInteger(resamples)||resamples<100)throw Error("Invalid resample count");
  const grouped=new Map();
  for(const r of predictions){
    const a=clip(r.q,1e-12,1-1e-12),b=clip(r.p,1e-12,1-1e-12);
    const delta=-r.y*Math.log(a)-(1-r.y)*Math.log(1-a)+r.y*Math.log(b)+(1-r.y)*Math.log(1-b);
    if(!grouped.has(r.event))grouped.set(r.event,{sum:0,n:0});
    const c=grouped.get(r.event);c.sum+=delta;c.n++;
  }
  const cards=[...grouped.values()];if(cards.length<2)throw Error("Insufficient events");
  const initialSeed=seed;
  const random=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;};
  const draws=[];
  for(let i=0;i<resamples;i++){
    let sum=0,n=0;
    for(let j=0;j<cards.length;j++){const c=cards[Math.floor(random()*cards.length)];sum+=c.sum;n+=c.n;}
    draws.push(sum/n);
  }
  draws.sort((a,b)=>a-b);
  return {seed:initialSeed,resamples,unit:"event",ci95:[draws[Math.floor(.025*resamples)],draws[Math.floor(.975*resamples)]]};
}
const api={CUTOFF,COLUMNS,FEATURES,marketProbability,decimalOdds,valueAtPrice,
  sigmoid,logit,validateDev,emptyState,profile,matchupFeatures,buildExamples,fit,predict,score,develop,eventBootstrap};
if(typeof module!=="undefined")module.exports=api;

"use client";
import { useState } from "react";

const outcome = (h, a) => h > a ? "H" : a > h ? "A" : "D";
const getStatus = (m) => {
  if (!m.result) return "pending";
  if (m.hs === m.result.hs && m.as_ === m.result.as_) return "exact";
  return outcome(m.hs, m.as_) === outcome(m.result.hs, m.result.as_) ? "correct" : "wrong";
};
const verdict = (s) => ({exact:"Marcador exacto (6 pts)",correct:"Ganador acertado (3-4 pts)",wrong:"Sin acierto (0 pts)"}[s]||"");
const STATUS = {
  exact:{icon:"✅",label:"¡Exacto!",color:"#4ADE80",bg:"rgba(5,46,22,0.9)",border:"#166534"},
  correct:{icon:"🎯",label:"Acertado",color:"#FFB800",bg:"rgba(45,31,6,0.9)",border:"#854D0E"},
  wrong:{icon:"❌",label:"Fallido",color:"#F87171",bg:"rgba(51,10,10,0.9)",border:"#7F1D1D"},
  pending:{icon:"⏳",label:"Pendiente",color:"#64748B",bg:"rgba(15,24,40,0.9)",border:"#1E293B"},
};
const TC = {
  FAV:{label:"Favorito",color:"#4ADE80",bg:"rgba(5,46,22,0.8)"},
  EMP:{label:"Parejo",color:"#94A3B8",bg:"rgba(30,41,59,0.9)"},
  SOR:{label:"Sorpresa posible",color:"#FBBF24",bg:"rgba(45,31,6,0.8)"},
};
const Score = ({h,a,size=30,color="#FFB800",muted=false}) => (
  <span style={{fontSize:size,fontWeight:900,letterSpacing:2,fontVariantNumeric:"tabular-nums",color:muted?"#475569":color}}>
    {h}<span style={{color:"#1E293B",margin:"0 1px"}}>–</span>{a}
  </span>
);

// barra 1X2
const Bar1X2 = ({m}) => {
  const md = m.model; if(!md) return null;
  const seg = [["1",md.ph,"#16a34a"],["X",md.pd,"#64748B"],["2",md.pa,"#2563eb"]];
  return (
    <div style={{margin:"2px 0 0"}}>
      <div style={{display:"flex",height:16,borderRadius:5,overflow:"hidden",border:"1px solid #1E293B"}}>
        {seg.map(([l,v,c])=>(
          <div key={l} style={{width:`${v}%`,background:c,display:"flex",alignItems:"center",justifyContent:"center",minWidth:v>=12?"auto":0}}>
            {v>=14 && <span style={{fontSize:9,fontWeight:700,color:"#fff"}}>{l} {v}%</span>}
          </div>
        ))}
      </div>
    </div>
  );
};

const Card = ({m,onOpen}) => {
  const tc=TC[m.type], st=STATUS[getStatus(m)];
  const revised=m.predictions.length>1, prev=revised?m.predictions[m.predictions.length-2]:null;
  const hwin=m.hs>m.as_, awin=m.as_>m.hs, md=m.model;
  return (
    <div onClick={onOpen} style={{background:"linear-gradient(160deg,#0f1828,#0a1020)",borderRadius:14,border:`1px solid ${st.border}`,overflow:"hidden",cursor:"pointer"}}>
      <div style={{padding:"8px 14px",background:"#060C16",display:"flex",justifyContent:"space-between",alignItems:"center",borderBottom:"1px solid #1a2540"}}>
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <span style={{background:"rgba(255,184,0,0.12)",color:"#FFB800",fontSize:10,fontWeight:700,padding:"2px 8px",borderRadius:20,border:"1px solid rgba(255,184,0,0.25)"}}>GRUPO {m.gid}</span>
          <span style={{color:"#475569",fontSize:11}}>⚽ {m.date}</span>
        </div>
        <div style={{display:"flex",gap:5,alignItems:"center"}}>
          {md && <span style={{background:"rgba(20,40,80,0.8)",color:"#7dd3fc",fontSize:9,fontWeight:700,padding:"2px 8px",borderRadius:20,border:"1px solid #1e3a5f"}}>📊 Modelo</span>}
          <span style={{background:st.bg,color:st.color,fontSize:9,fontWeight:700,padding:"2px 9px",borderRadius:20,border:`1px solid ${st.border}`}}>{st.icon} {st.label}</span>
        </div>
      </div>
      <div style={{padding:"14px 14px 6px",display:"flex",alignItems:"center",gap:6}}>
        <div style={{flex:1,textAlign:"center"}}>
          <div style={{fontSize:30}}>{m.home.flag}</div>
          {m.home.debut && <span style={{fontSize:8,background:"rgba(23,37,84,0.8)",color:"#60A5FA",padding:"1px 6px",borderRadius:10,display:"inline-block",marginTop:2}}>★ DEBUT</span>}
          <div style={{fontSize:11,fontWeight:700,marginTop:5,color:hwin?"#4ADE80":"#CBD5E1"}}>{m.home.name}</div>
        </div>
        <div style={{textAlign:"center",minWidth:92}}>
          <div style={{fontSize:8,color:"#334155",letterSpacing:2,marginBottom:3}}>{md?"PICK POLLA":"PRONÓSTICO"}</div>
          <Score h={m.hs} a={m.as_} size={32} muted={m.hs===m.as_}/>
          {revised && !m.result && <div style={{fontSize:9,color:"#60A5FA",marginTop:3}}>🔄 <span style={{textDecoration:"line-through",color:"#475569"}}>{prev.hs}–{prev.as_}</span></div>}
          {m.result ? (
            <div style={{marginTop:6,padding:"5px 0",background:st.bg,borderRadius:8,border:`1px solid ${st.border}`}}>
              <div style={{fontSize:7,color:st.color,letterSpacing:2,opacity:.8}}>RESULTADO</div>
              <Score h={m.result.hs} a={m.result.as_} size={24} color="#fff"/>
            </div>
          ) : <div style={{marginTop:6,fontSize:9,color:"#334155"}}>toca para detalle ›</div>}
        </div>
        <div style={{flex:1,textAlign:"center"}}>
          <div style={{fontSize:30}}>{m.away.flag}</div>
          {m.away.debut && <span style={{fontSize:8,background:"rgba(23,37,84,0.8)",color:"#60A5FA",padding:"1px 6px",borderRadius:10,display:"inline-block",marginTop:2}}>★ DEBUT</span>}
          <div style={{fontSize:11,fontWeight:700,marginTop:5,color:awin?"#4ADE80":"#CBD5E1"}}>{m.away.name}</div>
        </div>
      </div>
      <div style={{padding:"0 14px 10px"}}>
        {md ? <Bar1X2 m={m}/> : (
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <span style={{fontSize:10,color:"#475569"}}>Confianza</span>
            <span style={{fontSize:10,fontWeight:700,color:m.conf>=75?"#4ADE80":m.conf>=62?"#FFB800":"#94A3B8"}}>{m.conf}%</span>
          </div>
        )}
        {md && <div style={{display:"flex",justifyContent:"space-between",marginTop:5}}>
          <span style={{fontSize:9,color:"#475569"}}>λ {md.lh} – {md.la}</span>
          <span style={{background:tc.bg,color:tc.color,fontSize:8,fontWeight:600,padding:"1px 7px",borderRadius:10}}>{tc.label}</span>
        </div>}
      </div>
      <div style={{margin:"0 14px 14px",padding:"8px 10px",background:"#060C16",borderRadius:8,borderLeft:"2px solid #1E3A5F"}}>
        {m.venue && <div style={{fontSize:9,color:"#334155",marginBottom:3}}>📍 {m.venue}</div>}
        {m.note && <div style={{fontSize:11,color:"#94A3B8",lineHeight:1.6}}>{m.note}</div>}
      </div>
    </div>
  );
};

const Modal = ({m,onClose}) => {
  const [oh,setOh]=useState(""); const [oa,setOa]=useState("");
  const [opin,setOpin]=useState(""); const [obusy,setObusy]=useState(false); const [omsg,setOmsg]=useState("");
  if(!m) return null;
  const st=STATUS[getStatus(m)], md=m.model;
  async function saveOv(remove){
    if(!opin){setOmsg("Escribe el código.");return;}
    if(!remove && (oh===""||oa==="")){setOmsg("Escribe el marcador.");return;}
    setObusy(true);setOmsg("Guardando…");
    try{
      const r=await fetch("/api/override",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({pin:opin,fixtureId:m.fixtureId,hs:Number(oh),as_:Number(oa),remove:!!remove})});
      const d=await r.json();
      setOmsg(d.ok?(remove?"✅ Override quitado — actualizando (~1 min).":"✅ Guardado — se envía en ~1 min."):("❌ "+(d.error||("Error "+r.status))));
    }catch(e){setOmsg("❌ "+e.message);}
    setObusy(false);
  }
  return (
    <div onClick={onClose} style={{position:"fixed",inset:0,background:"rgba(3,6,12,0.82)",backdropFilter:"blur(3px)",display:"flex",alignItems:"center",justifyContent:"center",padding:14,zIndex:100}}>
      <div onClick={e=>e.stopPropagation()} style={{background:"#0B1220",borderRadius:16,border:"1px solid #1E293B",width:"100%",maxWidth:470,maxHeight:"88vh",overflowY:"auto"}}>
        <div style={{position:"sticky",top:0,background:"#060C16",padding:"12px 16px",borderBottom:"1px solid #1a2540",display:"flex",justifyContent:"space-between",alignItems:"center",zIndex:2}}>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            <span style={{background:"rgba(255,184,0,0.12)",color:"#FFB800",fontSize:10,fontWeight:700,padding:"2px 8px",borderRadius:20}}>GRUPO {m.gid}</span>
            <span style={{color:"#475569",fontSize:11}}>⚽ {m.date}</span>
          </div>
          <button onClick={onClose} style={{background:"#0F1828",border:"1px solid #1E293B",color:"#94A3B8",borderRadius:8,width:30,height:30,fontSize:16,cursor:"pointer"}}>✕</button>
        </div>
        <div style={{padding:"18px 16px 8px",display:"flex",alignItems:"center",gap:8}}>
          <div style={{flex:1,textAlign:"center"}}><div style={{fontSize:40}}>{m.home.flag}</div><div style={{fontSize:13,fontWeight:700,marginTop:6}}>{m.home.name}</div></div>
          <div style={{textAlign:"center",minWidth:70}}><div style={{fontSize:8,color:"#334155",letterSpacing:2}}>{md?"PICK":"PRON."}</div><Score h={m.hs} a={m.as_} size={30} muted={m.hs===m.as_}/></div>
          <div style={{flex:1,textAlign:"center"}}><div style={{fontSize:40}}>{m.away.flag}</div><div style={{fontSize:13,fontWeight:700,marginTop:6}}>{m.away.name}</div></div>
        </div>
        {m.venue && <div style={{textAlign:"center",fontSize:10,color:"#475569",padding:"0 16px 14px"}}>📍 {m.venue}</div>}

        {!m.result && (
          <div style={{margin:"0 16px 16px",padding:"12px 14px",background:"#101a30",borderRadius:12,border:"1px solid #1e3a5f"}}>
            <div style={{fontSize:10,color:"#FFB800",letterSpacing:2,marginBottom:8,fontWeight:700}}>✍️ FORZAR MARCADOR (p. ej. BetAlpha)</div>
            <div style={{display:"flex",gap:6,alignItems:"center",flexWrap:"wrap"}}>
              <input type="number" min="0" value={oh} onChange={e=>setOh(e.target.value)} placeholder={m.home.name.slice(0,6)}
                style={{width:62,background:"#0B1220",border:"1px solid #1E293B",borderRadius:8,color:"#E2E8F0",padding:"7px",textAlign:"center",fontSize:14}}/>
              <span style={{color:"#475569",fontWeight:800}}>–</span>
              <input type="number" min="0" value={oa} onChange={e=>setOa(e.target.value)} placeholder={m.away.name.slice(0,6)}
                style={{width:62,background:"#0B1220",border:"1px solid #1E293B",borderRadius:8,color:"#E2E8F0",padding:"7px",textAlign:"center",fontSize:14}}/>
              <input type="password" inputMode="numeric" value={opin} onChange={e=>setOpin(e.target.value)} placeholder="código"
                style={{width:84,background:"#0B1220",border:"1px solid #1E293B",borderRadius:8,color:"#E2E8F0",padding:"7px",textAlign:"center",fontSize:13}}/>
              <button onClick={()=>saveOv(false)} disabled={obusy}
                style={{background:obusy?"#1E293B":"#FFB800",color:obusy?"#64748B":"#06090E",border:"none",borderRadius:8,padding:"8px 12px",fontWeight:700,fontSize:13,cursor:"pointer"}}>Guardar</button>
              <button onClick={()=>saveOv(true)} disabled={obusy}
                style={{background:"transparent",color:"#94A3B8",border:"1px solid #1E293B",borderRadius:8,padding:"8px 10px",fontSize:12,cursor:"pointer"}}>Quitar</button>
            </div>
            {omsg && <div style={{fontSize:11,color:"#94A3B8",marginTop:8}}>{omsg}</div>}
            <div style={{fontSize:10,color:"#475569",marginTop:6}}>Reemplaza el pick del modelo para este partido y lo reenvía.</div>
          </div>
        )}

        {m.result && (
          <div style={{margin:"0 16px 16px",padding:12,background:st.bg,borderRadius:12,border:`1px solid ${st.border}`,textAlign:"center"}}>
            <div style={{fontSize:9,color:st.color,letterSpacing:2,marginBottom:4}}>RESULTADO FINAL</div>
            <Score h={m.result.hs} a={m.result.as_} size={34} color="#fff"/>
            <div style={{fontSize:12,fontWeight:700,color:st.color,marginTop:6}}>{st.icon} {verdict(getStatus(m))}</div>
          </div>
        )}

        {md && (
          <div style={{margin:"0 16px 16px",padding:"12px 14px",background:"#091428",borderRadius:12,border:"1px solid #1e3a5f"}}>
            <div style={{fontSize:10,color:"#7dd3fc",letterSpacing:2,marginBottom:10,fontWeight:700}}>📊 MERCADO + POISSON-ELO</div>
            <Bar1X2 m={m}/>
            <div style={{display:"flex",justifyContent:"space-around",marginTop:12,textAlign:"center"}}>
              <div><div style={{fontSize:8,color:"#475569"}}>GOLES ESP. (λ)</div><div style={{fontSize:13,fontWeight:700,color:"#cbd5e1"}}>{md.lh} – {md.la}</div></div>
              <div><div style={{fontSize:8,color:"#475569"}}>MÁS PROBABLE</div><div style={{fontSize:13,fontWeight:700,color:"#cbd5e1"}}>{md.modal.hs}–{md.modal.as_}</div></div>
              <div><div style={{fontSize:8,color:"#475569"}}>PICK / EV-ALT</div><div style={{fontSize:13,fontWeight:700,color:"#FFB800"}}>{m.hs}–{m.as_} <span style={{color:"#475569",fontWeight:400}}>/ {md.evPick.hs}–{md.evPick.as_}</span></div></div>
            </div>
            <div style={{fontSize:10,color:"#64748b",marginTop:10,lineHeight:1.5,textAlign:"center"}}>{md.coin?"Moneda al aire → recomiendo 1-1 (marcador más común).":"Favorito claro → me comprometo con él para asegurar el piso de puntos."}</div>
          </div>
        )}

        <div style={{padding:"0 16px 8px"}}>
          <div style={{fontSize:10,color:"#FFB800",letterSpacing:3,marginBottom:12,fontWeight:700}}>🕘 HISTORIAL DE PREDICCIONES</div>
          <div style={{position:"relative",paddingLeft:22}}>
            <div style={{position:"absolute",left:6,top:4,bottom:m.result?4:14,width:2,background:"#1E293B"}}/>
            {m.predictions.map((p,i)=>{
              const last=i===m.predictions.length-1 && !m.result, ptc=TC[p.type];
              const pv=i>0?m.predictions[i-1]:null, ch=pv&&(pv.hs!==p.hs||pv.as_!==p.as_);
              return (
                <div key={i} style={{position:"relative",marginBottom:16}}>
                  <div style={{position:"absolute",left:-22,top:2,width:14,height:14,borderRadius:"50%",background:last?"#FFB800":"#0B1220",border:`2px solid ${last?"#FFB800":"#475569"}`}}/>
                  <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4,flexWrap:"wrap"}}>
                    <span style={{fontSize:11,fontWeight:700,color:last?"#FFB800":"#CBD5E1"}}>{p.stage}</span>
                    <span style={{fontSize:9,color:"#475569"}}>{p.date}</span>
                    {last && <span style={{fontSize:8,background:"rgba(255,184,0,0.12)",color:"#FFB800",padding:"1px 7px",borderRadius:10,fontWeight:700}}>VIGENTE</span>}
                  </div>
                  <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:5}}>
                    <Score h={p.hs} a={p.as_} size={22} muted={p.hs===p.as_}/>
                    {ch && <span style={{fontSize:9,color:"#60A5FA"}}>🔄 <span style={{textDecoration:"line-through",color:"#475569"}}>{pv.hs}–{pv.as_}</span></span>}
                    <span style={{background:ptc.bg,color:ptc.color,fontSize:8,fontWeight:600,padding:"1px 7px",borderRadius:10}}>{ptc.label}</span>
                  </div>
                  <div style={{fontSize:11,color:"#94A3B8",lineHeight:1.6}}>{p.reason}</div>
                </div>
              );
            })}
            {m.result && (
              <div style={{position:"relative"}}>
                <div style={{position:"absolute",left:-22,top:2,width:14,height:14,borderRadius:"50%",background:st.color,border:`2px solid ${st.color}`}}/>
                <div style={{fontSize:11,fontWeight:700,color:st.color,marginBottom:4}}>Resultado real</div>
                <div style={{display:"flex",alignItems:"center",gap:10}}><Score h={m.result.hs} a={m.result.as_} size={22} color="#fff"/><span style={{fontSize:11,color:st.color,fontWeight:700}}>{st.icon} {st.label}</span></div>
              </div>
            )}
          </div>
        </div>
        {m.note && <div style={{margin:"8px 16px 18px",padding:"10px 12px",background:"#060C16",borderRadius:10,borderLeft:"2px solid #1E3A5F"}}>
          <div style={{fontSize:9,color:"#334155",letterSpacing:2,marginBottom:4}}>CONTEXTO</div>
          <div style={{fontSize:11,color:"#94A3B8",lineHeight:1.65}}>{m.note}</div>
        </div>}
      </div>
    </div>
  );
};

const AccuracyBar = ({label,value,max,color,icon}) => (
  <div style={{marginBottom:9}}>
    <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
      <span style={{fontSize:11,color:"#CBD5E1"}}>{icon} {label}</span>
      <span style={{fontSize:12,fontWeight:800,color}}>{value} pts</span>
    </div>
    <div style={{background:"#0D1525",borderRadius:6,height:8,overflow:"hidden"}}>
      <div style={{width:`${max>0?value/max*100:0}%`,height:"100%",borderRadius:6,background:`linear-gradient(90deg,${color}88,${color})`}}/>
    </div>
  </div>
);

export default function Dashboard({ db }){
  const MATCHES = db.matches || [];
  const BT = db.backtest || {rows:[]};
  const PARAMS = db.params || {};
  const GROUPS = [...new Set(MATCHES.map(m => m.gid))].sort();

  const [tab,setTab]=useState("★");
  const [sel,setSel]=useState(null);
  const [showBT,setShowBT]=useState(false);
  const updFmt=new Intl.DateTimeFormat("es-CO",{weekday:"short",day:"numeric",month:"short",hour:"numeric",minute:"2-digit",hour12:true,timeZone:"America/Bogota"});
  const updated=db.updated?updFmt.format(new Date(db.updated)):null;
  const [pin,setPin]=useState("");
  const [busy,setBusy]=useState(false);
  const [msg,setMsg]=useState("");
  async function trigger(){
    if(!pin){setMsg("Escribe el código primero.");return;}
    setBusy(true);setMsg("Disparando…");
    try{
      const r=await fetch("/api/trigger",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pin})});
      const d=await r.json();
      setMsg(d.ok?"✅ ¡Disparado! Se actualiza en ~30-60s (recarga la página).":("❌ "+(d.error||("Error "+r.status))));
      if(d.ok)setPin("");
    }catch(e){setMsg("❌ "+e.message);}
    setBusy(false);
  }
  const played=MATCHES.filter(m=>m.result);
  const ex=played.filter(m=>getStatus(m)==="exact").length;
  const co=played.filter(m=>getStatus(m)==="correct").length;
  const wr=played.filter(m=>getStatus(m)==="wrong").length;
  const byDate=MATCHES.reduce((a,m)=>({...a,[m.date]:[...(a[m.date]||[]),m]}),{});
  const dnum=(d)=>+String(d).replace(/[^0-9]/g,"");
  const dates=Object.keys(byDate).sort((a,b)=>dnum(a)-dnum(b));
  const cur=tab!=="★"?MATCHES.filter(m=>m.gid===tab):[];
  const btn=a=>({padding:"6px 12px",borderRadius:7,border:"1px solid",borderColor:a?"#FFB800":"#1E293B",backgroundColor:a?"#FFB800":"#0F1828",color:a?"#06090E":"#64748B",fontWeight:700,fontSize:12,cursor:"pointer"});
  const stats=[["⚽",played.length+"/"+MATCHES.length,"Jugados"],["✅",ex,"Exactos"],["🎯",co,"Acertados"],["❌",wr,"Fallidos"],["📊",BT.recPoints,"Pts modelo*"]];
  const maxpts=Math.max(BT.recPoints||0,BT.modalPoints||0,BT.heurPoints||0);

  return (
    <div style={{background:"#06090E",minHeight:"100vh",fontFamily:"system-ui,-apple-system,sans-serif",color:"#E2E8F0",padding:16}}>
      <div style={{textAlign:"center",paddingBottom:18,borderBottom:"1px solid #1E293B",marginBottom:18}}>
        <div style={{fontSize:9,color:"#FFB800",letterSpacing:5,marginBottom:6,textTransform:"uppercase"}}>⚽ FIFA World Cup 2026 · Mercado (cuotas) + Poisson-Elo</div>
        <h1 style={{margin:0,fontSize:"clamp(22px,6vw,44px)",fontWeight:900,letterSpacing:-1,background:"linear-gradient(130deg,#FFB800,#FF6B35,#FFB800)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"}}>PRONÓSTICOS & RESULTADOS</h1>
        <div style={{color:"#334155",fontSize:11,marginTop:5}}>Pick optimizado para polla 6/4/3 · toca cualquier partido para el detalle</div>
        {updated && <div style={{display:"inline-block",marginTop:10,background:"#0F1828",border:"1px solid #1E293B",borderRadius:20,padding:"4px 12px",fontSize:11,color:"#7dd3fc"}}>🕒 Última actualización: {updated} (Bogotá)</div>}
        <div style={{marginTop:12,display:"flex",gap:6,justifyContent:"center",alignItems:"center",flexWrap:"wrap"}}>
          <input type="password" inputMode="numeric" value={pin} onChange={e=>setPin(e.target.value)} placeholder="código"
            style={{background:"#0B1220",border:"1px solid #1E293B",borderRadius:8,color:"#E2E8F0",padding:"7px 10px",fontSize:13,width:110,textAlign:"center"}}/>
          <button onClick={trigger} disabled={busy}
            style={{background:busy?"#1E293B":"#FFB800",color:busy?"#64748B":"#06090E",border:"none",borderRadius:8,padding:"8px 14px",fontWeight:700,fontSize:13,cursor:busy?"default":"pointer"}}>
            {busy?"…":"🔄 Actualizar ahora"}</button>
        </div>
        {msg && <div style={{fontSize:11,color:"#94A3B8",marginTop:7}}>{msg}</div>}
        <div style={{display:"flex",justifyContent:"center",gap:7,marginTop:14,flexWrap:"wrap"}}>
          {stats.map(([e,v,l])=>(
            <div key={l} style={{background:"#0F1828",borderRadius:10,padding:"8px 12px",textAlign:"center",border:"1px solid #1E293B",minWidth:58}}>
              <div style={{fontSize:14}}>{e}</div><div style={{fontSize:18,fontWeight:800,color:"#FFB800",lineHeight:1}}>{v}</div>
              <div style={{fontSize:9,color:"#475569",marginTop:2}}>{l}</div>
            </div>
          ))}
        </div>
        <div style={{marginTop:16}}>
          <button onClick={()=>setShowBT(!showBT)} style={{background:"none",border:"1px solid #1E293B",borderRadius:8,color:"#7dd3fc",fontSize:12,cursor:"pointer",padding:"6px 16px"}}>{showBT?"▲":"▼"} Backtest del modelo ({BT.n||0} jugados)</button>
          {showBT && (
            <div style={{marginTop:12,background:"#0F1828",borderRadius:12,padding:"16px 18px",border:"1px solid #1E293B",textAlign:"left",maxWidth:520,margin:"12px auto 0"}}>
              <div style={{fontSize:11,color:"#94A3B8",marginBottom:12,lineHeight:1.5}}>Puntos que cada estrategia habría sumado en los <b style={{color:"#cbd5e1"}}>{BT.n} partidos ya jugados</b>, con el sistema 6/4/3:</div>
              <AccuracyBar label="Modelo (híbrido recomendado)" value={BT.recPoints} max={maxpts} color="#4ADE80" icon="📊"/>
              <AccuracyBar label="Marcador más probable" value={BT.modalPoints} max={maxpts} color="#7dd3fc" icon="🎲"/>
              <AccuracyBar label="Método anterior (heurístico)" value={BT.heurPoints} max={maxpts} color="#FFB800" icon="✋"/>
              <div style={{fontSize:10,color:"#64748b",margin:"6px 0 12px",lineHeight:1.5}}>Brier 1X2: <b style={{color:"#cbd5e1"}}>{BT.brierModel}</b> vs azar {BT.brierUnif} (menor = mejor calibrado). *El modelo sube ~40% sobre el método anterior, aunque parte de la ventaja viene de clavar 3 empates 1-1 (suerte de muestra pequeña).</div>
              <div style={{borderTop:"1px solid #1E293B",paddingTop:10}}>
                <div style={{fontSize:9,color:"#334155",letterSpacing:2,marginBottom:8}}>DETALLE (recomendado vs real vs método anterior)</div>
                {(BT.rows||[]).map((r,i)=>(
                  <div key={i} style={{display:"flex",alignItems:"center",gap:6,padding:"4px 0",borderBottom:"1px solid #0D1525"}}>
                    <span style={{fontSize:10,color:"#475569",minWidth:16}}>G{r.g}</span>
                    <span style={{fontSize:11,flex:1,color:"#CBD5E1"}}>{r.home.slice(0,11)} v {r.away.slice(0,9)}</span>
                    <span style={{fontSize:10,color:"#7dd3fc",fontVariantNumeric:"tabular-nums"}}>{r.rec}</span>
                    <span style={{fontSize:10,color:"#fff",minWidth:30,textAlign:"center",fontVariantNumeric:"tabular-nums"}}>{r.actual}</span>
                    <span style={{fontSize:10,fontWeight:700,minWidth:34,textAlign:"right",color:r.recpts>=6?"#4ADE80":r.recpts>=3?"#FFB800":"#475569"}}>{r.recpts}pt</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{display:"flex",gap:5,marginBottom:18,flexWrap:"wrap",justifyContent:"center"}}>
        <button onClick={()=>setTab("★")} style={btn(tab==="★")}>★ Resumen</button>
        {GROUPS.map(g=>{
          const gp=MATCHES.filter(m=>m.gid===g&&m.result);
          const ge=gp.filter(m=>getStatus(m)==="exact").length, gc=gp.filter(m=>getStatus(m)==="correct").length;
          return (
            <button key={g} onClick={()=>setTab(g)} style={{...btn(tab===g),position:"relative"}}>{g}
              {gp.length>0 && <span style={{position:"absolute",top:-5,right:-5,background:ge>0?"#4ADE80":gc>0?"#FFB800":"#F87171",color:"#06090E",fontSize:8,fontWeight:800,width:14,height:14,borderRadius:"50%",display:"flex",alignItems:"center",justifyContent:"center"}}>{gp.length}</span>}
            </button>
          );
        })}
      </div>

      {tab==="★"?(
        <div>{dates.map(dt=>(
          <div key={dt} style={{marginBottom:18}}>
            <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
              <span style={{background:"#FFB800",color:"#06090E",fontSize:11,fontWeight:700,padding:"3px 12px",borderRadius:20}}>{dt}</span>
              <div style={{flex:1,height:1,background:"#1E293B"}}/>
              <span style={{color:"#334155",fontSize:10}}>{byDate[dt].length} partidos</span>
            </div>
            {byDate[dt].map((m,i)=>{
              const stt=STATUS[getStatus(m)], rv=m.predictions.length>1;
              return (
                <div key={i} onClick={()=>setSel(m)} style={{background:"#0F1828",borderRadius:9,border:`1px solid ${stt.border}`,padding:"8px 12px",display:"flex",alignItems:"center",gap:7,marginBottom:5,cursor:"pointer"}}>
                  <span style={{background:"rgba(255,184,0,0.1)",color:"#FFB800",fontSize:9,fontWeight:700,padding:"2px 7px",borderRadius:20,minWidth:24,textAlign:"center"}}>G{m.gid}</span>
                  <div style={{flex:1,display:"flex",alignItems:"center",gap:5}}><span style={{fontSize:18}}>{m.home.flag}</span><span style={{fontSize:10,fontWeight:600,color:m.hs>m.as_?"#4ADE80":"#CBD5E1"}}>{m.home.name}</span></div>
                  <div style={{textAlign:"center",minWidth:42}}><div style={{fontSize:8,color:"#334155"}}>{m.model?"PICK":"PRED"} {rv&&<span style={{color:"#60A5FA"}}>🔄</span>}</div><div style={{fontSize:14,fontWeight:800,color:m.hs===m.as_?"#475569":"#FFB800"}}>{m.hs}–{m.as_}</div></div>
                  {m.result?(<><span style={{color:"#1E293B"}}>→</span><div style={{textAlign:"center",minWidth:42}}><div style={{fontSize:8,color:stt.color}}>REAL</div><div style={{fontSize:14,fontWeight:800,color:"#fff"}}>{m.result.hs}–{m.result.as_}</div></div></>):(<div style={{minWidth:42,textAlign:"center",fontSize:10,color:"#1E293B"}}>⏳</div>)}
                  <div style={{flex:1,display:"flex",alignItems:"center",gap:5,justifyContent:"flex-end"}}><span style={{fontSize:10,fontWeight:600,textAlign:"right",color:m.as_>m.hs?"#4ADE80":"#CBD5E1"}}>{m.away.name}</span><span style={{fontSize:18}}>{m.away.flag}</span></div>
                  <span style={{fontSize:14,minWidth:20,textAlign:"center"}}>{stt.icon}</span>
                </div>
              );
            })}
          </div>
        ))}</div>
      ):(
        <div>
          <div style={{textAlign:"center",marginBottom:16}}><div style={{fontSize:24,fontWeight:900,color:"#FFB800"}}>GRUPO {tab}</div></div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(290px,1fr))",gap:12}}>
            {cur.map((m,i)=><Card key={i} m={m} onOpen={()=>setSel(m)}/>)}
          </div>
        </div>
      )}

      <div style={{marginTop:20,padding:"12px 14px",background:"#0F1828",borderRadius:10,border:"1px solid #1E293B"}}>
        <div style={{fontSize:9,color:"#334155",letterSpacing:3,marginBottom:8,textTransform:"uppercase"}}>Cómo funciona</div>
        <div style={{fontSize:10,color:"#64748b",lineHeight:1.7}}>
          <b style={{color:"#7dd3fc"}}>Cómo se calcula:</b> manda el <b>mercado de cuotas</b> (the-odds-api) — sus <b>totales</b> dan los goles esperados (λ) y su <b>hándicap</b> la supremacía; eso define la distribución de marcadores (<b>Poisson + Dixon-Coles</b>). El <b>Poisson-Elo</b> solo matiza o sirve de respaldo cuando no hay cuotas. <b style={{color:"#7dd3fc"}}>Pick:</b> el <b>marcador más probable</b> de esa distribución. Las barras muestran probabilidad de victoria local (verde) / empate (gris) / visitante (azul). Se recalcula cada día con resultados y cuotas frescas; puedes forzar un marcador (BetAlpha) con el override.
        </div>
      </div>
      <Modal key={sel?sel.fixtureId:"none"} m={sel} onClose={()=>setSel(null)}/>
    </div>
  );
}

// static/js/pages/setPage.js
(() => {
  const MAX_SLOTS = 6;
  const form = document.getElementById("setForm");
  const btn = document.getElementById("btnGenerateSet");
  const resultsEl = document.getElementById("setResults");
  const themeInput = document.getElementById("setTheme");
  const refInput = document.getElementById("setRef");

  const titleCase = s => s ? s[0].toUpperCase()+s.slice(1) : "";

  function makePlaceholder(label="Available"){
    return `<div style="color:#888;font-size:12px;text-align:center;">${label}</div>`;
  }

  function ensureSlots(){
    resultsEl.innerHTML="";
    for(let i=0;i<MAX_SLOTS;i++){
      const card=document.createElement("div");
      card.className="piece-card empty"; card.dataset.slot=i;
      card.innerHTML=makePlaceholder("Available");
      resultsEl.appendChild(card);
    }
  }

  function setLoading(i,label){
    const card=resultsEl.querySelector(`[data-slot="${i}"]`);
    if(card){
      card.innerHTML=`<div class="spinner"></div><span class="label">${label} • generating…</span>`;
    }
  }

  function setImage(i,label,url){
    const card=resultsEl.querySelector(`[data-slot="${i}"]`);
    if(card){
      card.innerHTML=`<img src="${url}" alt="${label}"><span class="label">${label}</span>`;
    }
  }

  function setEmpty(i,label){
    const card=resultsEl.querySelector(`[data-slot="${i}"]`);
    if(card){
      card.innerHTML=makePlaceholder(label);
    }
  }

  async function onGenerate(){
    btn.disabled=true;
    const pieces=[...document.querySelectorAll('.toggle input:checked')].map(i=>i.value);
    if(!pieces.length){ alert("Select at least one piece."); btn.disabled=false; return; }

    ensureSlots();
    const order=pieces.slice(0,MAX_SLOTS);
    order.forEach((p,i)=>setLoading(i,titleCase(p)));

    const fd=new FormData();
    const theme=(themeInput?.value||"").trim();
    if(theme) fd.append("theme",theme);
    const refFile=refInput?.files?.[0];
    if(refFile) fd.append("ref_image",refFile);
    pieces.forEach(p=>fd.append("pieces",p));

    try{
      const res=await fetch("/api/set-simple",{method:"POST",body:fd});
      const data=await res.json();
      if(!res.ok||!data.ok) throw new Error(data?.error?.message||"Failed");

      const pieceToSlot=new Map(order.map((p,i)=>[p,i]));
      (data.results||[]).forEach(r=>{
        const idx=pieceToSlot.get(r.piece);
        if(idx!==undefined) setImage(idx,titleCase(r.piece),r.url);
      });
      order.forEach(p=>{
        const idx=pieceToSlot.get(p);
        if(!resultsEl.querySelector(`[data-slot="${idx}"] img`))
          setEmpty(idx,titleCase(p));
      });
    }catch(e){
      console.error(e); alert("Error: "+e.message);
      order.forEach((p,i)=>setEmpty(i,titleCase(p)));
    }finally{ btn.disabled=false; }
  }

  ensureSlots();
  form.addEventListener("submit",e=>{e.preventDefault();onGenerate();});
})();

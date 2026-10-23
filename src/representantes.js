// Meus representantes (#59): o visitante escolhe o estado e ve quem o representa hoje. O arquivo do estado
// (representantes/UF.json) so e baixado na escolha; a escolha fica neste navegador (localStorage, sem cookie).
(()=>{
  // so aparece depois que o pipeline gravou os arquivos (D.representantes = quantas pessoas)
  const box=document.getElementById("meus");if(!box||typeof D!=="object"||!D||!D.representantes)return;
  const sel=document.getElementById("meu-uf"),corpo=document.getElementById("meus-corpo");
  const CHAVE="cv-meu-estado",PRIMEIROS=6;
  const UFS={AC:"Acre",AL:"Alagoas",AP:"Amapá",AM:"Amazonas",BA:"Bahia",CE:"Ceará",DF:"Distrito Federal",ES:"Espírito Santo",
    GO:"Goiás",MA:"Maranhão",MT:"Mato Grosso",MS:"Mato Grosso do Sul",MG:"Minas Gerais",PA:"Pará",PB:"Paraíba",PR:"Paraná",
    PE:"Pernambuco",PI:"Piauí",RJ:"Rio de Janeiro",RN:"Rio Grande do Norte",RS:"Rio Grande do Sul",RO:"Rondônia",
    RR:"Roraima",SC:"Santa Catarina",SP:"São Paulo",SE:"Sergipe",TO:"Tocantins"};
  const CARGO={governador:"Governador",senadores:"Senador",federais:"Deputado federal",estaduais:"Deputado estadual"};
  const ico=k=>typeof ICO==="object"&&ICO[k]||"";  // icones do painel (template.html), quando houver
  const MARCA={exemplar:["exemplar","Parlamentar exemplar","Patrimônio compatível com o salário, cota abaixo da média e sem sanções"],
    selo:["selo","Mão na massa","Entre os 10% da sua casa com mais projetos aprovados nos últimos 4 anos"]};
  const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const https=u=>/^https:\/\//.test(u||"");
  const rel=u=>u&&!/^\s*[a-z][a-z0-9+.-]*:/i.test(u);
  const brl=v=>new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",notation:"compact",maximumFractionDigits:1}).format(v);
  const iniciais=n=>n.split(/\s+/).filter(w=>w.length>2).slice(0,2).map(w=>w[0]).join("").toUpperCase();
  // feed RSS por pessoa (thread RSS): existe para quem tem pessoa/pNNNN.html
  const feed=u=>{const m=/^pessoa\/(p\d+)\.html$/.exec(u||"");return m?`<a class="lk" href="feed/${m[1]}.xml" title="Receba um aviso (RSS) quando um dado mudar">Acompanhar</a>`:"";};
  const cache=new Map();
  const ler=()=>{try{return localStorage.getItem(CHAVE)||"";}catch(e){return"";}};
  const gravar=uf=>{try{uf?localStorage.setItem(CHAVE,uf):localStorage.removeItem(CHAVE);}catch(e){}};

  sel.append(...Object.entries(UFS).map(([uf,nome])=>{const o=document.createElement("option");o.value=uf;o.textContent=nome;return o;}));

  // uma linha de dados por parlamentar: cota comparada com a media da casa e projetos aprovados
  function numeros(p){
    const cota=p.cota==null?"Não informado":`${p.cota_link&&https(p.cota_link)?`<a href="${esc(p.cota_link)}" target="_blank" rel="noopener">${brl(p.cota)}</a>`:brl(p.cota)}`
      +(p.cota_media?` <small class="${p.cota>p.cota_media?"acima":"abaixo"}">${p.cota>p.cota_media?"acima":"abaixo"} da média (${brl(p.cota_media)})</small>`:"");
    const proj=p.apresentados==null?"Não informado":`${(p.aprovados??0).toLocaleString("pt-BR")} de ${p.apresentados.toLocaleString("pt-BR")} apresentados`;
    const pr=p.presenca,pres=pr&&pr.pct!=null?`<div><dt>Presença</dt><dd>${pr.link&&https(pr.link)?`<a href="${esc(pr.link)}" target="_blank" rel="noopener">${esc(pr.pct)}%</a>`:`${esc(pr.pct)}%`}${pr.media_casa!=null?` <small>média da casa ${esc(pr.media_casa)}%</small>`:""}</dd></div>`:"";
    const votos=p.votos?`<div><dt>Temas importantes</dt><dd>Votou em ${p.votos[0]} de ${p.votos[1]}</dd></div>`:"";
    return`<dl class="rep-num"><div><dt>Gastou da cota (4 anos)</dt><dd>${cota}</dd></div><div><dt>Projetos aprovados</dt><dd>${proj}</dd></div>${pres}${votos}</dl>`;
  }
  function pessoa(p,g,uf){
    const cargo=g==="estaduais"&&uf==="DF"?"Deputado distrital":CARGO[g];
    const foto=https(p.foto)?`<img src="${esc(p.foto)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`:"";
    const tags=(p.marcas||[]).filter(m=>MARCA[m]).map(m=>`<span class="tag ${MARCA[m][0]}" title="${esc(MARCA[m][2])}">${ico(m==="selo"?"pata":"estrela")} ${esc(MARCA[m][1])}</span>`).join("");
    const parl=g==="senadores"||g==="federais";
    const links=[https(p.perfil)?`<a class="lk" href="${esc(p.perfil)}" target="_blank" rel="noopener">${parl?"Perfil oficial":"Candidatura no TSE"}</a>`:"",
      rel(p.dossie)?`<a class="lk" href="${esc(p.dossie)}">Dossiê</a>`:"",feed(p.dossie)].filter(Boolean).join(" · ");
    return`<li class="rep"><span class="avatar" aria-hidden="true">${esc(iniciais(p.nome))}${foto}</span><div class="rep-txt">
<p class="rep-nome"><b>${esc(p.nome)}</b> <small>${esc(cargo)} · ${esc(p.partido||"Não informado")}</small></p>${tags?`<p class="tags">${tags}</p>`:""}
${parl?numeros(p):""}${links?`<p class="rep-links">${links}</p>`:""}</div></li>`;
  }
  function grupo(g,uf){
    const n=g.pessoas.length;if(!n)return"";
    const tit=g.id==="estaduais"&&uf==="DF"?"Deputados distritais":g.titulo;
    const mais=n>PRIMEIROS?`<p class="mais"><button type="button" class="botao rep-mais" aria-expanded="false">Ver todos os ${n}</button></p>`:"";
    return`<section class="rep-grupo${n>PRIMEIROS?" curto":""}" data-g="${esc(g.id)}"><h3>${esc(tit)} <small>(${n})</small></h3>
<ul class="rep-lista">${g.pessoas.map(p=>pessoa(p,g.id,uf)).join("")}</ul>${mais}</section>`;
  }
  // "1 governador, 3 senadores, 70 deputados federais e 94 deputados estaduais"
  const ROT={governador:["governador","governadores"],senadores:["senador","senadores"],federais:["deputado federal","deputados federais"],
    estaduais:["deputado estadual","deputados estaduais"],distritais:["deputado distrital","deputados distritais"]};
  function resumo(d){
    const partes=d.grupos.filter(g=>g.pessoas.length).map(g=>{const n=g.pessoas.length,r=ROT[g.id==="estaduais"&&d.uf==="DF"?"distritais":g.id]||[g.titulo,g.titulo];
      return`${n} ${r[n>1?1:0]}`;});
    return partes.length?partes.join(", ").replace(/, ([^,]*)$/," e $1"):"Não informado";
  }
  function mostrar(d){
    const uf=d.uf,nome=UFS[uf];
    corpo.innerHTML=`<p class="rep-resumo">${esc(nome)} tem hoje <b>${esc(resumo(d))}</b>. Eles trabalham para você: confira e cobre.</p>
<p class="rep-acoes"><button type="button" class="botao" id="meus-filtrar">Ver ${esc(uf)} nos destaques</button> <a class="botao" href="estado/${esc(uf)}.html">Gastos de ${esc(nome)}</a> <a class="botao" href="feed/uf-${esc(uf)}.xml" title="Receba um aviso (RSS) quando um dado mudar">Acompanhar ${esc(uf)}</a></p>
${d.grupos.map(g=>grupo(g,uf)).join("")}<p class="fonte">Fontes: Câmara dos Deputados, Senado Federal e TSE${d.eleicao_estadual?` (eleitos em ${esc(d.eleicao_estadual)})`:""}. Atualizado em ${esc(d.gerado_em||"Não informado")}.</p>`;
  }
  async function carregar(uf){
    if(!cache.has(uf))cache.set(uf,fetch(`representantes/${uf}.json`).then(r=>{if(!r.ok)throw new Error(r.status);return r.json();}));
    return cache.get(uf);
  }
  async function escolher(uf){
    sel.value=uf;gravar(uf);box.classList.toggle("escolhido",!!uf);
    if(!uf){corpo.replaceChildren();return;}
    corpo.innerHTML=`<p class="rep-resumo">Farejando quem representa ${esc(UFS[uf])}…</p>`;
    try{const d=await carregar(uf);if(sel.value===uf)mostrar(d);}
    catch(e){cache.delete(uf);if(sel.value===uf)corpo.innerHTML=`<p class="rep-resumo">Fonte não encontrada. Tente de novo mais tarde.</p>`;}
  }
  sel.onchange=()=>escolher(UFS[sel.value]?sel.value:"");
  corpo.onclick=ev=>{
    const b=ev.target.closest("button");if(!b)return;
    if(b.id==="meus-filtrar"&&typeof F==="object"&&typeof draw==="function"){F.uf=sel.value;F.regiao="";if(typeof verDestaques==="function"){draw();verDestaques();}else draw();return;}
    if(b.classList.contains("rep-mais")){const s=b.closest(".rep-grupo"),aberto=s.classList.toggle("curto");b.setAttribute("aria-expanded",!aberto);
      b.textContent=aberto?`Ver todos os ${s.querySelectorAll(".rep").length}`:"Mostrar menos";}
  };
  // link vindo de fora (paginas de estado): index.html#meus=SP escolhe o estado e rola ate o bloco
  const pedido=(location.hash.match(/^#meus=([A-Z]{2})$/)||[])[1],salvo=UFS[pedido]?pedido:ler();
  box.hidden=false;
  if(UFS[salvo])escolher(salvo);
  if(UFS[pedido])box.scrollIntoView({block:"start"});
})();

// Meus representantes (#59): o visitante escolhe o estado e ve quem o representa hoje. O arquivo do estado
// (representantes/UF.json) so e baixado na escolha; a escolha fica neste navegador (localStorage, sem cookie).
(()=>{
  // so aparece depois que o pipeline gravou os arquivos (D.representantes = quantas pessoas)
  const box=document.getElementById("meus");if(!box||typeof D!=="object"||!D||!D.representantes)return;
  const sel=document.getElementById("meu-uf"),corpo=document.getElementById("meus-corpo");
  const CHAVE="cv-meu-estado",CHAVE_CID="cv-minha-cidade",PRIMEIROS=6;
  const UFS={AC:"Acre",AL:"Alagoas",AP:"Amapá",AM:"Amazonas",BA:"Bahia",CE:"Ceará",DF:"Distrito Federal",ES:"Espírito Santo",
    GO:"Goiás",MA:"Maranhão",MT:"Mato Grosso",MS:"Mato Grosso do Sul",MG:"Minas Gerais",PA:"Pará",PB:"Paraíba",PR:"Paraná",
    PE:"Pernambuco",PI:"Piauí",RJ:"Rio de Janeiro",RN:"Rio Grande do Norte",RS:"Rio Grande do Sul",RO:"Rondônia",
    RR:"Roraima",SC:"Santa Catarina",SP:"São Paulo",SE:"Sergipe",TO:"Tocantins"};
  const CARGO={governador:"Governador",senadores:"Senador",federais:"Deputado federal",estaduais:"Deputado estadual",prefeito:"Prefeito",vice:"Vice-prefeito",vereadores:"Vereador"};
  const ico=k=>typeof ICO==="object"&&ICO[k]||"";  // icones do painel (template.html), quando houver
  const MARCA={exemplar:["exemplar","Parlamentar exemplar","Patrimônio compatível com o salário, cota abaixo da média e sem sanções"],
    selo:["selo","Mão na massa","Entre os 10% da sua casa com mais projetos aprovados nos últimos 4 anos"]};
  // numeros sempre no padrao brasileiro: 43,5% (virgula no decimal, ponto no milhar)
  const PCT=v=>Number(v).toLocaleString("pt-BR",{maximumFractionDigits:1})+"%";
  const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const https=u=>/^https:\/\//.test(u||"");
  const rel=u=>u&&!/^\s*[a-z][a-z0-9+.-]*:/i.test(u);
  const iniciais=n=>n.split(/\s+/).filter(w=>w.length>2).slice(0,2).map(w=>w[0]).join("").toUpperCase();
  // feed RSS por pessoa (thread RSS): existe para quem tem pessoa/pNNNN.html
  // todo link de feed e so o icone de RSS (.rss em estilo.css); o rotulo fica no title e no aria-label
  const RSS='<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor"><circle cx="3" cy="13" r="2"/><path d="M1 7.5a7.5 7.5 0 0 1 7.5 7.5h-2A5.5 5.5 0 0 0 1 9.5z"/><path d="M1 2a13 13 0 0 1 13 13h-2A11 11 0 0 0 1 4z"/></svg>';
  const rss=(href,rot,cls="rss")=>`<a class="${cls}" href="${href}" title="${esc(rot)}" aria-label="${esc(rot)}">${RSS}</a>`;
  const feed=u=>{const m=/^pessoa\/(p\d+)\.html$/.exec(u||"");return m?rss(`feed/${m[1]}.xml`,"Acompanhar por RSS: aviso quando um dado mudar","rss leve"):"";};
  // aba "Como cobrar" da pagina da pessoa (thread Como cobrar): texto pronto para mandar
  const cobrar=u=>/^pessoa\/p\d+\.html$/.test(u||"")?`<a class="lk" href="${esc(u)}#cobrar">texto pronto</a>`:"";
  const cache=new Map();
  const ler=(k=CHAVE)=>{try{return localStorage.getItem(k)||"";}catch(e){return"";}};
  const gravar=(v,k=CHAVE)=>{try{v?localStorage.setItem(k,v):localStorage.removeItem(k);}catch(e){}};
  const json=url=>{if(!cache.has(url))cache.set(url,fetch(url).then(r=>{if(!r.ok)throw new Error(r.status);return r.json();}).catch(e=>{cache.delete(url);throw e;}));return cache.get(url);};

  sel.append(...Object.entries(UFS).map(([uf,nome])=>{const o=document.createElement("option");o.value=uf;o.textContent=nome;return o;}));

  // uma linha de dados por parlamentar: cota comparada com a media da casa e projetos aprovados
  function numeros(p){
    // cota em percentual da media da casa (regra do site: percentual em vez de valor em reais)
    const dif=p.cota!=null&&p.cota_media?Math.round((p.cota/p.cota_media-1)*100):null;
    const txt=dif==null?(p.cota==null?"Não informado":"Sem média da casa"):dif===0?"Na média da casa":`${PCT(Math.abs(dif))} ${dif>0?"acima":"abaixo"} da média`;
    const cota=dif!=null&&p.cota_link&&https(p.cota_link)?`<a class="${dif>0?"acima":"abaixo"}" href="${esc(p.cota_link)}" target="_blank" rel="noopener">${txt}</a>`:`<span class="${dif>0?"acima":"abaixo"}">${txt}</span>`;
    const proj=p.apresentados==null?"Não informado":`${(p.aprovados??0).toLocaleString("pt-BR")} de ${p.apresentados.toLocaleString("pt-BR")} apresentados`;
    const pr=p.presenca,pres=pr&&pr.pct!=null?`<div><dt>Presença</dt><dd>${pr.link&&https(pr.link)?`<a href="${esc(pr.link)}" target="_blank" rel="noopener">${PCT(pr.pct)}</a>`:PCT(pr.pct)}${pr.media_casa!=null?` <small>média da casa ${PCT(pr.media_casa)}</small>`:""}</dd></div>`:"";
    const votos=p.votos?`<div><dt>Temas importantes</dt><dd>Votou em ${p.votos[0]} de ${p.votos[1]}</dd></div>`:"";
    return`<dl class="rep-num"><div><dt>Gasto da cota (4 anos)</dt><dd>${cota}</dd></div><div><dt>Projetos aprovados</dt><dd>${proj}</dd></div>${pres}${votos}</dl>`;
  }
  function pessoa(p,g,uf){
    const cargo=g==="estaduais"&&uf==="DF"?"Deputado distrital":CARGO[g];
    const foto=https(p.foto)?`<img src="${esc(p.foto)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`:"";
    const tags=(p.marcas||[]).filter(m=>MARCA[m]).map(m=>`<span class="tag ${MARCA[m][0]}" title="${esc(MARCA[m][2])}">${ico(m==="selo"?"pata":"estrela")} ${esc(MARCA[m][1])}</span>`).join("");
    const parl=g==="senadores"||g==="federais";
    const links=[https(p.perfil)?`<a class="lk" href="${esc(p.perfil)}" target="_blank" rel="noopener">${parl?"Perfil oficial":"Candidatura no TSE"}</a>`:"",
      rel(p.dossie)?`<a class="lk" href="${esc(p.dossie)}">Dossiê</a>`:"",feed(p.dossie)].filter(Boolean).join(" · ");
    const c=p.contato||{},tel=(c.telefone||"").replace(/\D/g,"");
    const fale=parl&&(c.email||tel)?`<p class="rep-fale"><b>Cobre direto:</b> ${[c.email?`<a class="lk" href="mailto:${esc(c.email)}">e-mail</a>`:"",
      tel?`<a class="lk" href="tel:+55${esc(tel)}">${esc(c.telefone)}</a>`:"",cobrar(p.dossie)].filter(Boolean).join(" · ")}</p>`:"";
    return`<li class="rep"><span class="avatar" aria-hidden="true">${esc(iniciais(p.nome))}${foto}</span><div class="rep-txt">
<p class="rep-nome"><b>${esc(p.nome)}</b> <small>${esc(cargo)} · ${esc(p.partido||"Não informado")}</small></p>${tags?`<p class="tags">${tags}</p>`:""}
${parl?numeros(p):""}${fale}${links?`<p class="rep-links">${links}</p>`:""}</div></li>`;
  }
  function grupo(g,uf,ala_){
    const n=g.pessoas.length;if(!n)return"";
    const tit=g.id==="estaduais"&&uf==="DF"?"Deputados distritais":g.titulo;
    const mais=n>PRIMEIROS?`<p class="mais"><button type="button" class="botao rep-mais" aria-expanded="false">Ver todos os ${n}</button></p>`:"";
    const ala=g.id==="estaduais"&&ala_&&https(ala_.site)?` <a class="lk" href="${esc(ala_.site)}" target="_blank" rel="noopener">Contatos na ${esc(ala_.nome)}</a>`:"";
    return`<section class="rep-grupo${n>PRIMEIROS?" curto":""}" data-g="${esc(g.id)}"><h3>${esc(tit)} <small>(${n})</small>${ala}</h3>
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
${(d.cidades||[]).length?`<p class="rep-cidade"><label for="minha-cidade">E na sua cidade?</label> <select id="minha-cidade"><option value="">Escolha sua cidade</option>${d.cidades.map(([c,n])=>`<option value="${esc(c)}">${esc(n)}</option>`).join("")}</select></p><div id="meus-cidade" aria-live="polite"></div>`:""}
<p class="rep-acoes"><button type="button" class="botao" id="meus-filtrar">Ver ${esc(uf)} nos destaques</button> <a class="botao" href="estado/${esc(uf)}.html">Gastos de ${esc(nome)}</a> ${rss(`feed/uf-${esc(uf)}.xml`,`Acompanhar ${uf} por RSS: aviso quando um dado mudar`)}</p>
${d.grupos.map(g=>grupo(g,uf,d.assembleia)).join("")}<p class="fonte">Fontes: Câmara dos Deputados, Senado Federal e TSE${d.eleicao_estadual?` (eleitos em ${esc(d.eleicao_estadual)})`:""}. Atualizado em ${esc(d.gerado_em||"Não informado")}.</p>`;
  }
  // prefeitura e camara municipal: um arquivo pequeno por cidade, baixado so na escolha
  async function cidade(cod){
    const alvo=document.getElementById("meus-cidade");if(!alvo)return;
    gravar(cod,CHAVE_CID);if(!cod){alvo.replaceChildren();return;}
    alvo.innerHTML=`<p class="rep-resumo">Farejando…</p>`;
    try{const c=await json(`representantes/cidades/${encodeURIComponent(cod)}.json`);if(document.getElementById("minha-cidade")?.value!==cod)return;
      alvo.innerHTML=`<div class="rep-cid">${c.grupos.map(g=>grupo(g,c.uf)).join("")||`<p class="rep-resumo">Não informado.</p>`}<p class="fonte">Fonte: TSE (eleitos em ${esc(c.eleicao||"Não informado")}).</p></div>`;}
    catch(e){alvo.innerHTML=`<p class="rep-resumo">Fonte não encontrada. Tente de novo mais tarde.</p>`;}
  }
  async function escolher(uf){
    sel.value=uf;gravar(uf);box.classList.toggle("escolhido",!!uf);
    if(!uf){corpo.replaceChildren();return;}
    corpo.innerHTML=`<p class="rep-resumo">Farejando quem representa ${esc(UFS[uf])}…</p>`;
    try{const d=await json(`representantes/${uf}.json`);if(sel.value!==uf)return;mostrar(d);
      const cs=document.getElementById("minha-cidade"),salva=ler(CHAVE_CID);
      if(cs){cs.onchange=()=>cidade(cs.value);if(salva&&d.cidades.some(([c])=>c===salva)){cs.value=salva;cidade(salva);}}}
    catch(e){if(sel.value===uf)corpo.innerHTML=`<p class="rep-resumo">Fonte não encontrada. Tente de novo mais tarde.</p>`;}
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

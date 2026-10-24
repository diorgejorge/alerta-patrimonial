// painel da pagina inicial (#73): fora do HTML para o navegador guardar em cache entre as visitas.
// D (dados do pipeline) e BENS (config/bens_referencia.json) vem do index.html, num <script> antes deste arquivo.
// icones flat de traco (cor do texto); um so desenho por ideia
const ICO={"mapa":'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5v15M4 5h12l-2 4 2 4H4"/></svg>',"regua":'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M3 15h18M5 15v-3M9 15v-3M13 15v-3M17 15v-3M21 15v-3"/><circle cx="19" cy="7" r="2.2" fill="currentColor" stroke="none"/></svg>',"estrela":'<svg class="ico" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true"><path d="M12 3l2.8 5.8 6.2.8-4.5 4.4 1.1 6.2L12 17.2l-5.6 3 1.1-6.2L3 9.6l6.2-.8z"/></svg>',"pata":'<svg class="ico" viewBox="0 0 24 24" fill="currentColor" stroke="none" aria-hidden="true"><ellipse cx="12" cy="16" rx="4.2" ry="3.4"/><circle cx="5.8" cy="10.6" r="1.9"/><circle cx="9.4" cy="6.6" r="1.9"/><circle cx="14.6" cy="6.6" r="1.9"/><circle cx="18.2" cy="10.6" r="1.9"/></svg>',"predio":'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 7h.01M15 7h.01M9 11h.01M15 11h.01M9 15h.01M15 15h.01M11 21v-3h2v3"/></svg>',"alta":'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg>',"moeda":'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-.9-1.6-1.5-3-1.5-1.7 0-3 .9-3 2s1.3 1.7 3 2 3 .9 3 2-1.3 2-3 2c-1.4 0-2.5-.6-3-1.5M12 6.5v11"/></svg>',"carrinho":'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="20" r="1.2"/><circle cx="18" cy="20" r="1.2"/><path d="M3 4h2.2l2.3 11.2h11.2L21 7.5H6.4"/></svg>',"balanca":'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v16M7 20h10M5 8h14M5 8l-2.5 6a3 3 0 0 0 5 0zM19 8l-2.5 6a3 3 0 0 0 5 0z"/></svg>'};
ICO.check='<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12.5l5 5L20 6.5"/></svg>';
ICO.faixa='<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 10l9-6 9 6M5 10v8M9.7 10v8M14.3 10v8M19 10v8M3 20h18"/></svg>';
ICO.urna='<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M4 11h16v9H4zM8 11V4h8v7M10 7h4"/></svg>';
ICO.equipe='<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="9" r="2.4"/><path d="M16 14.2c2.9.4 5 2.9 5 5.8"/></svg>';
// numeros sempre no padrao brasileiro (43,5% e 2.400): virgula no decimal, ponto no milhar
// formatadores criados uma vez (#73): toLocaleString monta um Intl.NumberFormat novo a cada chamada
const FORMATOS=new Map(),formato=casas=>FORMATOS.get(casas)||FORMATOS.set(casas,new Intl.NumberFormat("pt-BR",{maximumFractionDigits:casas})).get(casas);
const NUM=(v,casas=1)=>formato(casas).format(Number(v));
const PCT=v=>NUM(v)+"%";
// o bem mais caro que o crescimento compraria pelo menos uma vez: "daria para comprar 3 picapes ..."
function COMPRA(v){
  const b=(BENS&&BENS.bens||[]).filter(x=>x.preco>0&&v>=x.preco).sort((x,y)=>y.preco-x.preco)[0];
  if(!b)return"";const n=Math.floor(v/b.preco);
  return`Daria para comprar <b>${n.toLocaleString("pt-BR")}</b> ${esc(n>1?b.plural:b.singular)}${/^https:\/\//.test(b.link||"")?` · <a href="${esc(b.link)}" target="_blank" rel="noopener" title="${esc(b.referencia)}">ver preço</a>`:""}`;
}
// negativo com o sinal antes do R$: "−R$ 11.973.159"
const R=v=>v==null?"Não informado":(v<0?"−":"")+"R$ "+formato(0).format(Math.round(Math.abs(v)));
const NV={forte:"3 pegadas",atencao:"2 pegadas",informativo:"1 pegada"};  // so a cor (#62); a formula fica na legenda
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const REL=u=>u&&!/^\s*[a-z][a-z0-9+.-]*:/i.test(u);  // so caminhos relativos do proprio site
// link do TSE de um periodo
const TSE=a=>/^https:\/\//.test(a.link_tse||"")?`<a class="lk" href="${esc(a.link_tse)}" target="_blank" rel="noopener" title="Candidatura, bens e contas da campanha no TSE (DivulgaCandContas), período ${a.ano_ini}–${a.ano_fim}">TSE</a>`:"";
// processos (#51): desligados ate haver base oficial e gratuita por CPF; o pipeline liga com D.processos_ativo
const PROC_ON=D?.processos_ativo===true;
if(PROC_ON)for(const e of document.querySelectorAll("[data-processos]"))e.hidden=false;
// carimbo Eleito (#67): a legenda so aparece quando a carga ja traz o campo (antes dela, nada muda na tela)
if((D?.alertas||[]).some(a=>"eleito_atual" in a||"eleito_anos" in a))for(const e of document.querySelectorAll("[data-eleito]"))e.hidden=false;
// links da pessoa: TSE (so com um periodo; com varios, cada periodo traz o seu), dossie, noticias e busca de processos
const LK=p=>[p.per.length===1?TSE(p.per[0]):"",REL(p.pagina)?`<a class="lk" href="${esc(p.pagina)}">Raio-X</a>`:"",REL(p.pagina)&&p.cobrar?`<a class="lk" href="${esc(p.pagina)}#cobrar" title="Canais oficiais do gabinete e uma sugestão de texto para copiar">Como cobrar</a>`:"",SHARE(p),REL(p.dossie)?`<a class="lk" href="${esc(p.dossie)}"${p.mencoes?` title="${p.mencoes} ${p.mencoes>1?"menções":"menção"} na imprensa em 30 dias"`:""}>Notícias${p.mencoes?` (${p.mencoes})`:""}</a>`:"",
  PROC_ON&&`<a class="lk" href="${esc(PROC(p))}" target="_blank" rel="noopener" title="Busca pelo nome em sites de tribunais (jus.br), no Jusbrasil, no Escavador e no Processo Rápido; confira se não é outra pessoa com o mesmo nome">Conferir processos</a>`].filter(Boolean).join(" · ");
// compartilhar (#61): o compartilhar.js desenha o card numa imagem com estes dados (mesmos numeros da face do card)
const SHARE=p=>{if(!REL(p.pagina))return"";
  const n=p.cresc==null?[]:[[VO(p),`quanto o patrimônio aumentou de ${p.ano_ini} a ${p.ano_fim}`]];
  const d={nome:CAP(p.nome_urna||p.nome),ficha:[p.cargos.length?CAP(p.cargos[p.cargos.length-1]):"",p.partidos[p.partidos.length-1],p.ufs[p.ufs.length-1]].filter(Boolean).join(" · "),
    numeros:n,url:[...p.per].reverse().find(a=>/^https:\/\//.test(a.link_tse||""))?.link_tse||"https://dadosabertos.tse.jus.br/",fontes:"Fonte: declarações de bens entregues ao TSE."};
  return`<button type="button" class="lk" data-compartilhar="${esc(JSON.stringify(d))}" title="Gera uma imagem deste card para mandar no WhatsApp e nas redes">Compartilhar</button>`;};
// busca para o proprio leitor conferir processos pelo nome (o robo nao consulta esses sites)
const PROC=a=>"https://www.google.com/search?q="+encodeURIComponent(`"${(a.nome||"").trim()}" processo (site:jus.br OR site:jusbrasil.com.br OR site:escavador.com OR site:processorapido.com)`);
const NIVEIS=["forte","atencao","informativo"];
const COR=n=>`var(--${n==="informativo"?"info":n})`;
const F={partido:"",uf:"",cargo:"",regiao:"",flag:""};
// marcacoes da pessoa (uniao dos periodos): rotulo, teste e texto do botao da legenda quando ninguem tem a marcacao
const REU_OBS="Informação de lista revisada por leitores; pode ser homônimo, confira o processo. Ser réu não significa condenação";
const FLAG={eleito:["Eleito",a=>a.eleito_anos.length>0,"Nenhuma pessoa em destaque venceu eleição nesta atualização"],exemplar:["Parlamentar exemplar",a=>a.exemplar,"Nenhuma pessoa em destaque é parlamentar exemplar nesta atualização"],
  selo:["Pata na massa",a=>a.selo,"Nenhuma pessoa em destaque tem o selo Pata na massa nesta atualização"],
  renda:["Tem empresas declaradas",a=>a.outras_rendas,"Nenhuma pessoa em destaque tem empresas declaradas nesta atualização"],
  reu:["Responde a processo?",a=>(a.processos||[]).length>0,"Nenhuma pessoa em destaque está na lista de processos revisada por leitores nesta atualização"]};
if(!PROC_ON)delete FLAG.reu;
const REGIOES={Norte:"AC AM AP PA RO RR TO",Nordeste:"AL BA CE MA PB PE PI RN SE","Centro-Oeste":"DF GO MS MT",Sudeste:"ES MG RJ SP",Sul:"PR RS SC"};
const REG={BR:"Nacional",ZZ:"Exterior"};for(const [r,ufs] of Object.entries(REGIOES))for(const u of ufs.split(" "))REG[u]=r;
const RC=v=>new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",notation:"compact",maximumFractionDigits:1}).format(v);
const $=id=>document.getElementById(id);
const el=(t,c,txt)=>{const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e;};
// uma pessoa por card/linha (regra do site: sem redundancia); os periodos (registros de D.alertas) ficam dentro
const ORD={forte:0,atencao:1,informativo:2};
function agrupaPessoas(l){
  const m=new Map();for(const a of l){const k=a.pessoa||`${a.nome}|${a.uf}`;if(!m.has(k))m.set(k,[]);m.get(k).push(a);}
  return[...m.values()].map(per=>{
    per=[...per].sort((x,y)=>(x.ano_ini||0)-(y.ano_ini||0)||(x.ano_fim||0)-(y.ano_fim||0));
    const u=c=>[...new Set(per.map(a=>a[c]).filter(Boolean))],ult=per[per.length-1],cs=per.map(a=>a.cresc).filter(v=>v!=null);
    // periodo de maior crescimento: e nele que fica o alerta (nivel do card); o crescimento do card e a soma dos periodos
    const maior=per.reduce((x,a)=>(a.cresc??-Infinity)>(x.cresc??-Infinity)?a:x,per[0]);
    const procs=[...new Map(per.flatMap(a=>a.processos||[]).map(x=>[`${x.tribunal}|${x.numero}`,x])).values()],qe=per.map(a=>a.qtd_empresas).filter(v=>v!=null);
    return{per,nome:ult.nome,nome_urna:ult.nome_urna||per.find(a=>a.nome_urna)?.nome_urna,cargos:u("cargo"),partidos:u("partido"),ufs:u("uf"),
      maior,nivel:maior.nivel,cresc:cs.length?cs.reduce((s,v)=>s+v,0):null,pat_ini:per[0].pat_ini,pat_fim:ult.pat_fim,
      ano_ini:Math.min(...per.map(a=>a.ano_ini)),ano_fim:Math.max(...per.map(a=>a.ano_fim)),
      exemplar:per.some(a=>a.exemplar),selo:per.some(a=>a.selo),outras_rendas:per.some(a=>a.outras_rendas),processos:procs,
      novo:per.some(a=>a.novo),mencoes:Math.max(0,...per.map(a=>a.mencoes||0)),
      pagina:per.find(a=>REL(a.pagina))?.pagina,cobrar:per.some(a=>a.cobrar),dossie:per.find(a=>REL(a.dossie))?.dossie,
      // contadores do card: empresas (qtd_empresas do pipeline; sem o campo, nomes distintos), projetos do periodo mais recente
      qtd_empresas:qe.length?Math.max(...qe):new Set(per.flatMap(a=>a.empresas||[])).size,sem_qtd:!qe.length,
      projetos:per.map(a=>a.projetos).filter(Boolean).sort((x,y)=>(y.ate||0)-(x.ate||0))[0]||null,
      // presenca e votos (#56, #58): iguais em todos os periodos da pessoa (vem do parlamentar em exercicio)
      presenca:per.map(a=>a.presenca).find(Boolean)||null,votos:per.map(a=>a.votos).find(Boolean)||null,
      // equipe do gabinete (#66): so o numero; sem o dado (antes da carga ou fonte fora do ar) o contador nao aparece
      gabinete:per.map(a=>a.gabinete).find(g=>g&&g.pessoas>0)||null,
      // parlamentar: cargo do TSE ou contagem de projetos da casa em que esta em exercicio (o cargo do TSE pode ser outro)
      presidente:per.some(a=>a.presidente_atual),eleito:per.some(a=>a.eleito_atual),eleito_ano:Math.max(0,...per.map(a=>a.eleito_ano||0))||null,
      // um carimbo por eleicao vencida (pedido do usuario, 24/10); carga antiga: so o ano do mandato em curso; sem ano, nenhum
      eleito_anos:[...new Set(per.flatMap(a=>a.eleito_anos||(a.eleito_ano?[a.eleito_ano]:[])))].sort(),vice:per.some(a=>a.vice_atual),foto:[...per].reverse().map(a=>a.link_foto).find(v=>/^https:\/\//.test(v||"")),
      parlamentar:per.some(a=>a.projetos||/^(DEPUTADO FEDERAL|SENADOR)$/i.test(a.cargo||""))};});
}
// ordem dos destaques: presidente e depois vice em exercicio no topo (#63), depois o maior aumento percentual do patrimonio (pedido do usuario)
const TOPO=p=>p.presidente?2:p.vice?1:0;
const VN=p=>p.pat_ini>0&&p.cresc!=null?p.cresc/p.pat_ini:-Infinity;
// #62: faixas calculadas com a conta antiga (antes da carga) ficam escondidas; aparecem sozinhas quando a carga nova chegar
const FAIXA_NOVA=!!D&&(D.metodo||{}).formula==="vezes";
if(D)for(const a of D.alertas||[])if(!FAIXA_NOVA||!NIVEIS.includes(a.nivel))a.nivel=a.nivel_calculado=null;
const PES=D?agrupaPessoas(D.alertas||[]).sort((x,y)=>TOPO(y)-TOPO(x)||VN(y)-VN(x)):[];
// periodos da pessoa que atendem aos filtros de busca, nivel e dimensao (ign: o grafico ignora o proprio filtro)
function casa(p,ign){
  const q=$("q").value.toLowerCase(),nv=$("nv").value;
  return p.per.filter(a=>(!nv||p.nivel===nv)&&(ign==="partido"||!F.partido||a.partido===F.partido)&&(ign==="uf"||!F.uf||a.uf===F.uf)&&(ign==="uf"||!F.regiao||REG[a.uf]===F.regiao)&&(!F.cargo||a.cargo===F.cargo)
    &&(`${a.nome} ${a.nome_urna??""} ${a.cargo} ${a.uf} ${a.partido}`.toLowerCase().includes(q)));
}
// a pessoa entra no filtro se algum periodo dela atender; as marcacoes valem para a pessoa (uniao dos periodos)
const filtra=ign=>PES.filter(p=>(!F.flag||!!FLAG[F.flag][1](p))&&casa(p,ign).length>0);
// graficos: cada pessoa conta uma vez por barra, com o nivel do periodo de maior crescimento e a soma dos crescimentos daquela barra
function agrupa(rows,dim,max){
  const g={};
  for(const p of rows){const v={};
    for(const a of casa(p,dim)){const k=a[dim]||"Não informado",o=v[k]??={nivel:a.nivel,m:-Infinity,cresc:0};if((a.cresc??-Infinity)>o.m){o.m=a.cresc??-Infinity;o.nivel=a.nivel;}o.cresc+=a.cresc||0;}
    for(const [k,x] of Object.entries(v)){const o=g[k]??={k,n:0,cresc:0,forte:0,atencao:0,informativo:0};o.n++;o[x.nivel]++;o.cresc+=x.cresc;}}
  let l=Object.values(g).sort((x,y)=>y.n-x.n||y.cresc-x.cresc);
  if(max&&l.length>max){const r=l.slice(max),o={k:"Outros",outros:true,n:0,cresc:0,forte:0,atencao:0,informativo:0};
    for(const x of r)for(const c of ["n","cresc",...NIVEIS])o[c]+=x[c];l=[...l.slice(0,max),o];}
  return l;
}
function tip(ev,x){
  const t=$("tip");t.replaceChildren(el("b",null,x.k+(x.outros?"":"")));
  const lin=(rot,val,cls)=>{const d=el("div"),s=el("span");if(cls){const k=el("s");k.style.background=COR(cls);s.append(k);}s.append(rot);d.append(s,el("strong",null,val));t.append(d);};
  lin("Pessoas",x.n.toLocaleString("pt-BR"));for(const n of NIVEIS)if(x[n])lin(NV[n],x[n].toLocaleString("pt-BR"),n);
  t.hidden=false;const r=ev.target.closest(".trilho").getBoundingClientRect(),w=t.offsetWidth;
  t.style.left=Math.max(8,Math.min(innerWidth-w-8,(ev.clientX??r.left+r.width/2)-w/2))+"px";
  t.style.top=(r.top-t.offsetHeight-8<8?r.bottom+8:r.top-t.offsetHeight-8)+"px";
}
function grafico(id,dim,max){
  const l=agrupa(filtra(dim),dim,max),box=$(id),top=Math.max(1,...l.map(x=>x.n));
  box.replaceChildren();box.classList.toggle("filtrado",!!F[dim]||(dim==="uf"&&!!F.regiao));
  // estados agrupados por regiao (a regiao com mais destaques primeiro); o titulo da regiao filtra o painel
  const tot={};if(dim==="uf"){for(const x of l)tot[REG[x.k]||"Não informado"]=(tot[REG[x.k]||"Não informado"]||0)+x.n;
    l.sort((x,y)=>(tot[REG[y.k]||"Não informado"]-tot[REG[x.k]||"Não informado"])||(REG[x.k]||"").localeCompare(REG[y.k]||"")||y.n-x.n);}
  let reg=null;
  for(const x of l){
    if(dim==="uf"&&(REG[x.k]||"Não informado")!==reg){reg=REG[x.k]||"Não informado";const r=reg;
      const b=el("button","reg"+(F.regiao===r?" sel":""),`${r} · ${tot[r].toLocaleString("pt-BR")}`);b.type="button";
      b.title=F.regiao===r?"Remover filtro da região":`Filtrar pela região ${r}`;b.setAttribute("aria-pressed",F.regiao===r);
      b.onclick=()=>{F.regiao=F.regiao===r?"":r;F.uf="";draw();};box.append(b);}
    const tr=el("div","trilho"+(x.outros?" outros":"")+(F[dim]===x.k||(dim==="uf"&&!F.uf&&F.regiao&&REG[x.k]===F.regiao)?" sel":""));
    const trk=el("div","trk"),st=el("div","st");st.style.width=(x.n/top*100)+"%";
    for(const n of NIVEIS)if(x[n]){const s=el("i",n);s.style.flex=x[n]+" 1 0";st.append(s);}
    trk.append(st);tr.append(trk,el("span","tot",x.n));
    tr.setAttribute("aria-label",`${x.k}: ${x.n} ${x.n===1?"pessoa":"pessoas"} (`+NIVEIS.filter(n=>x[n]).map(n=>`${NV[n]} ${x[n]}`).join(", ")+")");
    tr.onpointermove=ev=>tip(ev,x);tr.onpointerleave=()=>$("tip").hidden=true;
    if(!x.outros){tr.tabIndex=0;tr.setAttribute("role","button");tr.setAttribute("aria-pressed",F[dim]===x.k);
      tr.onfocus=ev=>tip(ev,x);tr.onblur=()=>$("tip").hidden=true;
      const tg=()=>{F[dim]=F[dim]===x.k?"":x.k;$("tip").hidden=true;draw();if(F[dim])verDestaques();};
      tr.onclick=tg;tr.onkeydown=ev=>{if(ev.key==="Enter"||ev.key===" "){ev.preventDefault();tg();}};}
    box.append(el("span","rot",x.k),tr);
  }
  if(!l.length)box.append(el("span","rot","—"),el("span","tot","Nenhuma pessoa"));
  return l;
}
function tabela(id,titulo,l){
  const t=el("table"),h=el("tr");for(const c of [titulo,"Pessoas",NV.forte,NV.atencao,NV.informativo])h.append(el("th",c===titulo?null:"n",c));
  const tb=el("tbody");for(const x of l){const r=el("tr");r.append(el("td",null,x.k));for(const c of ["n",...NIVEIS])r.append(el("td","n",x[c].toLocaleString("pt-BR")));tb.append(r);}
  const th=el("thead");th.append(h);t.append(th,tb);$(id).replaceChildren(t);
}
// graficos gerados a parte (so existem com ID_SEGREDO) ficam num <template> e entram na pagina quando a aba abre (#73); sem conteudo, nao aparecem
function graficosGerados(){
  const t=$("graficos-gerados");if(!t)return;const s=t.content.firstElementChild;t.replaceWith(t.content);
  for(const c of s.querySelectorAll(":scope>.card"))if(c.children.length<=1)c.hidden=true;
  s.hidden=![...s.children].some(x=>!x.hidden&&x.tagName!=="H2");
}
function numeros(rows){
  graficosGerados();
  // rows = pessoas; o crescimento de cada pessoa e a soma dos seus periodos
  const n=nv=>rows.filter(p=>p.nivel===nv).length.toLocaleString("pt-BR");
  const k=$("kpis");k.replaceChildren();
  for(const [v,r] of [[rows.length.toLocaleString("pt-BR"),"Pessoas em destaque"],[n("forte"),NV.forte],[n("atencao"),NV.atencao],
    [n("informativo"),NV.informativo]]){
    const d=el("div","kpi");d.append(el("b",null,v),el("span",null,r));k.append(d);}
  tabela("tp","Partido",grafico("gp","partido",0));tabela("tu","UF",grafico("gu","uf",0));
}
function chips(){
  const c=$("chips");c.replaceChildren();
  if(F.flag){const b=el("button",null,`${FLAG[F.flag][0]} ×`);b.title="Remover filtro";b.onclick=()=>{F.flag="";draw();};c.append(b);}
  for(const [dim,rot] of [["cargo","Cargo"],["regiao","Região"],["partido","Partido"],["uf","UF"]])if(F[dim]){const b=el("button",null,`${rot}: ${F[dim]} ×`);b.title="Remover filtro";b.onclick=()=>{F[dim]="";draw();};c.append(b);}
}
for(const id of ["lg1","lg2"])for(const n of NIVEIS){const s=el("span");const i=el("i");i.style.background=COR(n);s.append(i,NV[n]);$(id).append(s);}
// cor de cada partido (aproximada da identidade visual, so como marcador; o texto fica em cor neutra)
const COR_PARTIDO={PT:"#c8102e",PL:"#1f4e9c",PP:"#0b6bb5",MDB:"#1b8a3e",PSDB:"#0057a8",PSD:"#f2a900",UNIÃO:"#123f8c",
  PDT:"#e31e24",PODE:"#2aa84a",AVANTE:"#f07d00",PSB:"#f4c400",REPUBLICANOS:"#00599c",PSC:"#1a9b46",PRTB:"#138a3b",
  NOVO:"#f47920",SOLIDARIEDADE:"#f58220",CIDADANIA:"#e5007e",PATRIOTA:"#00843d",REDE:"#00a19a",PTB:"#1d1d1b",PRD:"#00529b",
  DEMOCRATA:"#0b4ea2",DEM:"#0b4ea2",PV:"#2e9a3a",PSL:"#1b5ea8",PROS:"#f39200",PMB:"#7b2d8b",DC:"#1b6fb5",AGIR:"#e94e1b",
  PSOL:"#f9c300",PCdoB:"#da251d",MOBILIZA:"#0067b1"};
const PD=p=>COR_PARTIDO[p]?`<i class="cor" style="background:${COR_PARTIDO[p]}" aria-hidden="true"></i>`:"";
// processos em que a pessoa e re (lista curada por issue): tag com link para a consulta do primeiro
const PR=a=>{const p=(a.processos||[]).filter(x=>/^https:\/\//.test(x.link||""));
  if(!p.length)return"";
  return`<a class="tag reu" href="${esc(p[0].link)}" target="_blank" rel="noopener" title="${esc(p.map(x=>`${x.tribunal} ${x.numero}`).join("; "))}. ${REU_OBS}.">Responde a processo?${p.length>1?` (${p.length})`:""}</a>`;};
// tags de uma pessoa (cards e tabela): marcacoes + cargos, partidos e UF (uniao dos periodos) em cor neutra; todas filtram
// selo de cera clicavel (filtra pela marcacao): cor, icone e rotulo
// selo de cera: so nas abas proprias (Exemplares, Projetos); na principal a marcacao e uma tag colorida que filtra
const SELO=(cor,title,ic,rot)=>`<span class="selo-cera canto ${cor}" title="${esc(title)}"><span class="cera" aria-hidden="true"><span>${ic}</span></span><span class="sr">${rot}</span></span>`;
const MARCA=(v,title,ic,rot)=>BT(v,`data-f="flag" data-v="${v}"`,title,`${ic} ${rot}`);
const BT=(cls,attrs,title,txt)=>`<button type="button" class="tag ${cls}" ${attrs} title="${esc(title)}">${txt}</button>`;
const DIM=(dim,v,rot,txt)=>BT("",`data-dim="${dim}" data-v="${esc(v)}"`,`Filtrar pelo ${rot} ${v}`,txt);
const CPU=p=>(p.cargos.length?p.cargos.map(c=>DIM("cargo",c,"cargo",esc(c))).join(""):`<span class="tag">Não informado</span>`)
  +p.partidos.map(x=>DIM("partido",x,"partido",PD(x)+esc(x))).join("")+p.ufs.map(u=>DIM("uf",u,"estado",esc(u))).join("");
const TAGS=p=>{const rd=p.per.find(a=>a.nivel_calculado&&a.nivel_calculado!==a.nivel);
  return(p.exemplar?BT("","data-f=\"flag\" data-v=\"exemplar\"","Parlamentar exemplar: patrimônio compatível, cota abaixo da média e sem sanções. Clique para ver só os exemplares",`<span class="estrela">${ICO.estrela}</span> exemplar`):"")
  +(p.selo?BT("selo","data-f=\"flag\" data-v=\"selo\"","Pata na massa: entre os 10% da sua casa (Câmara ou Senado) com mais projetos aprovados nos últimos 4 anos. Clique para ver só quem tem o selo",`${ICO.pata} Pata na massa`):"")
  +PR(p)
  +(p.outras_rendas?BT("renda","data-f=\"flag\" data-v=\"renda\"",`Declarou participação em empresas: tem outra fonte de renda${rd?`; destaque reduzido de ${NV[rd.nivel_calculado]} para ${NV[rd.nivel]}${p.per.length>1?` em ${rd.ano_ini}–${rd.ano_fim}`:""}`:""}. Clique para ver só quem tem empresas`,"Tem empresas declaradas"):"")
  +CPU(p);};
// cards em lotes de PAG pessoas (pagina leve); a tabela completa so e montada quando aberta
const PAG=24;let ROWS=[],VIS=0;
const CR=a=>`<p class="cresc"><small>Aumento do patrimônio</small><b>${VO(a)}</b></p>`;
const DL=a=>`<dl><div class="col"><dt>Entre colegas do mesmo cargo</dt><dd>${COL(a,1)}</dd></div></dl>`;
// um periodo dentro do card (so para quem tem mais de um): anos, cargo (e partido, se mudou), numeros e TSE;
// o chip de nivel so aparece no periodo de maior crescimento (classe maior)
const PER=(a,p)=>`<li class="periodo"><span class="anos">${a.ano_ini}–${a.ano_fim}</span> <span class="cargo">${esc(a.cargo||"Não informado")}${p.partidos.length>1&&a.partido?` · ${esc(a.partido)}`:""}</span>
${CR(a)}${DL(a)}${TSE(a)?`<p class="links">${TSE(a)}</p>`:""}</li>`;
// contadores da pessoa (card e tabela): empresas declaradas, processos da lista revisada e projetos aprovados (so deputado federal e senador)
const CONT=(p,tag="p",cls="contadores")=>{
  const ne=p.qtd_empresas||0,np=p.processos.length,lk=p.processos.find(x=>/^https:\/\//.test(x.link||""))?.link,j=p.projetos,n=v=>Number(v||0).toLocaleString("pt-BR");
  const s=(z,t,txt,c="")=>`<span class="contador${c}${z?" zero":""}"${t?` title="${esc(t)}"`:""}>${txt}</span>`,ic=e=>`<span aria-hidden="true">${e}</span> `;
  const pr=`<b>${n(np)}</b> ${np===1?"processo?":"processos?"}`;
  return`<${tag} class="${cls}">`+(!ne&&p.sem_qtd&&p.outras_rendas?s(0,"",ICO.predio+" "+"Tem empresas declaradas"):s(!ne,"",ICO.predio+" "+(ne?`<b>${n(ne)}</b> ${ne===1?"empresa declarada":"empresas declaradas"}`:"Nenhuma empresa declarada")))+" "
    +(PROC_ON?s(!np,REU_OBS,ICO.balanca+" "+(np?(lk?`<a href="${esc(lk)}" target="_blank" rel="noopener">${pr}</a>`:pr):"Nenhum processo informado")," processos")+" ":"")
    +(p.parlamentar?s(j&&!j.aprovados,j?"Projetos de lei, de lei complementar e PECs como autor ou coautor; aprovados = viraram norma jurídica":"",ICO.pata+" "+(j?`<b>${n(j.aprovados)}</b> ${j.aprovados===1?"projeto aprovado":"projetos aprovados"} de ${n(j.apresentados)} ${j.apresentados===1?"apresentado":"apresentados"}${j.de?` (${j.de}–${j.ate})`:""}${/^https:\/\//.test(j.link||"")?` · <a href="${esc(j.link)}" target="_blank" rel="noopener" aria-label="Ver os projetos no site oficial">ver</a>`:""}`:"Projetos: Não informado")):"")
    +(p.presenca&&p.presenca.pct!=null?" "+s(0,"Presença registrada em sessões do plenário desde o início da legislatura, comparada com a média da casa. Falta pode ter justificativa (licença, missão)",ICO.check+` Presença <b>${PCT(p.presenca.pct)}</b>${p.presenca.media_casa!=null?` (média da casa ${PCT(p.presenca.media_casa)})`:""}`," presenca"):"")
    +(p.gabinete?" "+s(0,"Pessoas que trabalham hoje no gabinete, pagas com dinheiro público, segundo a fonte oficial",ICO.equipe+` <b>${n(p.gabinete.pessoas)}</b> ${p.gabinete.pessoas===1?"pessoa":"pessoas"} no gabinete${/^https:\/\//.test(p.gabinete.link||"")?` · <a href="${esc(p.gabinete.link)}" target="_blank" rel="noopener" aria-label="Ver a equipe no site oficial">ver</a>`:""}`," gabinete"):"")
    +(p.votos&&p.votos.length?" "+s(0,"Votações de temas importantes no plenário. Veja como votou em cada um no Raio-X",ICO.urna+` Votou em <b>${p.votos.filter(v=>v.voto!=="Não votou").length}</b> de ${p.votos.length} temas${/^dossie\//.test(p.dossie||"")?` · <a href="${esc(p.dossie)}#votos">ver votos</a>`:""}`," votos"):"")
    +`</${tag}>`;};
// nome e cargo do TSE em caixa alta viram "Zé da Silva", "Deputado Estadual" (conectivos ficam minusculos)
const MIN=new Set(["de","da","do","das","dos","e"]);
const CAP=c=>String(c).toLowerCase().replace(/\p{L}+/gu,w=>MIN.has(w)?w:w[0].toUpperCase()+w.slice(1));
// filtro discreto no resumo do card: texto clicavel com o mesmo data-dim das tags (porTag)
const FIL=(dim,v,rot,txt)=>`<button type="button" class="tag fil" data-dim="${dim}" data-v="${esc(v)}" title="Filtrar pelo ${rot} ${esc(v)}">${txt}</button>`;
const SEP=' <span class="sep" aria-hidden="true">·</span> ';
// uma linha: cargo · partido · UF · anos (mudancas entre periodos com seta)
const CPU_RES=p=>[p.cargos.length?p.cargos.map(c=>FIL("cargo",c,"cargo",esc(CAP(c)))).join(" → "):"Não informado",
  p.partidos.map(x=>FIL("partido",x,"partido",PD(x)+esc(x))).join(" → "),p.ufs.map(u=>FIL("uf",u,"estado",esc(u))).join(" → ")].filter(Boolean).join(SEP);
// listas de cota e projetos: um registro por pessoa, mesmo resumo neutro dos cards
const RES1=c=>`<p class="resumo">${CPU_RES({cargos:[c.cargo].filter(Boolean),partidos:[c.partido].filter(Boolean),ufs:[c.uf].filter(Boolean)})}</p>`;
// marcacoes que valem a pena na face do card; zeros e "Não informado" ficam nos detalhes
const MARCAS=p=>{const ne=p.qtd_empresas||0,rd=p.per.find(a=>a.nivel_calculado&&a.nivel_calculado!==a.nivel);
  const l=[p.exemplar&&MARCA("exemplar","Parlamentar exemplar: patrimônio compatível, cota abaixo da média e sem sanções. Clique para ver só os exemplares",ICO.estrela,"Exemplar"),
    p.selo&&MARCA("selo","Pata na massa: entre os 10% da sua casa (Câmara ou Senado) com mais projetos aprovados nos últimos 4 anos. Clique para ver só quem tem o selo",ICO.pata,"Pata na massa"),
    PROC_ON&&PR(p),
    (ne||p.outras_rendas)&&BT("renda","data-f=\"flag\" data-v=\"renda\"",`Declarou participação em empresas: tem outra fonte de renda${rd?`; destaque reduzido de ${NV[rd.nivel_calculado]} para ${NV[rd.nivel]}${p.per.length>1?` em ${rd.ano_ini}–${rd.ano_fim}`:""}`:""}. Clique para ver só quem tem empresas`,
      `${ICO.predio} ${ne?`${ne.toLocaleString("pt-BR")} ${ne===1?"empresa":"empresas"}`:"Tem empresas"}`)].filter(Boolean);
  return l.length?`<p class="tags">${l.join("")}</p>`:"";};
// analogia principal: quantas vezes o que daria para guardar com o salario (soma dos periodos; sem salario de referencia, nao aparece)
// face do card (#62): so o percentual de aumento do patrimonio declarado; os valores em reais ficam em Detalhes
// a conta das faixas (#62): aumento do patrimonio dividido pelo valor original (o salario nao entra); sem reais na tela
// aumento percentual sobre o valor original (#62): (fim - comeco) / comeco x 100
const AUMP=x=>x<0?`diminuiu ${NUM(Math.round(-x*100),0)}%`:`+${NUM(Math.round(x*100),0)}%`;
const VO=p=>p.cresc==null||p.pat_ini==null?"Não informado":p.pat_ini>0?AUMP(p.cresc/p.pat_ini):p.cresc>0?"começou do zero":"Não informado";
const AUM=p=>`<b>${VO(p)}</b>`;
// fatos do card: mesma fonte e um icone por linha; linha sem dado nao aparece
const FATOS=p=>{const ic=(e,t)=>t?`<li><span class="ic" aria-hidden="true">${e}</span><span>${t}</span></li>`:"";
  return`<ul class="fatos">${ic(ICO.carrinho,COMPRA(p.cresc))}${ic(ICO.regua,p.maior.percentil==null?"":`Comparado com os colegas ${COL(p.maior)}`)}</ul>`;};
// detalhes sob demanda: contadores completos, numeros do calculo e periodos
const DET=p=>{const m=p.per.length>1;
  return`<div class="det" hidden>${CONT(p)}
${m?`<p class="mut">Maior crescimento: <b class="maior-ano">${p.maior.ano_ini}–${p.maior.ano_fim}</b></p><ul class="periodos">${p.per.map(a=>PER(a,p)).join("")}</ul>`:CR(p.per[0])+DL(p.per[0])}</div>`;};
const ROT_VER="Detalhes";
// abre e fecha os detalhes do card (clique delegado no documento)
function verDet(ev){const b=ev.target.closest("button.ver");if(!b)return false;
  const d=b.closest("li").querySelector(".det"),abre=d.hidden;d.hidden=!abre;b.setAttribute("aria-expanded",abre);
  b.firstChild.textContent=abre?"Fechar":b.dataset.rot;return true;}
// faixa do presidente em exercicio (#63): cargo e resultado do TSE, foto oficial sobre as iniciais
const INI=n=>String(n).split(/\s+/).filter(w=>w&&!MIN.has(w.toLowerCase())).slice(0,2).map(w=>w[0]).join("").toUpperCase();
const PRES=p=>`<div class="faixa-pres"><span class="avatar g" aria-hidden="true">${esc(INI(p.nome_urna||p.nome))}${p.foto?`<img src="${esc(p.foto)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`:""}</span><span class="rot">${ICO.faixa} ${p.presidente?"Presidente":"Vice-presidente"} da República em exercício</span></div>`;
const MULTI=p=>p.per.length>1?` <span class="multi">${p.per.length} períodos</span>`:"";
const ELEITO="Eleito: o TSE registra que venceu a eleição e o mandato está em curso. Pode ser cobrado no cargo";
// carimbo Eleito (#67): o ano da eleicao vai dentro do selo, sem texto ao lado (o significado fica na legenda);
// sem o ano (carga antiga), o selo mostra o check. Um carimbo por eleicao vencida, lado a lado no canto
const CARIMBO_ELEITO=ano=>`<span class="selo-cera verde${ano?" com-ano":""}" title="${esc(ELEITO+(ano?`. Eleição de ${ano}`:""))}"><span class="cera" aria-hidden="true"><span>${ano?`<b class="ano">${ano}</b>`:ICO.check}</span></span><span class="sr">Eleito${ano?` em ${ano}`:""}</span></span>`;
const CARIMBOS=anos=>anos.length?`<span class="carimbos canto">${anos.map(CARIMBO_ELEITO).join("")}</span>`:"";
const CARD=p=>`<li class="card alerta${p.exemplar?" exemplar":""}${p.presidente?" presidente":p.vice?" vice":""}${p.eleito?" eleito":""}${p.eleito_anos.length?" com-selo":""}">${CARIMBOS(p.eleito_anos)}${TOPO(p)?PRES(p):""}<div class="topo"><b class="nome">${p.exemplar?`<span class="estrela" title="Parlamentar exemplar: patrimônio compatível, cota abaixo da média e sem sanções">${ICO.estrela}</span> `:""}${esc(CAP(p.nome_urna||p.nome))}${p.novo?' <span class="novo">novo</span>':""}</b>${NV[p.nivel]?`<span class="chip nv-${p.nivel}" role="img" aria-label="${NV[p.nivel]}: o patrimônio aumentou ${VO(p.maior)}" title="${NV[p.nivel]}${p.per.length>1?` no período de maior crescimento (${p.maior.ano_ini}–${p.maior.ano_fim})`:""}. Veja a fórmula em Como ler os números">${NV[p.nivel]}</span>`:""}</div>
<p class="resumo">${CPU_RES(p)}</p>
<p class="valor">${AUM(p)}<span>${p.cresc<0?"no patrimônio":"de aumento no patrimônio"} de ${p.ano_ini} a ${p.ano_fim}</span></p>
${FATOS(p)}${MARCAS(p)}${DET(p)}
<div class="pe"><p class="links">${LK(p)}</p><button type="button" class="ver" aria-expanded="false" data-rot="${ROT_VER}"${p.per.length>1?` title="Números do cálculo e os ${p.per.length} períodos"`:""}>${ROT_VER}<span aria-hidden="true"> ▾</span></button></div></li>`;
// parlamentares exemplares: um card por pessoa (nome + UF), periodos agrupados
function exemplares(){
  const m=new Map();for(const x of D.exemplares||[]){const k=`${x.nome}|${x.uf}`;if(!m.has(k))m.set(k,[]);m.get(k).push(x);}
  if(!Array.isArray(D.exemplares))return;  // sem a lista de parlamentares nesta execucao: secao escondida
  const l=[...m.values()];
  if(!l.length){$("exemplares-qtd").textContent="Nenhum parlamentar em exercício cumpre os três critérios nesta atualização.";$("exemplares").hidden=false;return;}
  const RS=R;
  const u=(g,c)=>[...new Set(g.map(x=>x[c]).filter(Boolean))];
  $("exemplares-qtd").textContent=l.length===1?"1 parlamentar cumpre os três critérios nesta atualização.":`${l.length.toLocaleString("pt-BR")} parlamentares cumprem os três critérios nesta atualização.`;
  $("exemplares-lista").innerHTML=l.map(g=>{const x=g[0],lk=g.find(y=>/^https:\/\//.test(y.link||""))?.link,mul=g.length>1;
    const p={cargos:u(g,"cargo"),partidos:u(g,"partido"),ufs:u(g,"uf")};
    return`<li class="card alerta exemplar com-selo">${SELO("ouro","Parlamentar exemplar: patrimônio compatível, cota abaixo da média e sem sanções",ICO.estrela,"Exemplar")}<div class="topo"><span><b>${esc(x.nome)}</b>${mul?` <span class="multi">${g.length} períodos</span>`:""}<br><small>Patrimônio de ${Math.min(...g.map(y=>y.ano_ini))}–${Math.max(...g.map(y=>y.ano_fim))}</small></span></div>
<p class="resumo">${CPU_RES(p)}</p>
<dl><div><dt>Cota parlamentar (últimos 4 anos)</dt><dd>${RS(x.cota)}</dd></div><div><dt>Média do cargo</dt><dd>${RS(x.cota_media)}</dd></div>${g.map(y=>`<div><dt>Crescimento do patrimônio (${y.ano_ini}–${y.ano_fim})</dt><dd>${R(y.cresc)}</dd></div><div><dt>Poderia juntar com o salário${mul?` (${y.ano_ini}–${y.ano_fim})`:""}</dt><dd>${R(y.cap)}</dd></div>`).join("")}</dl>
<p class="links">${lk?`<a class="lk" href="${esc(lk)}" target="_blank" rel="noopener">Site oficial</a>`:"Site oficial: Não informado"}</p></li>`;}).join("");
  $("exemplares").hidden=false;
}
function cota(){
  const l=D.cota||[];if(!l.length)return;
  const RS=v=>"R$ "+v.toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2});
  $("cota-lista").innerHTML=l.map((c,i)=>`<li class="card alerta"><div class="topo"><span><b>${i+1}. ${esc(c.nome)}</b><br><small>${c.de}–${c.ate}</small></span></div>
${RES1(c)}
<p class="cresc"><small>Total gasto da cota</small><b>${RS(c.total)}</b></p>
<dl>${(c.tipos||[]).map(t=>`<div><dt>${esc(t.tipo||"Outros")}</dt><dd>${RS(t.valor)}</dd></div>`).join("")}</dl>
<p class="links">${/^https:\/\//.test(c.link||"")?`<a class="lk" href="${esc(c.link)}" target="_blank" rel="noopener">Site oficial</a>`:""}${REL(c.dossie)?` · <a class="lk" href="${esc(c.dossie)}">Raio-X</a>`:""}</p></li>`).join("");
  $("cota").hidden=false;
}
function projetos(){
  const l=D.projetos||[];if(!l.length)return;
  $("projetos-lista").innerHTML=l.map((c,i)=>`<li class="card alerta${c.selo?" com-selo":""}">${c.selo?SELO("caramelo","Pata na massa: entre os 10% da sua casa com mais projetos aprovados",ICO.pata,"Pata na massa"):""}<div class="topo"><span><b>${i+1}. ${esc(c.nome)}</b><br><small>${c.de}–${c.ate}</small></span></div>
${RES1(c)}
<dl><div><dt>Projetos apresentados</dt><dd>${c.apresentados.toLocaleString("pt-BR")}</dd></div><div><dt>Aprovados (viraram norma jurídica)</dt><dd>${c.aprovados.toLocaleString("pt-BR")}</dd></div></dl>
<p class="links">${/^https:\/\//.test(c.link||"")?`<a class="lk" href="${esc(c.link)}" target="_blank" rel="noopener">Ver a lista no site oficial</a>`:""}${REL(c.dossie)?` · <a class="lk" href="${esc(c.dossie)}">Raio-X</a>`:""}</p></li>`).join("");
  $("projetos").hidden=false;
}
function mais(){
  const ate=Math.min(ROWS.length,VIS+PAG);$("cards").insertAdjacentHTML("beforeend",ROWS.slice(VIS,ate).map(CARD).join(""));VIS=ate;
  const r=ROWS.length-VIS;$("mais").hidden=r<=0;$("mais").textContent=`Mostrar mais ${Math.min(r,PAG)} (faltam ${r.toLocaleString("pt-BR")})`;
}
function tabelaToda(){
  if(!$("tabela").open)return;
  // uma linha por pessoa; com varios periodos, cada celula traz uma linha por periodo, na mesma ordem da coluna Periodo
  const L=(p,f)=>p.per.map(f).join("<br>");
  document.getElementById("tb").innerHTML=ROWS.map(p=>`<tr><td data-label="Nome"><span>${p.exemplar?`<span class="estrela" title="Parlamentar exemplar">${ICO.estrela}</span> `:""}${esc(p.nome)}${p.novo?' <span class="novo">novo</span>':""}${MULTI(p)}<br><small>${LK(p)}</small></span></td><td data-label="Tags"><span class="tags">${TAGS(p)}</span>${CONT(p,"span","contadores compacto")}</td><td data-label="Período"><span>${L(p,a=>`${a.ano_ini}–${a.ano_fim}${p.per.length>1?` <small>${esc(a.cargo||"Não informado")}${TSE(a)?` · ${TSE(a)}`:""}</small>`:""}`)}</span></td><td class="n" data-label="Aumento do patrimônio"><span>${p.per.length>1?`<b>${VO(p)}</b><br><small>${L(p,a=>`${a.ano_ini}–${a.ano_fim}: ${VO(a)}`)}</small>`:VO(p)}</span></td><td class="n" data-label="Entre colegas do mesmo cargo"><span>${L(p,a=>COL(a,1))}</span></td><td class="nivel ${p.nivel||""}" data-label="Faixa"><span>${NV[p.nivel]||"Sem faixa"}${p.per.length>1?`<br><small>maior crescimento: ${p.maior.ano_ini}–${p.maior.ano_fim}</small>`:""}</span></td></tr>`).join("");
}
// lista completa leve (#43): docs/todos.json so e baixado quando o leitor abre a lista
// pessoa: [nome publico, nome civil, pagina do dossie, marcas ("e" exemplar, "s" selo), periodos]
// periodo: [ano_ini, ano_fim, cargo, partido, uf, patrimonio no inicio, no fim, nivel (0 a 3), link do TSE sem o prefixo]
const TN=["Sem destaque",NV.informativo,NV.atencao,NV.forte],TNC=["","informativo","atencao","forte"],TPAG=40,TSEL=["tcg","tpt","tuf","tnv","tmc"];
let TD=null,TL=[],TV=0,TPEND="",TCARR=false;
const SA=s=>String(s||"").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"");
function todosAbrir(abrir){
  const box=$("todos-box"),ab=abrir??box.hidden;
  box.hidden=!ab;$("todos-abrir").setAttribute("aria-expanded",ab);$("todos-abrir").textContent=ab?"Fechar a lista completa":"Abrir a lista completa";
  if(ab&&!TD&&!TCARR)todosCarregar();
}
async function todosCarregar(){
  TCARR=true;$("todos-qtd").textContent="Carregando a lista...";
  try{const r=await fetch("todos.json",{cache:"no-cache"});if(!r.ok)throw new Error(r.status);TD=await r.json();if(!Array.isArray(TD.lista))throw new Error("formato");}
  catch(e){TD=null;TCARR=false;$("todos-qtd").innerHTML="<b>Fonte não encontrada</b>: não deu para carregar a lista agora. Feche e abra a lista de novo para tentar outra vez.";return;}
  TD.P=TD.lista.map(([n,c,pg,m,per])=>({n,c,pg,m:m||"",per,nv:Math.max(0,...per.map(x=>FAIXA_NOVA&&x[7]<TN.length?x[7]||0:0)),  // conta antiga: sem faixa ate a proxima carga

    cg:new Set(per.map(x=>TD.cargos[x[2]])),pt:new Set(per.map(x=>TD.partidos[x[3]])),uf:new Set(per.map(x=>x[4]||"Não informado")),q:SA(`${n} ${c}`)}));
  const opc=(id,k)=>$(id).append(...[...new Set(TD.P.flatMap(p=>[...p[k]]))].sort((x,y)=>x.localeCompare(y,"pt-BR")).map(v=>{const o=el("option",null,v);o.value=v;return o;}));
  opc("tcg","cg");opc("tpt","pt");opc("tuf","uf");
  if(TPEND){$("tmc").value=TPEND;TPEND="";}
  let t;$("tq").oninput=()=>{clearTimeout(t);t=setTimeout(todosDraw,180);};
  for(const id of TSEL)$(id).onchange=todosDraw;$("todos-mais").onclick=todosMais;
  todosDraw();
}
const TK={tcg:"cg",tpt:"pt",tuf:"uf"};
// a pessoa entra se algum periodo tiver o cargo, partido ou estado; o nivel e o maior dos periodos (ign: ignora um filtro)
// filtros = [[id do select, valor escolhido]], lidos uma vez por desenho (#73): ler o DOM pessoa a pessoa travava o celular
function tPassa(p,filtros,ign,q){
  for(const [id,v] of filtros){if(id===ign)continue;
    if(TK[id]?!p[TK[id]].has(v):id==="tnv"?p.nv!==+v:!p.m.includes(v))return false;}
  return!q||p.q.includes(q);
}
function todosDraw(){
  const q=SA($("tq").value.trim()),filtros=TSEL.map(id=>[id,$(id).value]).filter(([,v])=>v);TL=TD.P.filter(p=>tPassa(p,filtros,null,q));
  // opcoes sem ninguem (com os outros filtros) ficam desativadas; sem nenhuma opcao, o filtro todo fica desativado
  for(const id of TSEL){const s=$(id),tem=new Set();
    for(const p of TD.P)if(tPassa(p,filtros,id,q)){if(TK[id])for(const v of p[TK[id]])tem.add(v);else if(id==="tnv")tem.add(String(p.nv));else for(const c of p.m)tem.add(c);}
    for(const o of s.options)if(o.value)o.disabled=!tem.has(o.value)&&o.value!==s.value;
    s.disabled=!s.value&&![...s.options].some(o=>o.value&&!o.disabled);}
  const n=TL.length,tot=TD.P.length;
  $("todos-qtd").innerHTML=`Mostrando <b>${n.toLocaleString("pt-BR")}</b> de ${tot.toLocaleString("pt-BR")} ${tot===1?"pessoa":"pessoas"}`+(n?"":". Ninguém com este filtro.");
  TV=0;$("todos-lista").replaceChildren();todosMais();
}
const TLK=s=>/^https:\/\//.test(TD.link_tse||"")&&/^[A-Z]+\/[A-Z]{2}\/\d+\/\d+\/\d{4}\/\w+$/.test(s||"")?TD.link_tse+s:"";
// lista completa: so o aumento percentual (#62: sem valores em reais do patrimonio)
const VAR=(ini,fim)=>ini==null||fim==null?"Não informado":VO({cresc:fim-ini,pat_ini:ini});
const LEVE=p=>`<li class="leve"><div class="topo"><span><b>${p.m.includes("e")?`<span class="estrela" title="Parlamentar exemplar: patrimônio compatível, cota abaixo da média e sem sanções">${ICO.estrela}</span> `:""}${esc(p.n)}</b>${p.per.length>1?` <span class="multi">${p.per.length} períodos</span>`:""}${p.c?`<br><small>${esc(p.c)}</small>`:""}</span><span class="chip${p.nv?` nv-${TNC[p.nv]}`:""}">${TN[p.nv]}</span></div>
<p class="tags">${p.m.includes("s")?`<span class="tag selo" title="Entre os 10% da sua casa com mais projetos aprovados nos últimos 4 anos">${ICO.pata} Pata na massa</span>`:""}${[...p.cg,...p.pt,...p.uf].map(v=>`<span class="tag">${esc(v)}</span>`).join("")}</p>
<ul>${p.per.map(x=>{const l=TLK(x[8]);return`<li>${x[0]}–${x[1]}${p.per.length>1?` · ${esc(TD.cargos[x[2]])}`:""}: o patrimônio aumentou ${VAR(x[5],x[6])}${l?` · <a href="${esc(l)}" target="_blank" rel="noopener" title="Declaração no DivulgaCandContas (TSE), ${x[0]}–${x[1]}">TSE</a>`:" · TSE: Não informado"}</li>`;}).join("")}</ul>
${REL(p.pg)?`<p class="links"><a class="lk" href="${esc(p.pg)}">Raio-X</a></p>`:""}</li>`;
function todosMais(){
  const ate=Math.min(TL.length,TV+TPAG);$("todos-lista").insertAdjacentHTML("beforeend",TL.slice(TV,ate).map(LEVE).join(""));TV=ate;
  const r=TL.length-TV;$("todos-mais").hidden=r<=0;$("todos-mais").textContent=`Mostrar mais ${Math.min(r,TPAG)} (faltam ${r.toLocaleString("pt-BR")})`;
}
// abre a lista completa ja filtrada por uma marcacao (legenda, quando ninguem entre os destaques a tem)
function todosCom(m){
  if(TD){$("tmc").value=m;todosDraw();}else TPEND=m;
  if(ABA)abrirAba("todos");todosAbrir(true);$("todos").scrollIntoView({behavior:"smooth",block:"start"});
}
function todos(){
  const t=D.todos;if(!t||!t.pessoas)return;
  $("todos-abrir").textContent="Abrir a lista completa";$("todos-abrir").onclick=()=>todosAbrir();
  $("todos").querySelector(".fonte").append(` São ${t.pessoas.toLocaleString("pt-BR")} pessoas (${t.comparacoes.toLocaleString("pt-BR")} comparações); a lista é baixada só quando aberta (cerca de ${t.kb>=1024?`${(Math.round(t.kb/102.4)/10).toLocaleString("pt-BR")} MB`:`${Math.max(1,t.kb).toLocaleString("pt-BR")} KB`} sem compressão).`);
  $("todos").hidden=false;
}
function draw(){
  const rows=filtra();chips();
  $("cg").value=F.cargo;$("rg").value=F.regiao;const nf=[F.cargo,F.regiao,$("nv").value].filter(Boolean).length;$("filtros-bt").textContent=nf?`Filtros (${nf})`:"Filtros";for(const b of $("legenda").querySelectorAll("button"))b.setAttribute("aria-pressed",F[b.dataset.f]===b.dataset.v);ROWS=rows;VIS=0;$("cards").replaceChildren();mais();tabelaToda();
  if(ABA==="numeros")numeros(rows);else DESENHADAS.delete("numeros");  // fora da aba, redesenha quando ela abrir
  const fl=[F.flag&&FLAG[F.flag][0].toLowerCase(),F.cargo&&`cargo ${F.cargo}`,F.regiao&&`região ${F.regiao}`,F.partido&&`partido ${F.partido}`,F.uf&&`estado ${F.uf}`].filter(Boolean);
  $("contagem").innerHTML=`Mostrando <b>${rows.length.toLocaleString("pt-BR")}</b> de ${PES.length.toLocaleString("pt-BR")} ${PES.length===1?"pessoa":"pessoas"}`+(fl.length?` · filtro: ${esc(fl.join(" e "))} <button type="button" id="limpar">Limpar filtro</button>`:"");
  if(fl.length)$("limpar").onclick=()=>{F.partido=F.uf=F.cargo=F.regiao=F.flag="";$("cg").value="";$("rg").value="";draw();};
  document.getElementById("vz").hidden=rows.length>0;
}
// percentil no grupo de pares: 100 = o maior crescimento do grupo
const PC=p=>p==null?"Não informado":p>=99.5?"o maior<br><small>do grupo</small>":`acima de ${Math.round(p)}%<br><small>dos colegas</small>`;
// regua dos colegas (#64): em qual das 5 partes iguais de colegas a pessoa esta, sem valor exato; ponto dourado acima de P_ALTO
const P_ALTO=90,PARTE=["a dos que menos cresceram","a segunda","a do meio","a quarta","a dos que mais cresceram"];
const GRUPO=a=>{const n=Number(a.n_pares||0).toLocaleString("pt-BR");
  // grupo = cargo disputado no inicio do periodo (o do mandato); se a pessoa trocou de cargo depois, a legenda diz isso
  return!a.n_pares?"":a.cargo_pares?(CAP(a.cargo_pares)===CAP(a.cargo||a.cargo_pares)?`Entre ${n} candidatos a ${esc(CAP(a.cargo_pares))} em ${a.ano_ini}`
    :`Entre ${n} que disputaram ${esc(CAP(a.cargo_pares))} em ${a.ano_ini}, como esta pessoa (depois ela disputou ${esc(CAP(a.cargo))})`):`Entre ${n} pessoas de todos os cargos em ${a.ano_ini} (poucos colegas de cargo)`;};
const RG=a=>{if(a.percentil==null)return"";const q=Math.min(4,Math.floor(a.percentil/20)),alto=a.percentil>=P_ALTO;
  return`<span class="regua${alto?" alto":""}" role="img" aria-label="Posição do crescimento entre os colegas: parte ${q+1} de 5, ${PARTE[q]}${alto?`; cresceu mais que ${P_ALTO} de cada 100`:""}" title="Régua dos colegas: veja a fórmula em Como ler os números">${"<i></i>".repeat(5)}<b style="left:${q*20+10}%"></b></span>`;};
// regua com a legenda do grupo; com o valor (detalhes e tabela) o leitor confere a faixa
const COL=(a,valor)=>a.percentil==null?"Não informado":`<span class="colegas"><span class="regua-linha"><small aria-hidden="true">menos</small>${RG(a)}<small aria-hidden="true">mais</small></span>${valor?` ${PC(a.percentil).replace(/<br><small>(.*)<\/small>/," $1")}`:""}<small>${GRUPO(a)}</small></span>`;
// regras dos niveis (o pipeline manda as atuais em D.metodo)
const metodo=()=>Object.assign({taxa:.3,minimo:100000,forte:{razao:3,percentil:95},atencao:{razao:2,percentil:90},informativo:{percentil:95},min_pares:20},D.metodo||{});
function leitura(){
  const m=metodo();
  $("leitura").innerHTML=`
<p><b>A conta</b>: quanto o patrimônio aumentou, em percentual sobre o valor do começo. <code>aumento = (patrimônio do fim − patrimônio do começo) ÷ patrimônio do começo × 100</code>. Exemplo: tinha R$ 1 milhão em 2018 e declarou R$ 3 milhões em 2022. Aumentou R$ 2 milhões, ou seja, <b>+200%</b>. O salário não entra na conta.</p>
<p><b>Entre colegas do mesmo cargo</b> (régua dos colegas): põe em fila, do menor ao maior, o crescimento em reais de todos os candidatos ao mesmo cargo na mesma eleição (o cargo disputado no início do período, mesmo que depois a pessoa tenha disputado outro) que declararam bens de novo na eleição seguinte, e corta a fila em 5 partes iguais. O ponto ${RG({percentil:60})} mostra em qual parte a pessoa está; fica dourado ${RG({percentil:96})} quando ela cresceu mais que ${P_ALTO} de cada 100 colegas. Nos detalhes aparece o valor: "acima de 97% dos colegas" quer dizer que, de cada 100 colegas, 97 tiveram crescimento menor. Se o cargo tiver menos de ${m.min_pares} pessoas, a comparação é com todos os cargos do período, e a régua avisa. O crescimento é em reais, sem correção pela inflação.</p>
<p><b>Faixas de cor</b>: a cor é só o resultado da fórmula, não um julgamento. Só valem para quem aumentou pelo menos ${R(m.minimo)}:</p>
<ul><li><span class="nivel forte">${NV.forte}</span>: aumentou ${PCT(m.forte.razao*100)} ou mais <i>e</i> mais que ${NUM(m.forte.percentil)} de cada 100 colegas.</li>
<li><span class="nivel atencao">${NV.atencao}</span>: aumentou ${PCT(m.atencao.razao*100)} ou mais <i>e</i> mais que ${NUM(m.atencao.percentil)} de cada 100 colegas, ou mais que 98 de cada 100 colegas.</li>
<li><span class="nivel informativo">${NV.informativo}</span>: aumentou mais que ${NUM(m.informativo.percentil)} de cada 100 colegas.</li></ul>
<p><b>Ordem</b>: primeiro o presidente e o vice em exercício; depois, quem teve o maior aumento percentual do patrimônio.</p>
<p><b>Carimbo verde "Eleito"</b>: o <a href="https://divulgacandcontas.tse.jus.br/" target="_blank" rel="noopener">TSE</a> registra que a pessoa venceu a eleição daquele ano (o ano fica dentro do carimbo; quem venceu duas eleições analisadas, por exemplo 2018 e 2022, tem dois carimbos). Só contam eleições com posse já ocorrida (1º de janeiro do ano seguinte). <b>Borda verde</b>: o mandato está em curso hoje (dura 4 anos, ou 8 para senador); presidente, vice e exemplares mantêm a borda deles. Quem só foi candidato não tem carimbo.</p>
${PROC_ON?`<p><b>"Responde a processo?"</b>: o nome da pessoa aparece como réu em processo público de uma lista informada e revisada por leitores antes de entrar no site (tribunal, número e link da consulta). A lista casa pelo nome e pelo estado, então <b>pode ser homônimo: confira o processo</b> antes de qualquer conclusão. Para procurar outros processos pelo nome, use o link "Conferir processos" de cada card. Ser réu não significa condenação.</p>`:""}
<p><b>Uma pessoa, um card</b>: quem tem mais de um período analisado aparece uma vez só; os períodos (cargo, anos e números de cada um) ficam em "Ver detalhes". Quando a pessoa tem mais de um período, o card soma o crescimento de todos (por exemplo, de 2018 a 2026) e o alerta aponta o período em que ela mais cresceu; "Daria para comprar" usa a soma e as tags juntam todos os períodos. Filtros, gráficos e contagens contam pessoas: uma pessoa entra no filtro se algum período dela atender.</p>
<p><b>"Tem empresas declaradas"</b>: a pessoa declarou ao TSE participação em empresas (quotas, ações, capital social) no início ou no fim do período. Como há outra fonte de renda declarada, o destaque desce um grau (de "${NV.forte}" para "${NV.atencao}" e de "${NV.atencao}" para "${NV.informativo}").</p>
<p>Herança, venda de bens, atividade própria e renda do cônjuge não entram na conta, por isso cada destaque é um ponto de partida para pesquisar, não uma conclusão.</p>`+(BENS&&BENS.bens&&BENS.bens.length?`
<p><b>"Daria para comprar"</b>: o crescimento comparado ao bem mais caro desta lista que ele pagaria pelo menos uma vez. Preços de referência de ${esc(BENS.atualizado_em||"")}; podem mudar.</p>
<ul>${BENS.bens.map(b=>`<li>${esc(b.singular)}: ${R(b.preco)} (${esc(b.referencia)})${/^https:\/\//.test(b.link||"")?` · <a href="${esc(b.link)}" target="_blank" rel="noopener">${esc(b.rotulo_link||"ver")}</a>`:""}</li>`).join("")}</ul>`:"");
}
function contrib(){
  // repositorio: informado pelo pipeline no Actions ou deduzido do endereco usuario.github.io/repo
  let repo=D.repo;const h=location.hostname.match(/^([\w-]+)\.github\.io$/i),p=location.pathname.split("/").filter(Boolean)[0];
  if(!repo&&h&&p)repo=`${h[1]}/${p}`;
  if(!repo||!/^[\w.-]+\/[\w.-]+$/.test(repo))return;
  const base=`https://github.com/${repo}/issues`;
  $("sug-noticia").href=`${base}/new?template=fonte-noticias.yml`;$("sug-dados").href=`${base}/new?template=fonte-dados.yml`;
  $("sug-lista").href=`${base}?q=is%3Aissue+in%3Atitle+%22Fonte+de%22`;
  const fs=D.fontes||[];
  $("fontes-uso").textContent="Notícias do Raio-X: Google Notícias"+(fs.length?` e ${fs.length} fonte${fs.length>1?"s":""} sugerida${fs.length>1?"s":""} (${fs.map(f=>f.nome+(f.uf?` – ${f.uf}`:"")).join(", ")})`:"")+".";
  $("contrib").hidden=false;
}
// legenda: cada marcacao mostra quantas pessoas do painel a tem; sem ninguem, o botao fica desativado e explica
function legenda(){
  const m=metodo();
  $("leg-niveis").hidden=!FAIXA_NOVA;  // #62: sem faixas da conta nova, a legenda delas some
  $("leg-niveis").innerHTML=[["forte",`O patrimônio aumentou ${PCT(m.forte.razao*100)} ou mais, e mais que ${NUM(m.forte.percentil)} de cada 100 colegas.`],
    ["atencao",`O patrimônio aumentou ${PCT(m.atencao.razao*100)} ou mais, ou bem mais que os colegas do mesmo cargo.`],
    ["informativo",`Cresceu mais que ${NUM(m.informativo.percentil)} de cada 100 colegas do mesmo cargo.`]]
    .map(([n,t])=>`<li><span class="chip nv-${n}">${NV[n]}</span> <span class="expl">${t}</span></li>`).join("");
  const tt={eleito:"Clique para ver só quem já venceu eleição",exemplar:"Clique para ver só os parlamentares exemplares",selo:"Clique para ver só quem tem o selo Pata na massa",renda:"Clique para ver só quem tem empresas declaradas",reu:`${REU_OBS}. Clique para ver só quem está na lista`};
  for(const b of $("legenda").querySelectorAll('button[data-f="flag"]')){const f=FLAG[b.dataset.v];if(!f)continue;
    const n=PES.filter(f[1]).length,nt=(D.todos||{})[b.dataset.v]||0;  // nt: na lista completa (exemplar e selo)
    if(n||nt)b.removeAttribute("aria-disabled");else b.setAttribute("aria-disabled","true");
    if(!n&&nt)b.dataset.todos="1";else delete b.dataset.todos;
    b.title=n?tt[b.dataset.v]:nt?`${f[2]}. Clique para ver na lista completa`:f[2];
    const td=b.closest("li")?.querySelector(".expl");if(!n&&td)td.append(" ",el("small",null,nt?"(nenhum entre os destaques; veja na lista completa)":"(ninguém nesta atualização)"));}
}
// indicadores do IBGE na aba Estados (#68): Brasil ao lado da bandeira com valor e seta; nos cards dos estados so os
// icones coloridos (sem texto ao lado), com a legenda no topo da aba e a tabela completa sob demanda. Sem dado: escondido
const IND_ICO={desemprego:'<path d="M4 8h16v11H4zM9 8V5h6v3"/>',renda:'<circle cx="12" cy="12" r="8.5"/><path d="M14.5 9.5c-.5-.8-1.4-1.2-2.5-1.2-1.4 0-2.5.7-2.5 1.7s1.1 1.4 2.5 1.7 2.5.8 2.5 1.8-1.1 1.7-2.5 1.7c-1.1 0-2-.4-2.5-1.2M12 6.5v1.8M12 15.7v1.8"/>',
  analfabetismo:'<path d="M3 5h6.5A2.5 2.5 0 0 1 12 7.5V20a2 2 0 0 0-2-2H3zM21 5h-6.5A2.5 2.5 0 0 0 12 7.5V20a2 2 0 0 1 2-2h7z"/>',
  esgoto:'<path d="M12 3.5s5.5 6.3 5.5 10a5.5 5.5 0 0 1-11 0c0-3.7 5.5-10 5.5-10z"/>',mortalidade:'<path d="M12 20s-7-4.4-7-9.6A3.9 3.9 0 0 1 12 8a3.9 3.9 0 0 1 7 2.4C19 15.6 12 20 12 20z"/>'};
const icoInd=id=>`<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IND_ICO[id]||'<circle cx="12" cy="12" r="8"/>'}</svg>`;
const SETA={melhor:'<path d="M12 19V5M6 11l6-6 6 6"/>',pior:'<path d="M12 5v14M6 13l6 6 6-6"/>',igual:'<path d="M5 9h14M5 15h14"/>'};
const seta=t=>t?`<svg class="seta" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SETA[t]}</svg>`:"";
const TEND={melhor:"melhorou",pior:"piorou",igual:"ficou igual"};
const valorInd=(v,i)=>i.unidade==="R$"?"R$ "+NUM(v,0):i.unidade==="%"?PCT(Number(v.toFixed(i.casas))):NUM(v,i.casas)+" "+i.unidade;
const IB=()=>D&&D.ibge&&Array.isArray(D.ibge.indicadores)?D.ibge:null;
function rotuloInd(i,r){return`${i.nome}: ${valorInd(r[0],i)} (${r[2]})${r[4]?`, ${TEND[r[4]]}${r[3]?` desde ${r[3]}`:""}`:""}`;}
// icones do card do estado (chamado por representantes.js ao montar a grade)
function indUf(uf){
  const ib=IB(),v=ib&&ib.valores[uf];if(!v)return"";
  const itens=ib.indicadores.filter(i=>v[i.id]).map(i=>{const r=v[i.id],t=rotuloInd(i,r);return`<span class="ind ${r[4]||""}" role="img" title="${esc(t)}" aria-label="${esc(t)}">${icoInd(i.id)}</span>`;});
  return itens.length?`<span class="uf-ind">${itens.join("")}</span>`:"";
}
function indicadores(){
  const ib=IB();if(!ib)return;
  const br=ib.valores.BR||{},lista=$("ind-br");
  const itens=ib.indicadores.filter(i=>br[i.id]).map(i=>{const r=br[i.id];
    return`<li title="${esc(rotuloInd(i,r))}"><span class="ind ${r[4]||""}">${icoInd(i.id)}${seta(r[4])}</span> ${esc(i.nome)} <b>${valorInd(r[0],i)}</b> <a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(r[2])}</a></li>`;});
  const h=ib.idh;
  if(h&&h.valor){const t=h.anterior==null?"":Math.round(h.valor*1000)===Math.round(h.anterior*1000)?"igual":h.valor>h.anterior?"melhor":"pior";
    itens.push(`<li title="Índice de Desenvolvimento Humano do PNUD${h.posicao?`: ${h.posicao}º entre os países`:""}"><span class="ind ${t}">${seta(t)}</span> IDH <b>${NUM(h.valor,3)}</b>${h.posicao?` <small>${h.posicao}º no mundo</small>`:""} <a href="${esc(h.link)}" target="_blank" rel="noopener">PNUD ${h.ano}</a></li>`);}
  if(!itens.length)return;
  lista.innerHTML=itens.join("");lista.hidden=false;
  // legenda: cores e setas, os icones de cada indicador (usados sem texto nos cards) e as fontes
  const fontes=[...new Set(ib.indicadores.map(i=>i.fonte))].join(", ");
  $("ind-leg").innerHTML=`<span class="ind melhor">${seta("melhor")} melhorou</span><span class="ind pior">${seta("pior")} piorou</span><span class="ind">${seta("igual")} igual</span>
<span>em relação ao ano anterior.${ib.indicadores.length?" Nos estados:":""}</span>${ib.indicadores.map(i=>`<span>${icoInd(i.id)} ${esc(i.nome)}</span>`).join("")}<span>Fonte: ${[fontes&&`IBGE (${esc(fontes)})`,h&&"PNUD"].filter(Boolean).join(" e ")}.</span>`;
  $("ind-leg").hidden=false;
  const ufs=Object.keys(ib.valores).filter(u=>u!=="BR").sort((a,b)=>a.localeCompare(b));
  if(!ufs.length)return;
  $("ind-tabela").innerHTML=`<table class="resp"><thead><tr><th>Estado</th>${ib.indicadores.map(i=>`<th class="n"><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.nome)}</a></th>`).join("")}</tr></thead><tbody>${
    ["BR",...ufs].map(u=>`<tr><th scope="row">${u==="BR"?"Brasil":esc(u)}</th>${ib.indicadores.map(i=>{const r=(ib.valores[u]||{})[i.id];
      return`<td class="n">${r?`<span class="ind ${r[4]||""}" title="${esc(rotuloInd(i,r))}">${valorInd(r[0],i)} ${seta(r[4])}</span>`:"Não informado"}</td>`;}).join("")}</tr>`).join("")}</tbody></table>`;
  $("ind-tab").hidden=false;
}
// abas (#52): uma secao por vez e a pessoa escolhe o que aprofundar; sem JS tudo aparece em sequencia
const ABAS=[["destaques","Destaques"],["meus","Quem representa você"],["estados",ICO.mapa+" Estados"],["exemplares",ICO.estrela+" Exemplares"],["projetos",ICO.pata+" Projetos"],["cota","Cota parlamentar"],["numeros","Números"],["todos","Todas as pessoas"]];
let ABA="";
// abas desenhadas so quando abrem (#73): no celular, montar todas na carga travava a tela por 1 s
const DESENHO={exemplares,projetos,cota,numeros:()=>numeros(ROWS)},DESENHADAS=new Set();
function desenhaAba(id){if(!DESENHO[id]||DESENHADAS.has(id))return;DESENHADAS.add(id);DESENHO[id]();}
function mostraAbasComDados(){
  $("exemplares").hidden=!Array.isArray(D.exemplares);$("projetos").hidden=!(D.projetos||[]).length;$("cota").hidden=!(D.cota||[]).length;
}
function abrirAba(id,foco,inicio){
  if(!$("aba-"+id))id="destaques";ABA=id;desenhaAba(id);
  for(const [x] of ABAS){const b=$("aba-"+x);if(!b)continue;const on=x===id;$(x).classList.toggle("fora",!on);b.setAttribute("aria-selected",on);b.tabIndex=on?0:-1;if(on&&foco)b.focus();}
  if(id==="todos")todosAbrir(true);
  if(!inicio)try{history.replaceState(null,"","#"+id);}catch(e){}  // na carga nao: o navegador rolaria ate a ancora
}
function abas(){
  const nav=$("abas"),ids=ABAS.map(([id])=>id).filter(id=>!$(id).hidden);
  for(const [id,rot] of ABAS){if(!ids.includes(id))continue;const b=el("button");b.innerHTML=rot;b.type="button";b.id="aba-"+id;
    b.setAttribute("role","tab");b.setAttribute("aria-controls",id);b.onclick=()=>abrirAba(id);
    $(id).setAttribute("role","tabpanel");$(id).setAttribute("aria-labelledby",b.id);nav.append(b);}
  nav.onkeydown=ev=>{const d={ArrowRight:1,ArrowLeft:-1}[ev.key];if(!d)return;ev.preventDefault();abrirAba(ids[(ids.indexOf(ABA)+d+ids.length)%ids.length],true);};
  $("todos-abrir").parentElement.hidden=true;nav.hidden=false;document.documentElement.classList.add("abas-prontas");
  abrirAba(location.hash.slice(1),false,true);
}
// depois de filtrar (tag, legenda ou barra de grafico): volta aos destaques, na contagem
// cabecalho: total de pessoas em destaque e quantas cresceram mais do que o salario permitiria (sem valores em reais, #62)
function heroNum(){
  const mais=PES.filter(p=>p.per.some(a=>a.pat_ini>0&&a.cresc/a.pat_ini>=1)).length,b=$("hero-num");
  b.innerHTML=`<div><dd>${PES.length.toLocaleString("pt-BR")}</dd><dt>pessoas em destaque</dt></div><div><dd>${mais.toLocaleString("pt-BR")}</dd><dt>pelo menos dobraram o patrimônio</dt></div>`;
  b.hidden=!PES.length;
}
function verDestaques(){if(ABA&&ABA!=="destaques")abrirAba("destaques");$("contagem").scrollIntoView({behavior:"smooth",block:"start"});}
// filtros recolhidos no celular; o botao mostra quantos estao ativos
$("leg-mais").onclick=()=>{const on=$("legenda").classList.toggle("explicada");$("leg-mais").setAttribute("aria-expanded",on);$("leg-mais").textContent=on?"Esconder":"O que significa?";};
$("filtros-bt").onclick=()=>$("filtros-bt").setAttribute("aria-expanded",$("filtros").classList.toggle("aberto"));
if(D){contrib();todos();legenda();mostraAbasComDados();$("estados").hidden=$("meus").hidden=!D.representantes;indicadores();abas();heroNum();$("como-ler").addEventListener("toggle",()=>{if($("como-ler").open&&!$("leitura").childElementCount)leitura();});if(location.hash==="#como-ler")$("como-ler").open=true;document.getElementById("meta").textContent=`Atualizado em ${D.gerado_em} · ${D.universo.toLocaleString("pt-BR")} comparações no universo analisado`;
document.getElementById("q").oninput=draw;document.getElementById("nv").onchange=draw;
$("legenda").onclick=ev=>{const b=ev.target.closest("button[data-f]");if(!b||b.getAttribute("aria-disabled")==="true")return;if(b.dataset.todos){todosCom(b.dataset.v==="exemplar"?"e":"s");return;}F[b.dataset.f]=F[b.dataset.f]===b.dataset.v?"":b.dataset.v;draw();verDestaques();};
$("rg").onchange=()=>{F.regiao=$("rg").value;F.uf="";draw();};
$("cg").append(...[...new Set(D.alertas.map(a=>a.cargo).filter(Boolean))].sort((x,y)=>x.localeCompare(y,"pt-BR")).map(c=>{const o=el("option",null,c);o.value=c;return o;}));$("cg").onchange=()=>{F.cargo=$("cg").value;draw();};$("mais").onclick=mais;
// tags clicaveis (cards e tabela): cargo, partido e UF filtram pela dimensao; marcacoes filtram pela legenda
const porTag=ev=>{const t=ev.target.closest("button[data-dim],button[data-f]");if(!t)return;if(t.dataset.f)F[t.dataset.f]=t.dataset.v;else F[t.dataset.dim]=t.dataset.v;draw();verDestaques();};
$("cards").onclick=porTag;document.addEventListener("click",verDet);$("tb").onclick=porTag;$("exemplares-lista").onclick=$("cota-lista").onclick=$("projetos-lista").onclick=porTag;$("tabela").ontoggle=tabelaToda;draw();}
document.documentElement.classList.add("abas-prontas");  // sem dados as secoes voltam a aparecer em sequencia

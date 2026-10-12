'use strict';
const $=id=>document.getElementById(id);
const pageSize=25;
let news=null,category='all',visible=pageSize,loading=false;
const dateFormat=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Tallinn',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false});
const refreshFormat=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Tallinn',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;}
function safeLink(url,text,className){const link=element('a',className,text);const parsed=new URL(url,location.href);if(!['http:','https:'].includes(parsed.protocol))throw new Error('Invalid publisher link');link.href=parsed.href;link.target='_blank';link.rel='noopener noreferrer';return link;}
function matches(){const query=$('search').value.normalize('NFKC').toLocaleLowerCase().trim();const source=$('source').value;return news.articles.filter(story=>story.reports.some(report=>(category==='all'||report.category===category)&&(source==='all'||report.source===source)&&(!query||report.title.normalize('NFKC').toLocaleLowerCase().includes(query))));}
function card(story){const selected=$('source').value;const report=story.reports.find(report=>(category==='all'||report.category===category)&&(selected==='all'||report.source===selected))||story.primary;const source=news.sources.find(source=>source.id===report.source);const article=element('article');article.lang=report.language;const metadata=element('p','metadata');metadata.append(element('span','source-name',source.name));const time=element('time',null,dateFormat.format(new Date(report.published_at)));time.dateTime=report.published_at;time.title=(report.date_basis==='updated'?'Feed update time':'Publication time')+' · Europe/Tallinn';metadata.append(time,element('span','language',report.language.toUpperCase()));if(category==='all')metadata.append(element('span','category',news.categories[report.category]));const heading=element('h2');heading.append(safeLink(report.url,report.title));article.append(metadata,heading);if(report.excerpt)article.append(element('p','excerpt',report.excerpt));const others=story.reports.filter(item=>item.source!==report.source||item.url!==report.url);if(others.length){const details=element('details','alternatives');details.append(element('summary',null,`Also reported by ${others.length} ${others.length===1?'source':'sources'}`));for(const other of others){const label=news.sources.find(s=>s.id===other.source)?.name||other.source;const link=safeLink(other.url,label);link.title=other.title;link.lang=other.language;details.append(link);}article.append(details);}return article;}
function render(){if(!news)return;const items=matches();$('articles').replaceChildren(...items.slice(0,visible).map(card));$('result-count').textContent=`${items.length.toLocaleString()} ${items.length===1?'story':'stories'}`;$('empty').hidden=items.length>0;$('more').hidden=visible>=items.length;}
function populateSources(){const prior=$('source').value;$('source').replaceChildren(element('option',null,'All sources'));$('source').firstElementChild.value='all';for(const source of news.sources.filter(source=>category==='all'||source.category===category).sort((a,b)=>a.name.localeCompare(b.name))){const option=element('option',null,source.name);option.value=source.id;$('source').append(option);}if(Array.from($('source').options).some(option=>option.value===prior))$('source').value=prior;}
$('categories').addEventListener('click',event=>{const button=event.target.closest('button[data-category]');if(!button)return;category=button.dataset.category;visible=pageSize;for(const tab of $('categories').querySelectorAll('button'))tab.setAttribute('aria-pressed',String(tab===button));populateSources();render();});
$('search').addEventListener('input',()=>{visible=pageSize;render();});$('source').addEventListener('change',()=>{visible=pageSize;render();});$('more').addEventListener('click',()=>{visible+=pageSize;render();});
async function start(){
  if(loading)return;
  loading=true;
  try{
    const response=await fetch('data/news.json',{cache:'no-cache'});
    if(!response.ok)throw new Error('Could not load the latest edition.');
    const next=await response.json();
    const changed=!news||next.updated_at!==news.updated_at;
    news=next;
    $('updated').textContent='Updated '+refreshFormat.format(new Date(news.updated_at))+' · Tallinn';
    const age=(Date.now()-new Date(news.updated_at))/3600000;
    $('notice').hidden=age<=12;
    if(age>12)$('notice').textContent='This edition is more than 12 hours old. The last successful collection is still available while the next refresh runs.';
    if(!changed)return;
    populateSources();render();
    const status=element('div');
    status.append(element('p',null,`${news.stats.stored_reports.toLocaleString()} publisher reports · ${news.stats.duplicates_consolidated.toLocaleString()} duplicate reports consolidated. RSS excerpts may be shortened. Headlines and claims remain attributed to their publishers.`));
    const list=element('ul');
    for(const source of news.sources){
      const health=news.source_status.find(item=>item.id===source.id);
      const item=element('li');
      item.append(safeLink(source.website,source.name),document.createTextNode(` · ${source.language.toUpperCase()} · ${health?.status==='ok'?'feed current':health?.status==='stale'?'no recent feed items':'feed unavailable; retained recent articles'}`));
      list.append(item);
    }
    status.append(list);$('source-status').replaceChildren(status);
  }catch(error){
    if(!news)$('updated').textContent='Edition unavailable';
    $('notice').textContent=news?'Could not check for a newer edition. Your last loaded edition is still available.':error.message+' Please reload in a moment.';
    $('notice').hidden=false;
  }finally{loading=false;}
}
start();
setInterval(()=>{if(!document.hidden)start();},5*60*1000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)start();});

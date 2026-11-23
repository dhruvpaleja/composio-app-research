(function(){
  var rows=[].slice.call(document.querySelectorAll('tr.arow-main'));
  var q=document.getElementById('q'),fc=document.getElementById('fcat'),fv=document.getElementById('fver'),fa=document.getElementById('facc'),fp=document.getElementById('fcomp'),cnt=document.getElementById('count'),rs=document.getElementById('freset');
  function apply(){var t=(q.value||'').toLowerCase().trim(),n=0;
    rows.forEach(function(r){var ok=(!t||r.dataset.q.indexOf(t)>-1)&&(!fc.value||r.dataset.cat===fc.value)&&(!fv.value||r.dataset.verdict===fv.value)&&(!fa.value||r.dataset.access===fa.value)&&(!fp.checked||r.dataset.comp==='n');
      r.hidden=!ok;var d=r.nextElementSibling;if(!ok&&d)d.hidden=true;if(ok)n++;});
    [fc,fv,fa].forEach(function(s){s.classList.toggle('set',!!s.value);});
    var any=!!(t||fc.value||fv.value||fa.value||fp.checked);
    if(rs)rs.hidden=!any;
    cnt.textContent=any?(n+' of '+rows.length+' apps'):(n+(n===1?' app':' apps'));}
  function clear(){q.value='';[fc,fv,fa].forEach(function(e){e.value='';});fp.checked=false;apply();}
  [q,fc,fv,fa,fp].forEach(function(el){el.addEventListener('input',apply);el.addEventListener('change',apply);});
  if(rs)rs.addEventListener('click',function(){clear();q.focus();});
  q.addEventListener('keydown',function(e){if(e.key==='Escape'){clear();}});
  document.querySelectorAll('button.exp').forEach(function(b){b.addEventListener('click',function(){
    var d=document.getElementById(b.getAttribute('aria-controls'));var open=b.getAttribute('aria-expanded')==='true';
    b.setAttribute('aria-expanded',String(!open));d.hidden=open;});});
  function openHash(){var m=location.hash.match(/^#app-(\d+)$/);if(!m)return;var r=document.getElementById('app-'+m[1]);if(!r)return;
    clear();
    var b=r.querySelector('button.exp');if(b&&b.getAttribute('aria-expanded')!=='true')b.click();}
  window.addEventListener('hashchange',openHash);openHash();
  // scroll-spy: highlight the section currently in view
  var links=[].slice.call(document.querySelectorAll('.top nav a')),map={};
  links.forEach(function(a){map[a.getAttribute('href').slice(1)]=a;});
  if('IntersectionObserver' in window){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){links.forEach(function(a){a.classList.remove('on');a.removeAttribute('aria-current');});
      var a=map[e.target.id];if(a){a.classList.add('on');a.setAttribute('aria-current','true');}}});},{rootMargin:'-35% 0px -60% 0px'});
    Object.keys(map).forEach(function(id){var s=document.getElementById(id);if(s)io.observe(s);});
  }
})();
